"""A reusable, safe subprocess execution layer.

The only module in ``src/maops_pydevops`` permitted to import
``subprocess``. Never invokes a shell, never logs or prints, and never
exposes an arbitrary command-execution surface -- callers must supply a
fixed, pre-validated ``argv``.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_CHILD_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "LANG": "C",
    "NO_COLOR": "1",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "TERM": "dumb",
    # Terraform's CLI performs an outbound "checkpoint" network call on
    # `terraform version` unless this is set -- required to keep the fixed
    # allowlisted tool checks genuinely network-free.
    "CHECKPOINT_DISABLE": "1",
}


class RunFailureReason(StrEnum):
    """Why a command did not produce a normal exit code."""

    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    INVALID_SPEC = "invalid_spec"
    INVALID_WORKING_DIRECTORY = "invalid_working_directory"


@dataclass(frozen=True)
class CommandSpec:
    """A fixed, pre-validated command to execute."""

    argv: tuple[str, ...]
    timeout_seconds: float
    max_output_bytes: int
    working_directory: Path | None = None


@dataclass(frozen=True)
class CommandResult:
    """The outcome of executing a :class:`CommandSpec`."""

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    duration_ms: int
    timed_out: bool
    failure_reason: RunFailureReason | None


def _truncate(raw: bytes, max_output_bytes: int) -> tuple[str, bool]:
    truncated = len(raw) > max_output_bytes
    return raw[:max_output_bytes].decode("utf-8", errors="replace"), truncated


def _invalid_result(
    argv: tuple[str, ...], failure_reason: RunFailureReason, duration_ms: int = 0
) -> CommandResult:
    return CommandResult(
        argv=argv,
        exit_code=None,
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_ms=duration_ms,
        timed_out=False,
        failure_reason=failure_reason,
    )


def run_command(spec: CommandSpec) -> CommandResult:
    """Execute ``spec`` with ``shell=False`` and a fixed, noninteractive child env."""
    if not spec.argv or any("\0" in arg for arg in spec.argv):
        return _invalid_result(spec.argv, RunFailureReason.INVALID_SPEC)

    if spec.working_directory is not None and not spec.working_directory.is_dir():
        return _invalid_result(spec.argv, RunFailureReason.INVALID_WORKING_DIRECTORY)

    child_env = dict(os.environ)
    child_env.update(_CHILD_ENV_OVERRIDES)

    start = time.monotonic()
    try:
        completed = subprocess.run(
            list(spec.argv),
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            cwd=str(spec.working_directory) if spec.working_directory is not None else None,
            env=child_env,
            timeout=spec.timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        duration_ms = round((time.monotonic() - start) * 1000)
        return _invalid_result(spec.argv, RunFailureReason.NOT_FOUND, duration_ms)
    except PermissionError:
        duration_ms = round((time.monotonic() - start) * 1000)
        return _invalid_result(spec.argv, RunFailureReason.PERMISSION_DENIED, duration_ms)
    except subprocess.TimeoutExpired as exc:
        duration_ms = round((time.monotonic() - start) * 1000)
        raw_stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        raw_stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
        stdout, stdout_truncated = _truncate(raw_stdout, spec.max_output_bytes)
        stderr, stderr_truncated = _truncate(raw_stderr, spec.max_output_bytes)
        return CommandResult(
            argv=spec.argv,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            duration_ms=duration_ms,
            timed_out=True,
            failure_reason=RunFailureReason.TIMEOUT,
        )

    duration_ms = round((time.monotonic() - start) * 1000)
    stdout, stdout_truncated = _truncate(completed.stdout, spec.max_output_bytes)
    stderr, stderr_truncated = _truncate(completed.stderr, spec.max_output_bytes)
    return CommandResult(
        argv=spec.argv,
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        duration_ms=duration_ms,
        timed_out=False,
        failure_reason=None,
    )
