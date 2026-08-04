"""run_command() distinctly identifies not-found, permission-denied, and timeout failures."""

import os
import sys
from pathlib import Path

import pytest

from maops_pydevops.core.runner import CommandSpec, RunFailureReason, run_command


def test_command_not_found(tmp_path: Path) -> None:
    spec = CommandSpec(
        argv=(str(tmp_path / "does-not-exist-binary"),),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.NOT_FOUND
    assert result.exit_code is None


@pytest.mark.skipif(
    hasattr(os, "getuid") and os.getuid() == 0, reason="root bypasses executable permission bits"
)
def test_permission_denied(tmp_path: Path) -> None:
    non_executable = tmp_path / "not-executable"
    non_executable.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    non_executable.chmod(0o644)
    spec = CommandSpec(argv=(str(non_executable),), timeout_seconds=5.0, max_output_bytes=65536)
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.PERMISSION_DENIED
    assert result.exit_code is None


def test_timeout_reports_distinct_failure_and_partial_output() -> None:
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import sys, time; sys.stdout.write('partial'); sys.stdout.flush(); time.sleep(10)",
        ),
        timeout_seconds=0.5,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.TIMEOUT
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.duration_ms >= 0


def test_timeout_duration_is_meaningful() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import time; time.sleep(10)"),
        timeout_seconds=0.3,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.timed_out is True
    assert result.duration_ms >= 200
