"""``build_log_analysis_report`` orchestration: exit semantics, streaming,
signature leakage, and complete JSON schema shape.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from maops_pydevops.commands.logs import build_log_analysis_report
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.models import CheckStatus

_DEFAULTS: dict[str, int] = {
    "max_lines": 10000,
    "max_bytes": 10485760,
    "max_line_bytes": 65536,
    "top": 10,
    "bucket_seconds": 300,
    "repeat_threshold": 5,
    "error_threshold": 1,
}


def _write(path: Path, *lines: str) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_meaningful_warning_report_exits_conceptually_zero(tmp_path: Path) -> None:
    # overall == WARN must still be considered a "meaningful" (exit 0) report.
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "ok", "severity": "error"}), "not json {")
    report, error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.WARN


def test_no_events_non_empty_file_is_fail(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, "not json {", "still not json {")
    report, error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.FAIL


def test_empty_file_is_pass(tmp_path: Path) -> None:
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    report, error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.PASS


def test_blank_only_file_truncated_is_warn(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("\n\n\n\n\n", encoding="utf-8")
    report, error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=3,
        max_bytes=10485760,
        max_line_bytes=65536,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=True,
    )
    assert error is None
    assert report is not None
    assert report.truncated is True
    assert report.overall is CheckStatus.WARN


def test_missing_file_returns_error(tmp_path: Path) -> None:
    report, error = build_log_analysis_report(
        str(tmp_path / "nope.log"), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert report is None
    assert error is not None


def test_complete_json_field_types(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "ok", "severity": "error", "source": "api"}))
    report, _error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert report is not None
    data = report.to_dict()
    assert isinstance(data["severity_counts"], dict)
    assert isinstance(data["source_counts"], list)
    assert isinstance(data["top_signatures"], list)
    assert isinstance(data["time"], dict)
    assert isinstance(data["findings"], list)
    assert isinstance(data["issues"], list)
    assert isinstance(data["line_limit_reached"], bool)
    assert isinstance(data["truncated"], bool)
    parsed = json.loads(report.to_json())
    assert parsed["overall"] in ("pass", "warn", "fail")


def test_explicit_null_fields_when_no_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "no timestamp here"}))
    report, _error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert report is not None
    data = report.to_dict()
    assert data["time"]["first_timestamp"] is None
    assert data["time"]["last_timestamp"] is None
    assert data["time"]["peak_bucket_start"] is None
    assert data["time"]["peak_bucket_count"] == 0


def test_raw_secret_absent_from_analysis_signatures(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "password=hunter2secretvalue login failed"}))
    report, _error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert report is not None
    assert "hunter2secretvalue" not in report.to_json()


def test_no_redact_analysis_shows_secret(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "password=hunter2secretvalue login failed"}))
    report, _error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=False, **_DEFAULTS
    )
    assert report is not None
    assert "hunter2secretvalue" in report.to_json()


def test_overlong_and_blank_lines_counted_in_analysis_summary(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_bytes(json.dumps({"message": "ok"}).encode() + b"\n" + b"\n" + b"x" * 500 + b"\n")
    report, _error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=32,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=True,
    )
    assert report is not None
    assert report.summary.overlong_lines == 1
    assert report.summary.events_parsed == 1
    assert any(f.code.value == "overlong_lines" for f in report.findings)


def test_streaming_no_events_field_on_report() -> None:
    # Checking hasattr() on the class itself is a tautology for a
    # dataclass field with no default -- Python never creates a
    # class-level attribute for it regardless of whether the field
    # exists, so this must instead enumerate the dataclass's own field
    # names.
    from maops_pydevops.core.log_models import LogAnalysisReport

    field_names = {f.name for f in dataclasses.fields(LogAnalysisReport)}
    assert "events" not in field_names


def test_text_output_smoke(tmp_path: Path) -> None:
    from maops_pydevops.core.output import render_logs_analyze_text

    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "ok", "severity": "warning"}))
    report, _error = build_log_analysis_report(
        str(path), input_format=LogInputFormat.JSONL, redact=True, **_DEFAULTS
    )
    assert report is not None
    text = render_logs_analyze_text(report)
    assert "\x1b[" not in text
    assert "Overall status:" in text
