"""Allowlisted, read-only DevOps-tool version inspection.

Only the five listed tools may ever be inspected, and only via their fixed,
hardcoded argv definitions -- never a user-composed command.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence

from maops_pydevops.core.models import (
    CheckStatus,
    ToolInspectionResult,
    ToolsInspectReport,
    ToolsRunConfiguration,
)
from maops_pydevops.core.runner import CommandResult, CommandSpec, RunFailureReason, run_command

TOOL_ALLOWLIST: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("git", ("git", "--version")),
    ("docker", ("docker", "--version")),
    ("kubectl", ("kubectl", "version", "--client=true")),
    ("terraform", ("terraform", "version")),
    ("ansible", ("ansible", "--version")),
)

_ARGV_BY_NAME: dict[str, tuple[str, ...]] = dict(TOOL_ALLOWLIST)

_FAILURE_DETAILS: dict[RunFailureReason, str] = {
    RunFailureReason.NOT_FOUND: "executable could not be executed (not found)",
    RunFailureReason.PERMISSION_DENIED: "executable could not be executed (permission denied)",
    RunFailureReason.TIMEOUT: "timed out",
    RunFailureReason.INVALID_SPEC: "inspection failed: invalid command specification",
    RunFailureReason.INVALID_WORKING_DIRECTORY: "inspection failed: invalid working directory",
}


def _selected_tools(tool_names: Sequence[str] | None) -> tuple[str, ...]:
    """Deduplicate requested tool names, always in fixed allowlist order."""
    allowlist_order = tuple(name for name, _ in TOOL_ALLOWLIST)
    if not tool_names:
        return allowlist_order
    requested = set(tool_names)
    return tuple(name for name in allowlist_order if name in requested)


def _inspect_tool(
    name: str,
    *,
    timeout_seconds: float,
    max_output_bytes: int,
    which: Callable[[str], str | None],
    run: Callable[[CommandSpec], CommandResult],
) -> ToolInspectionResult:
    executable = which(name)
    if executable is None:
        return ToolInspectionResult(
            name=name,
            executable=None,
            status=CheckStatus.WARN,
            exit_code=None,
            timed_out=False,
            duration_ms=None,
            stdout=None,
            stderr=None,
            stdout_truncated=None,
            stderr_truncated=None,
            detail=f"{name} not found on PATH.",
        )

    fixed_argv = _ARGV_BY_NAME[name]
    argv = (executable, *fixed_argv[1:])
    result = run(
        CommandSpec(argv=argv, timeout_seconds=timeout_seconds, max_output_bytes=max_output_bytes)
    )

    if result.failure_reason is not None:
        detail = f"{name} {_FAILURE_DETAILS[result.failure_reason]}."
        return ToolInspectionResult(
            name=name,
            executable=executable,
            status=CheckStatus.FAIL,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            detail=detail,
        )

    status = CheckStatus.PASS if result.exit_code == 0 else CheckStatus.FAIL
    return ToolInspectionResult(
        name=name,
        executable=executable,
        status=status,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        duration_ms=result.duration_ms,
        stdout=result.stdout,
        stderr=result.stderr,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
        detail=f"{name} executable found at {executable}; exited {result.exit_code}.",
    )


def _compute_overall(results: tuple[ToolInspectionResult, ...]) -> CheckStatus:
    if any(result.status is CheckStatus.FAIL for result in results):
        return CheckStatus.FAIL
    if any(result.status is CheckStatus.WARN for result in results):
        return CheckStatus.WARN
    return CheckStatus.PASS


def build_inspect_report(
    *,
    tool_names: Sequence[str] | None = None,
    version: str,
    timeout_seconds: float,
    max_output_bytes: int,
    config_path: str,
    which: Callable[[str], str | None] | None = None,
    run: Callable[[CommandSpec], CommandResult] | None = None,
) -> ToolsInspectReport:
    """Inspect the selected (or all) allowlisted tools in deterministic order."""
    active_which = which if which is not None else shutil.which
    active_run = run if run is not None else run_command
    selected = _selected_tools(tool_names)
    results = tuple(
        _inspect_tool(
            name,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            which=active_which,
            run=active_run,
        )
        for name in selected
    )
    return ToolsInspectReport(
        version=version,
        configuration=ToolsRunConfiguration(
            path=config_path,
            command_timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        ),
        tools=results,
        overall=_compute_overall(results),
    )
