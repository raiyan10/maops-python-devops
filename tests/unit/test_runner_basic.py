"""run_command() executes a fixed argv with shell=False and preserves the exit code."""

import sys
from pathlib import Path

from maops_pydevops.core.runner import CommandSpec, RunFailureReason, run_command


def test_exit_code_preserved_on_success() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.exit(0)"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.exit_code == 0
    assert result.failure_reason is None
    assert result.timed_out is False


def test_nonzero_exit_code_preserved() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.exit(7)"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.exit_code == 7
    assert result.failure_reason is None


def test_stdout_and_stderr_captured_separately() -> None:
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('out-line'); sys.stderr.write('err-line')",
        ),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.stdout == "out-line"
    assert result.stderr == "err-line"


def test_stdin_is_devnull_child_never_blocks() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; data = sys.stdin.read(); print(repr(data))"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.exit_code == 0
    assert result.stdout.strip() == "''"


def test_empty_argv_is_rejected() -> None:
    spec = CommandSpec(argv=(), timeout_seconds=5.0, max_output_bytes=65536)
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.INVALID_SPEC
    assert result.exit_code is None


def test_nul_character_in_argv_is_rejected() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "pass\0malicious"), timeout_seconds=5.0, max_output_bytes=65536
    )
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.INVALID_SPEC


def test_duration_is_nonnegative() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "pass"), timeout_seconds=5.0, max_output_bytes=65536
    )
    result = run_command(spec)
    assert result.duration_ms >= 0


def test_working_directory_is_honored(tmp_path: Path) -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import os; print(os.getcwd())"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
        working_directory=tmp_path,
    )
    result = run_command(spec)
    assert result.stdout.strip() == str(tmp_path.resolve())


def test_missing_working_directory_is_rejected(tmp_path: Path) -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "pass"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
        working_directory=tmp_path / "does-not-exist",
    )
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.INVALID_WORKING_DIRECTORY


def test_working_directory_must_be_a_directory_not_a_file(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("x", encoding="utf-8")
    spec = CommandSpec(
        argv=(sys.executable, "-c", "pass"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
        working_directory=file_path,
    )
    result = run_command(spec)
    assert result.failure_reason is RunFailureReason.INVALID_WORKING_DIRECTORY


def test_utf8_output_decoded_with_replacement_for_invalid_bytes() -> None:
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'valid-\\xff-bytes')",
        ),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert "�" in result.stdout
    assert result.stdout.startswith("valid-")
