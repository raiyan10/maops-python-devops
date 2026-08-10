"""Sequential workflow step execution, ordering, and aggregate rollup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import maops_pydevops.core.workflow_runner as workflow_runner
from maops_pydevops.core.inventory_models import (
    FilesystemInventoryReport,
    FilesystemScanOptions,
    FilesystemScanSummary,
)
from maops_pydevops.core.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
    PlatformInfo,
    PythonInfo,
)
from maops_pydevops.core.workflow_models import (
    DoctorStepParams,
    InventoryFilesystemStepParams,
    Workflow,
    WorkflowStep,
    WorkflowStepKind,
)
from maops_pydevops.core.workflow_runner import run_workflow

_PYTHON_INFO = PythonInfo(version="3.12.0", executable="/usr/bin/python3", supported=True)
_PLATFORM_INFO = PlatformInfo(
    system="Linux", release="6.8.0", architecture="x86_64", filesystem_encoding="utf-8"
)


def _doctor_report(status: CheckStatus) -> DoctorReport:
    check = DoctorCheck(name="python_version", status=status, required=True, detail="ok")
    return DoctorReport(
        version="0.6.0",
        python=_PYTHON_INFO,
        platform=_PLATFORM_INFO,
        checks=(check,),
        overall=status,
    )


def _step(step_id: str, kind: WorkflowStepKind = WorkflowStepKind.DOCTOR) -> WorkflowStep:
    return WorkflowStep(id=step_id, kind=kind, params=DoctorStepParams())


def test_sequential_execution_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    call_order: list[str] = []

    def _fake_build_doctor_report() -> DoctorReport:
        call_order.append("called")
        return _doctor_report(CheckStatus.PASS)

    monkeypatch.setattr(workflow_runner, "build_doctor_report", _fake_build_doctor_report)
    workflow = Workflow(schema_version=1, name="seq", steps=(_step("a"), _step("b"), _step("c")))
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert [step.id for step in report.steps] == ["a", "b", "c"]
    assert call_order == ["called", "called", "called"]


def test_pass_aggregate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(CheckStatus.PASS)
    )
    workflow = Workflow(schema_version=1, name="p", steps=(_step("a"), _step("b")))
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.overall.value == "pass"
    assert report.summary.pass_count == 2
    assert report.summary.fail_count == 0


def test_warn_aggregate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([CheckStatus.PASS, CheckStatus.WARN])
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(next(responses))
    )
    workflow = Workflow(schema_version=1, name="w", steps=(_step("a"), _step("b")))
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.overall.value == "warn"
    assert report.summary.warn_count == 1
    assert report.summary.fail_count == 0


def test_fail_aggregate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL])
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(next(responses))
    )
    workflow = Workflow(schema_version=1, name="f", steps=(_step("a"), _step("b"), _step("c")))
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.overall.value == "fail"
    assert report.summary.pass_count == 1
    assert report.summary.warn_count == 1
    assert report.summary.fail_count == 1


def test_prior_results_preserved_when_later_step_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(CheckStatus.PASS)
    )

    def _failing_filesystem_report(
        path_arg: str | None, *, max_depth: int, max_entries: int, top: int
    ) -> tuple[FilesystemInventoryReport | None, str | None]:
        return None, "root path does not exist"

    monkeypatch.setattr(workflow_runner, "build_filesystem_report", _failing_filesystem_report)

    workflow = Workflow(
        schema_version=1,
        name="mixed",
        steps=(
            _step("first", WorkflowStepKind.DOCTOR),
            WorkflowStep(
                id="second",
                kind=WorkflowStepKind.INVENTORY_FILESYSTEM,
                params=InventoryFilesystemStepParams(path="missing"),
            ),
            _step("third", WorkflowStepKind.DOCTOR),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert [step.id for step in report.steps] == ["first", "second", "third"]
    assert report.steps[0].status.value == "pass"
    assert report.steps[0].error is None
    assert report.steps[1].status.value == "fail"
    assert report.steps[1].error == "root path does not exist"
    assert report.steps[2].status.value == "pass"
    assert report.overall.value == "fail"
    assert report.summary.steps == 3


def test_relative_path_resolved_against_workflow_dir_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    captured: dict[str, object] = {}

    def _fake_filesystem_report(
        path_arg: str | None, *, max_depth: int, max_entries: int, top: int
    ) -> tuple[FilesystemInventoryReport | None, str | None]:
        captured["path_arg"] = path_arg
        options = FilesystemScanOptions(max_depth=max_depth, max_entries=max_entries, top=top)
        summary = FilesystemScanSummary(
            scanned_entries=0,
            directories=0,
            files=0,
            symlinks=0,
            other=0,
            total_file_bytes=0,
            skipped_entries=0,
            inaccessible_entries=0,
            different_filesystem_entries=0,
        )
        report = FilesystemInventoryReport(
            version="0.6.0",
            root=path_arg or "",
            options=options,
            summary=summary,
            largest_files=(),
            issues=(),
            max_depth_reached=False,
            truncated=False,
            overall=CheckStatus.PASS,
        )
        return report, None

    monkeypatch.setattr(workflow_runner, "build_filesystem_report", _fake_filesystem_report)
    unrelated_cwd = tmp_path / "unrelated"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    workflow = Workflow(
        schema_version=1,
        name="relpath",
        steps=(
            WorkflowStep(
                id="fs",
                kind=WorkflowStepKind.INVENTORY_FILESYSTEM,
                params=InventoryFilesystemStepParams(path="subdir"),
            ),
        ),
    )
    run_workflow(workflow, workflow_path=str(workflow_dir / "wf.toml"), workflow_dir=workflow_dir)
    assert captured["path_arg"] == str(workflow_dir / "subdir")


def test_no_cwd_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(CheckStatus.PASS)
    )
    before = os.getcwd()
    workflow = Workflow(schema_version=1, name="cwd", steps=(_step("a"),))
    run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert os.getcwd() == before


def test_inventory_filesystem_default_path_is_workflow_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def _fake_filesystem_report(
        path_arg: str | None, *, max_depth: int, max_entries: int, top: int
    ) -> tuple[FilesystemInventoryReport | None, str | None]:
        captured["path_arg"] = path_arg
        options = FilesystemScanOptions(max_depth=max_depth, max_entries=max_entries, top=top)
        summary = FilesystemScanSummary(0, 0, 0, 0, 0, 0, 0, 0, 0)
        report = FilesystemInventoryReport(
            version="0.6.0",
            root=path_arg or "",
            options=options,
            summary=summary,
            largest_files=(),
            issues=(),
            max_depth_reached=False,
            truncated=False,
            overall=CheckStatus.PASS,
        )
        return report, None

    monkeypatch.setattr(workflow_runner, "build_filesystem_report", _fake_filesystem_report)
    workflow = Workflow(
        schema_version=1,
        name="default-path",
        steps=(
            WorkflowStep(
                id="fs",
                kind=WorkflowStepKind.INVENTORY_FILESYSTEM,
                params=InventoryFilesystemStepParams(path=None),
            ),
        ),
    )
    run_workflow(workflow, workflow_path=str(tmp_path / "wf.toml"), workflow_dir=tmp_path)
    assert captured["path_arg"] == str(tmp_path)
