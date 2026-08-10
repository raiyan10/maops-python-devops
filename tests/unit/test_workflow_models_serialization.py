"""JSON field-type coverage for workflow validation/run report models."""

from __future__ import annotations

import json

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.report_models import ReportMetric
from maops_pydevops.core.workflow_models import (
    WorkflowRunOptions,
    WorkflowRunReport,
    WorkflowRunSummary,
    WorkflowStepKind,
    WorkflowStepResult,
    WorkflowValidationReport,
    WorkflowValidationStatus,
)


def test_workflow_validation_report_json_field_types() -> None:
    report = WorkflowValidationReport(
        version="0.6.0",
        path="wf.toml",
        status=WorkflowValidationStatus.VALID,
        workflow_name="demo",
        step_count=2,
        error=None,
    )
    data = json.loads(report.to_json())
    assert isinstance(data["version"], str)
    assert isinstance(data["path"], str)
    assert isinstance(data["status"], str)
    assert isinstance(data["workflow_name"], str)
    assert isinstance(data["step_count"], int)
    assert data["error"] is None


def test_workflow_validation_report_invalid_error_is_string() -> None:
    report = WorkflowValidationReport(
        version="0.6.0",
        path="wf.toml",
        status=WorkflowValidationStatus.INVALID,
        workflow_name=None,
        step_count=0,
        error="something went wrong",
    )
    data = json.loads(report.to_json())
    assert data["workflow_name"] is None
    assert isinstance(data["error"], str)


def test_workflow_run_report_json_field_types() -> None:
    step = WorkflowStepResult(
        id="a",
        kind=WorkflowStepKind.DOCTOR,
        status=CheckStatus.PASS,
        headline="1 check(s): 1 pass, 0 warn, 0 fail",
        metrics=(ReportMetric("checks_total", "1"),),
        error=None,
    )
    report = WorkflowRunReport(
        version="0.6.0",
        path="wf.toml",
        name="demo",
        options=WorkflowRunOptions(max_steps=32),
        summary=WorkflowRunSummary(steps=1, pass_count=1, warn_count=0, fail_count=0),
        steps=(step,),
        overall=CheckStatus.PASS,
    )
    data = json.loads(report.to_json())
    assert isinstance(data["version"], str)
    assert isinstance(data["path"], str)
    assert isinstance(data["name"], str)
    assert isinstance(data["options"]["max_steps"], int)
    assert isinstance(data["summary"]["steps"], int)
    assert isinstance(data["summary"]["pass_count"], int)
    assert isinstance(data["summary"]["warn_count"], int)
    assert isinstance(data["summary"]["fail_count"], int)
    assert isinstance(data["steps"], list)
    step_entry = data["steps"][0]
    assert isinstance(step_entry["id"], str)
    assert isinstance(step_entry["kind"], str)
    assert isinstance(step_entry["status"], str)
    assert isinstance(step_entry["headline"], str)
    assert isinstance(step_entry["metrics"], list)
    assert step_entry["error"] is None
    assert isinstance(data["overall"], str)


def test_workflow_run_report_json_is_deterministic() -> None:
    step = WorkflowStepResult(
        id="a",
        kind=WorkflowStepKind.DOCTOR,
        status=CheckStatus.PASS,
        headline="ok",
        metrics=(),
        error=None,
    )
    report = WorkflowRunReport(
        version="0.6.0",
        path="wf.toml",
        name="demo",
        options=WorkflowRunOptions(max_steps=32),
        summary=WorkflowRunSummary(steps=1, pass_count=1, warn_count=0, fail_count=0),
        steps=(step,),
        overall=CheckStatus.PASS,
    )
    assert report.to_json() == report.to_json()


def test_workflow_step_result_error_field_present_on_fail() -> None:
    step = WorkflowStepResult(
        id="a",
        kind=WorkflowStepKind.INVENTORY_FILESYSTEM,
        status=CheckStatus.FAIL,
        headline="root path does not exist",
        metrics=(),
        error="root path does not exist",
    )
    data = json.loads(json.dumps(step.to_dict()))
    assert data["error"] == "root path does not exist"
