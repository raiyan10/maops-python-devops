"""Security regressions specific to the Day 4 log modules: no subprocess,
no shell, no eval/exec/pickle, no socket/HTTP, and no raw-line serialization.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"

_LOG_MODULES = (
    "commands/logs.py",
    "core/log_models.py",
    "core/log_reader.py",
    "core/log_parsers.py",
    "core/log_redaction.py",
    "core/log_analysis.py",
)

_FORBIDDEN_TOKENS = (
    "subprocess",
    "os.system(",
    "os.popen(",
    "shell=True",
    "eval(",
    "exec(",
    "pickle",
    "socket",
    "urllib",
    "http.client",
    "mmap",
)


@pytest.mark.parametrize("relative_path", _LOG_MODULES)
def test_module_contains_no_forbidden_tokens(relative_path: str) -> None:
    text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
    for token in _FORBIDDEN_TOKENS:
        # Docstrings legitimately *name* these concepts as things this
        # module deliberately does not do; only fail on tokens appearing
        # in actual code, i.e. outside the module's own docstring block.
        code_only = text.split('"""', 2)[-1] if text.count('"""') >= 2 else text
        assert token not in code_only, f"{relative_path} contains forbidden token {token!r}"


def test_no_third_party_regex_library_used() -> None:
    for relative_path in ("core/log_redaction.py", "core/log_parsers.py", "core/log_analysis.py"):
        text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
        assert "import regex" not in text
        assert "from regex" not in text


def test_build_log_parse_report_never_calls_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.commands.logs import build_log_parse_report
    from maops_pydevops.core.log_models import LogInputFormat

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess invoked")

    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "Popen", _fail)

    path = tmp_path / "a.log"
    path.write_text('{"message": "hi"}\n', encoding="utf-8")
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=4096,
        max_line_bytes=256,
        max_events=10,
        redact=True,
    )
    assert error is None
    assert report is not None


def test_no_raw_line_serialization_in_parse_report(tmp_path: Path) -> None:
    from maops_pydevops.commands.logs import build_log_parse_report
    from maops_pydevops.core.log_models import LogInputFormat

    marker = "UNIQUE_RAW_LINE_MARKER_SHOULD_NOT_APPEAR_WHOLE"
    path = tmp_path / "a.log"
    path.write_text(f"not json {{ {marker} garbage trailing content\n", encoding="utf-8")
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=4096,
        max_line_bytes=256,
        max_events=10,
        redact=True,
    )
    assert report is not None
    for issue in report.issues:
        assert marker not in issue.detail
    assert marker not in report.to_json()


def test_no_raw_line_serialization_for_overlong_lines(tmp_path: Path) -> None:
    from maops_pydevops.commands.logs import build_log_parse_report
    from maops_pydevops.core.log_models import LogInputFormat

    marker = "SECRET_OVERLONG_CONTENT_MARKER"
    path = tmp_path / "a.log"
    path.write_text(marker + "x" * 500 + "\n", encoding="utf-8")
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=100_000,
        max_line_bytes=50,
        max_events=10,
        redact=True,
    )
    assert report is not None
    assert marker not in report.to_json()
    assert report.summary.overlong_lines == 1


def test_no_stdin_reference_in_log_modules() -> None:
    for relative_path in _LOG_MODULES:
        text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
        assert "sys.stdin" not in text


def test_no_glob_expansion_in_log_modules() -> None:
    for relative_path in _LOG_MODULES:
        text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
        assert "glob.glob" not in text
        assert "Path.glob" not in text
        assert ".rglob(" not in text
