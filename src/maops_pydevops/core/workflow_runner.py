"""Sequential execution of a validated workflow's declared steps.

Executes each step through the package's own existing internal APIs
(``commands/doctor.py``, ``commands/tools.py``, ``commands/inventory.py``,
``commands/logs.py``, ``commands/health.py``) -- never a recursive
``maops-py`` subprocess, never a shell, never dynamic imports or
``eval``/``exec``. This is the one module in the ``core/`` package
permitted to import from ``commands/``: its entire purpose is to
orchestrate across other commands' own orchestration functions, the same
"real" APIs each equivalent CLI subcommand calls. Steps always run in
declared order, one at a time; a step that cannot produce a report becomes
a FAIL :class:`~maops_pydevops.core.workflow_models.WorkflowStepResult`
rather than aborting the run, so already-completed step results are never
discarded.
"""

from __future__ import annotations

from pathlib import Path

from maops_pydevops.commands.doctor import build_report as build_doctor_report
from maops_pydevops.commands.health import build_health_http_report, build_health_tcp_report
from maops_pydevops.commands.inventory import build_filesystem_report, build_system_report
from maops_pydevops.commands.logs import build_log_analysis_report
from maops_pydevops.commands.tools import build_inspect_report
from maops_pydevops.core.config_models import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_MAX_OUTPUT_BYTES,
)
from maops_pydevops.core.health_models import HttpMethod
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.report_aggregate import normalize_report
from maops_pydevops.core.report_models import ReportKind
from maops_pydevops.core.workflow_models import (
    MAX_WORKFLOW_STEPS,
    DoctorStepParams,
    HealthHttpStepParams,
    HealthTcpStepParams,
    InventoryFilesystemStepParams,
    InventorySystemStepParams,
    LogsAnalyzeStepParams,
    ToolsInspectStepParams,
    Workflow,
    WorkflowRunOptions,
    WorkflowRunReport,
    WorkflowRunSummary,
    WorkflowStep,
    WorkflowStepResult,
)
from maops_pydevops.version import get_version


def _resolve_relative(raw: str, workflow_dir: Path) -> str:
    """Resolve ``raw`` against ``workflow_dir`` (never the process cwd).

    A lexical join only -- an already-absolute path is returned as-is,
    never re-based, and no filesystem access or ``os.chdir()`` occurs
    here.
    """
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    return str(workflow_dir / candidate)


def _error_result(step: WorkflowStep, error: str | None) -> WorkflowStepResult:
    return WorkflowStepResult(
        id=step.id,
        kind=step.kind,
        status=CheckStatus.FAIL,
        headline=error or "step failed",
        metrics=(),
        error=error or "step failed",
    )


def _run_step(step: WorkflowStep, *, workflow_dir: Path) -> WorkflowStepResult:
    params = step.params
    raw: dict[str, object]

    if isinstance(params, DoctorStepParams):
        raw = build_doctor_report().to_dict()
        kind = ReportKind.DOCTOR

    elif isinstance(params, ToolsInspectStepParams):
        timeout_seconds = (
            params.timeout_seconds
            if params.timeout_seconds is not None
            else DEFAULT_COMMAND_TIMEOUT_SECONDS
        )
        raw = build_inspect_report(
            tool_names=params.tools,
            version=get_version(),
            timeout_seconds=timeout_seconds,
            max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            config_path="(workflow)",
        ).to_dict()
        kind = ReportKind.TOOLS_INSPECT

    elif isinstance(params, InventorySystemStepParams):
        raw = build_system_report().to_dict()
        kind = ReportKind.INVENTORY_SYSTEM

    elif isinstance(params, InventoryFilesystemStepParams):
        path_arg = (
            _resolve_relative(params.path, workflow_dir)
            if params.path is not None
            else str(workflow_dir)
        )
        fs_report, fs_error = build_filesystem_report(
            path_arg, max_depth=params.max_depth, max_entries=params.max_entries, top=params.top
        )
        if fs_report is None:
            return _error_result(step, fs_error)
        raw = fs_report.to_dict()
        kind = ReportKind.INVENTORY_FILESYSTEM

    elif isinstance(params, LogsAnalyzeStepParams):
        path_arg = _resolve_relative(params.path, workflow_dir)
        log_report, log_error = build_log_analysis_report(
            path_arg,
            input_format=LogInputFormat(params.input_format),
            max_lines=params.max_lines,
            max_bytes=params.max_bytes,
            max_line_bytes=params.max_line_bytes,
            top=params.top,
            bucket_seconds=params.bucket_seconds,
            repeat_threshold=params.repeat_threshold,
            error_threshold=params.error_threshold,
            redact=params.redact,
        )
        if log_report is None:
            return _error_result(step, log_error)
        raw = log_report.to_dict()
        kind = ReportKind.LOGS_ANALYZE

    elif isinstance(params, HealthHttpStepParams):
        http_report, http_error = build_health_http_report(
            params.urls,
            method=HttpMethod(params.method),
            expected_status_min=params.expect_status_min,
            expected_status_max=params.expect_status_max,
            timeout_seconds=params.timeout_seconds,
            retries=params.retries,
            retry_delay_seconds=params.retry_delay_seconds,
            workers=params.workers,
        )
        if http_report is None:
            return _error_result(step, http_error)
        raw = http_report.to_dict()
        kind = ReportKind.HEALTH_HTTP

    elif isinstance(params, HealthTcpStepParams):
        tcp_report, tcp_error = build_health_tcp_report(
            params.targets,
            timeout_seconds=params.timeout_seconds,
            retries=params.retries,
            retry_delay_seconds=params.retry_delay_seconds,
            workers=params.workers,
        )
        if tcp_report is None:
            return _error_result(step, tcp_error)
        raw = tcp_report.to_dict()
        kind = ReportKind.HEALTH_TCP

    else:  # pragma: no cover - exhaustive over the closed StepParams union
        raise AssertionError(f"unreachable step params type: {type(params)!r}")

    normalized, normalize_error = normalize_report(kind, raw, source_path=step.id)
    if normalized is None:
        return _error_result(step, normalize_error)
    return WorkflowStepResult(
        id=step.id,
        kind=step.kind,
        status=normalized.status,
        headline=normalized.headline,
        metrics=normalized.metrics,
        error=None,
    )


def run_workflow(
    workflow: Workflow, *, workflow_path: str, workflow_dir: Path
) -> WorkflowRunReport:
    """Execute every step of ``workflow`` in declared order, sequentially.

    Every step always runs, regardless of an earlier step's outcome --
    there is no fail-fast short-circuit -- so a failed step never discards
    already-completed results.
    """
    results = tuple(_run_step(step, workflow_dir=workflow_dir) for step in workflow.steps)

    pass_count = sum(1 for result in results if result.status is CheckStatus.PASS)
    warn_count = sum(1 for result in results if result.status is CheckStatus.WARN)
    fail_count = sum(1 for result in results if result.status is CheckStatus.FAIL)

    if fail_count > 0:
        overall = CheckStatus.FAIL
    elif warn_count > 0:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    return WorkflowRunReport(
        version=get_version(),
        path=workflow_path,
        name=workflow.name,
        options=WorkflowRunOptions(max_steps=MAX_WORKFLOW_STEPS),
        summary=WorkflowRunSummary(
            steps=len(results), pass_count=pass_count, warn_count=warn_count, fail_count=fail_count
        ),
        steps=results,
        overall=overall,
    )
