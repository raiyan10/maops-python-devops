"""Log modules never read named environment variables.

``core/config.py`` is the sole module permitted to do so. ``--format``
resolution for ``logs parse``/``logs analyze`` still goes through
``resolve_effective_config()`` at the CLI boundary, but none of the
``log_*``/``commands/logs.py`` modules touch ``os.environ`` directly.
"""

from __future__ import annotations

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


@pytest.mark.parametrize("relative_path", _LOG_MODULES)
def test_module_never_references_os_environ_or_getenv(relative_path: str) -> None:
    text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
    assert "os.environ" not in text
    assert "os.getenv" not in text


def test_build_log_parse_report_ignores_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_OUTPUT_FORMAT", raising=False)
    from maops_pydevops.commands.logs import build_log_parse_report
    from maops_pydevops.core.log_models import LogInputFormat

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


def test_build_log_analysis_report_ignores_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_OUTPUT_FORMAT", raising=False)
    from maops_pydevops.commands.logs import build_log_analysis_report
    from maops_pydevops.core.log_models import LogInputFormat

    path = tmp_path / "a.log"
    path.write_text('{"message": "hi"}\n', encoding="utf-8")
    report, error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=4096,
        max_line_bytes=256,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=True,
    )
    assert error is None
    assert report is not None
