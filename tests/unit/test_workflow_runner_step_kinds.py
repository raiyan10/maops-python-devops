"""Every ``_run_step`` branch in ``core/workflow_runner.py``: one test per
step kind (tools_inspect, logs_analyze, health_http, health_tcp -- doctor
and inventory_system/inventory_filesystem are already covered by
``test_workflow_runner.py``), plus the post-normalization failure branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import maops_pydevops.core.workflow_runner as workflow_runner
from maops_pydevops.core.health_models import (
    HealthProtocol,
    HttpMethod,
    HttpOptions,
    HttpReport,
    HttpSummary,
    TcpOptions,
    TcpReport,
    TcpSummary,
)
from maops_pydevops.core.log_models import (
    LogAnalysisOptions,
    LogAnalysisReport,
    LogAnalysisSummary,
    LogAnalysisTime,
    LogInputFormat,
)
from maops_pydevops.core.models import (
    CheckStatus,
    ToolInspectionResult,
    ToolsInspectReport,
    ToolsRunConfiguration,
)
from maops_pydevops.core.workflow_models import (
    HealthHttpStepParams,
    HealthTcpStepParams,
    LogsAnalyzeStepParams,
    ToolsInspectStepParams,
    Workflow,
    WorkflowStep,
    WorkflowStepKind,
)
from maops_pydevops.core.workflow_runner import run_workflow


def test_tools_inspect_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_build_inspect_report(
        *,
        tool_names: object,
        version: str,
        timeout_seconds: float,
        max_output_bytes: int,
        config_path: str,
    ) -> ToolsInspectReport:
        captured["timeout_seconds"] = timeout_seconds
        captured["tool_names"] = tool_names
        tool = ToolInspectionResult(
            name="git",
            executable="/usr/bin/git",
            status=CheckStatus.PASS,
            exit_code=0,
            timed_out=False,
            duration_ms=1,
            stdout="git version 2\n",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            detail="ok",
        )
        return ToolsInspectReport(
            version="0.6.0",
            configuration=ToolsRunConfiguration(
                path="(workflow)",
                command_timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
            ),
            tools=(tool,),
            overall=CheckStatus.PASS,
        )

    monkeypatch.setattr(workflow_runner, "build_inspect_report", _fake_build_inspect_report)
    workflow = Workflow(
        schema_version=1,
        name="tools",
        steps=(
            WorkflowStep(
                id="t1",
                kind=WorkflowStepKind.TOOLS_INSPECT,
                params=ToolsInspectStepParams(tools=("git",), timeout_seconds=5.0),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "pass"
    assert captured["timeout_seconds"] == 5.0
    assert captured["tool_names"] == ("git",)


def test_tools_inspect_step_uses_default_timeout_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def _fake_build_inspect_report(
        *,
        tool_names: object,
        version: str,
        timeout_seconds: float,
        max_output_bytes: int,
        config_path: str,
    ) -> ToolsInspectReport:
        captured["timeout_seconds"] = timeout_seconds
        return ToolsInspectReport(
            version="0.6.0",
            configuration=ToolsRunConfiguration(
                path="(workflow)",
                command_timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
            ),
            tools=(),
            overall=CheckStatus.PASS,
        )

    monkeypatch.setattr(workflow_runner, "build_inspect_report", _fake_build_inspect_report)
    workflow = Workflow(
        schema_version=1,
        name="tools",
        steps=(
            WorkflowStep(
                id="t1", kind=WorkflowStepKind.TOOLS_INSPECT, params=ToolsInspectStepParams()
            ),
        ),
    )
    run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    from maops_pydevops.core.config_models import DEFAULT_COMMAND_TIMEOUT_SECONDS

    assert captured["timeout_seconds"] == DEFAULT_COMMAND_TIMEOUT_SECONDS


def _log_analysis_report(overall: CheckStatus) -> LogAnalysisReport:
    return LogAnalysisReport(
        version="0.6.0",
        path="/var/log/app.log",
        options=LogAnalysisOptions(
            input_format=LogInputFormat.AUTO,
            max_lines=10000,
            max_bytes=10485760,
            max_line_bytes=65536,
            top=10,
            bucket_seconds=300,
            repeat_threshold=5,
            error_threshold=1,
            redact=True,
        ),
        summary=LogAnalysisSummary(
            bytes_read=1, lines_read=1, events_parsed=1, malformed_lines=0, overlong_lines=0
        ),
        severity_counts=(),
        source_counts=(),
        top_signatures=(),
        time=LogAnalysisTime(
            timestamped_events=0,
            first_timestamp=None,
            last_timestamp=None,
            out_of_order_events=0,
            bucket_seconds=300,
            peak_bucket_start=None,
            peak_bucket_count=0,
        ),
        findings=(),
        issues=(),
        line_limit_reached=False,
        byte_limit_reached=False,
        truncated=False,
        overall=overall,
    )


def test_logs_analyze_step_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_build_log_analysis_report(
        path_arg: str, **kwargs: object
    ) -> tuple[LogAnalysisReport, None]:
        captured["path_arg"] = path_arg
        return _log_analysis_report(CheckStatus.PASS), None

    monkeypatch.setattr(
        workflow_runner, "build_log_analysis_report", _fake_build_log_analysis_report
    )
    workflow = Workflow(
        schema_version=1,
        name="logs",
        steps=(
            WorkflowStep(
                id="l1",
                kind=WorkflowStepKind.LOGS_ANALYZE,
                params=LogsAnalyzeStepParams(path="app.log"),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "pass"
    assert captured["path_arg"] == str(tmp_path / "app.log")


def test_logs_analyze_step_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner,
        "build_log_analysis_report",
        lambda path_arg, **kwargs: (None, "cannot open file"),
    )
    workflow = Workflow(
        schema_version=1,
        name="logs",
        steps=(
            WorkflowStep(
                id="l1",
                kind=WorkflowStepKind.LOGS_ANALYZE,
                params=LogsAnalyzeStepParams(path="app.log"),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "fail"
    assert report.steps[0].error == "cannot open file"


def _http_report(overall: CheckStatus) -> HttpReport:
    return HttpReport(
        version="0.6.0",
        protocol=HealthProtocol.HTTP,
        options=HttpOptions(
            method=HttpMethod.GET,
            expected_status_min=200,
            expected_status_max=399,
            timeout_seconds=3.0,
            retries=1,
            retry_delay_seconds=0.25,
            workers=4,
            follow_redirects=False,
            tls_verify=True,
        ),
        summary=HttpSummary(targets=1, passed=1, warned=0, failed=0, attempts=1),
        results=(),
        overall=overall,
    )


def test_health_http_step_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner,
        "build_health_http_report",
        lambda urls, **kwargs: (_http_report(CheckStatus.PASS), None),
    )
    workflow = Workflow(
        schema_version=1,
        name="http",
        steps=(
            WorkflowStep(
                id="h1",
                kind=WorkflowStepKind.HEALTH_HTTP,
                params=HealthHttpStepParams(urls=("http://127.0.0.1:1/",)),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "pass"


def test_health_http_step_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_health_http_report", lambda urls, **kwargs: (None, "invalid target")
    )
    workflow = Workflow(
        schema_version=1,
        name="http",
        steps=(
            WorkflowStep(
                id="h1",
                kind=WorkflowStepKind.HEALTH_HTTP,
                params=HealthHttpStepParams(urls=("http://127.0.0.1:1/",)),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "fail"
    assert report.steps[0].error == "invalid target"


def _tcp_report(overall: CheckStatus) -> TcpReport:
    return TcpReport(
        version="0.6.0",
        protocol=HealthProtocol.TCP,
        options=TcpOptions(timeout_seconds=3.0, retries=1, retry_delay_seconds=0.25, workers=4),
        summary=TcpSummary(targets=1, passed=1, warned=0, failed=0, attempts=1),
        results=(),
        overall=overall,
    )


def test_health_tcp_step_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner,
        "build_health_tcp_report",
        lambda targets, **kwargs: (_tcp_report(CheckStatus.PASS), None),
    )
    workflow = Workflow(
        schema_version=1,
        name="tcp",
        steps=(
            WorkflowStep(
                id="t1",
                kind=WorkflowStepKind.HEALTH_TCP,
                params=HealthTcpStepParams(targets=("127.0.0.1:1",)),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "pass"


def test_health_tcp_step_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner,
        "build_health_tcp_report",
        lambda targets, **kwargs: (None, "invalid target"),
    )
    workflow = Workflow(
        schema_version=1,
        name="tcp",
        steps=(
            WorkflowStep(
                id="t1",
                kind=WorkflowStepKind.HEALTH_TCP,
                params=HealthTcpStepParams(targets=("127.0.0.1:1",)),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "fail"
    assert report.steps[0].error == "invalid target"


def test_step_normalization_failure_becomes_fail_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        workflow_runner,
        "build_health_tcp_report",
        lambda targets, **kwargs: (_tcp_report(CheckStatus.PASS), None),
    )
    monkeypatch.setattr(
        workflow_runner, "normalize_report", lambda kind, raw, *, source_path: (None, "boom")
    )
    workflow = Workflow(
        schema_version=1,
        name="tcp",
        steps=(
            WorkflowStep(
                id="t1",
                kind=WorkflowStepKind.HEALTH_TCP,
                params=HealthTcpStepParams(targets=("127.0.0.1:1",)),
            ),
        ),
    )
    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)
    assert report.steps[0].status.value == "fail"
    assert report.steps[0].error == "boom"
