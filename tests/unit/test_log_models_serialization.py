"""Explicit serialization and immutability of log models -- no
``dataclasses.asdict``, no dict-spreading, frozen dataclasses throughout.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from maops_pydevops.core.log_models import (
    LogAnalysisFinding,
    LogAnalysisFindingCode,
    LogAnalysisOptions,
    LogAnalysisReport,
    LogAnalysisSummary,
    LogAnalysisTime,
    LogEvent,
    LogInputFormat,
    LogParseIssue,
    LogParseIssueCode,
    LogParseOptions,
    LogParseReport,
    LogParseSummary,
    LogSeverity,
    SignatureEntry,
    SourceCount,
    normalize_severity,
)
from maops_pydevops.core.models import CheckStatus


def _sample_event() -> LogEvent:
    return LogEvent(
        line_number=1,
        input_format=LogInputFormat.JSONL,
        timestamp="2026-08-06T04:30:00+00:00",
        timestamp_raw="2026-08-06T10:30:00+06:00",
        hostname="app01",
        source="api",
        pid=123,
        severity=LogSeverity.ERROR,
        message="database connection failed",
        redacted=False,
    )


def test_log_event_is_frozen() -> None:
    event = _sample_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.line_number = 2  # type: ignore[misc]


def test_log_event_to_dict_field_types() -> None:
    event = _sample_event()
    data = event.to_dict()
    assert isinstance(data["line_number"], int)
    assert isinstance(data["input_format"], str)
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["hostname"], str)
    assert isinstance(data["pid"], int)
    assert isinstance(data["severity"], str)
    assert isinstance(data["message"], str)
    assert isinstance(data["redacted"], bool)


def test_log_event_explicit_nulls() -> None:
    event = LogEvent(
        line_number=1,
        input_format=LogInputFormat.SYSLOG,
        timestamp=None,
        timestamp_raw=None,
        hostname=None,
        source=None,
        pid=None,
        severity=LogSeverity.UNKNOWN,
        message="m",
        redacted=False,
    )
    data = event.to_dict()
    assert data["timestamp"] is None
    assert data["timestamp_raw"] is None
    assert data["hostname"] is None
    assert data["source"] is None
    assert data["pid"] is None


def test_log_parse_issue_to_dict() -> None:
    issue = LogParseIssue(4, LogParseIssueCode.MALFORMED_JSON, CheckStatus.WARN, "detail text")
    assert issue.to_dict() == {
        "line_number": 4,
        "code": "malformed_json",
        "status": "warn",
        "detail": "detail text",
    }


def test_log_parse_report_to_json_is_valid_json() -> None:
    report = LogParseReport(
        version="0.4.0",
        path="/tmp/test.log",
        options=LogParseOptions(
            input_format=LogInputFormat.AUTO,
            max_lines=10000,
            max_bytes=10485760,
            max_line_bytes=65536,
            max_events=1000,
            redact=True,
        ),
        summary=LogParseSummary(
            bytes_read=10,
            lines_read=1,
            blank_lines=0,
            events_parsed=1,
            events_emitted=1,
            malformed_lines=0,
            overlong_lines=0,
        ),
        events=(_sample_event(),),
        issues=(),
        line_limit_reached=False,
        byte_limit_reached=False,
        truncated=False,
        overall=CheckStatus.PASS,
    )
    parsed = json.loads(report.to_json())
    assert parsed["version"] == "0.4.0"
    assert parsed["overall"] == "pass"
    assert len(parsed["events"]) == 1
    assert parsed["events"][0]["message"] == "database connection failed"


def test_no_ansi_in_json_output() -> None:
    report = LogParseReport(
        version="0.4.0",
        path="/tmp/test.log",
        options=LogParseOptions(
            input_format=LogInputFormat.AUTO,
            max_lines=1,
            max_bytes=1,
            max_line_bytes=1,
            max_events=1,
            redact=True,
        ),
        summary=LogParseSummary(0, 0, 0, 0, 0, 0, 0),
        events=(),
        issues=(),
        line_limit_reached=False,
        byte_limit_reached=False,
        truncated=False,
        overall=CheckStatus.PASS,
    )
    assert "\x1b[" not in report.to_json()


def test_signature_entry_severity_counts_dict_shape() -> None:
    entry = SignatureEntry(
        signature="connection failed for host <ip>",
        count=5,
        first_line=2,
        last_line=15,
        severity_counts=((LogSeverity.ERROR, 5),),
    )
    assert entry.to_dict()["severity_counts"] == {"error": 5}


def test_source_count_to_dict() -> None:
    assert SourceCount(source="api", count=12).to_dict() == {"source": "api", "count": 12}


def test_log_analysis_finding_to_dict() -> None:
    finding = LogAnalysisFinding(LogAnalysisFindingCode.ERROR_VOLUME, CheckStatus.WARN, "detail")
    assert finding.to_dict() == {"code": "error_volume", "status": "warn", "detail": "detail"}


def test_log_analysis_report_field_order_matches_schema() -> None:
    report = LogAnalysisReport(
        version="0.4.0",
        path="/tmp/a.log",
        options=LogAnalysisOptions(
            input_format=LogInputFormat.AUTO,
            max_lines=1,
            max_bytes=1,
            max_line_bytes=1,
            top=10,
            bucket_seconds=300,
            repeat_threshold=5,
            error_threshold=1,
            redact=True,
        ),
        summary=LogAnalysisSummary(0, 0, 0, 0, 0),
        severity_counts=tuple((s, 0) for s in LogSeverity),
        source_counts=(),
        top_signatures=(),
        time=LogAnalysisTime(0, None, None, 0, 300, None, 0),
        findings=(),
        issues=(),
        line_limit_reached=False,
        byte_limit_reached=False,
        truncated=False,
        overall=CheckStatus.PASS,
    )
    keys = list(report.to_dict().keys())
    assert keys == [
        "version",
        "path",
        "options",
        "summary",
        "severity_counts",
        "source_counts",
        "top_signatures",
        "time",
        "findings",
        "issues",
        "line_limit_reached",
        "byte_limit_reached",
        "truncated",
        "overall",
    ]


def test_severity_counts_include_all_ten_canonical_severities() -> None:
    report_severities = {s.value for s in LogSeverity}
    assert report_severities == {
        "trace",
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
        "unknown",
    }


def test_normalize_severity_unknown_string_becomes_unknown() -> None:
    assert normalize_severity("totally-not-a-severity") is LogSeverity.UNKNOWN


def test_no_dataclasses_asdict_used_in_module_source() -> None:
    import pathlib

    import maops_pydevops.core.log_models as log_models_module

    source = pathlib.Path(log_models_module.__file__).read_text(encoding="utf-8")
    assert "asdict" not in source
