"""run_command() truncates captured output byte-exactly and flags truncation."""

import sys

from maops_pydevops.core.runner import CommandSpec, run_command


def test_stdout_under_limit_is_not_truncated() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.write('a' * 10)"),
        timeout_seconds=5.0,
        max_output_bytes=100,
    )
    result = run_command(spec)
    assert result.stdout_truncated is False
    assert result.stdout == "a" * 10


def test_stdout_over_limit_is_truncated_to_exact_byte_count() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.write('a' * 100)"),
        timeout_seconds=5.0,
        max_output_bytes=10,
    )
    result = run_command(spec)
    assert result.stdout_truncated is True
    assert result.stdout == "a" * 10


def test_stderr_truncation_independent_of_stdout() -> None:
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('a' * 5); sys.stderr.write('b' * 100)",
        ),
        timeout_seconds=5.0,
        max_output_bytes=10,
    )
    result = run_command(spec)
    assert result.stdout_truncated is False
    assert result.stderr_truncated is True
    assert result.stdout == "a" * 5
    assert result.stderr == "b" * 10


def test_truncation_at_exact_boundary_is_not_flagged() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.write('a' * 10)"),
        timeout_seconds=5.0,
        max_output_bytes=10,
    )
    result = run_command(spec)
    assert result.stdout_truncated is False


def test_truncation_at_mid_multibyte_utf8_sequence_is_deterministic() -> None:
    # U+00E9 ('e' + combining or precomposed) encodes as two bytes in UTF-8 (0xC3 0xA9).
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.buffer.write('é'.encode('utf-8'))"),
        timeout_seconds=5.0,
        max_output_bytes=1,
    )
    result = run_command(spec)
    assert result.stdout_truncated is True
    assert result.stdout == "�"
