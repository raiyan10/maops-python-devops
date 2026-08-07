"""``auto`` format detection: per-line, deterministic, never silently
falls back from a malformed JSON-looking line to syslog parsing.
"""

from __future__ import annotations

import json

from maops_pydevops.core.log_models import LogInputFormat, LogParseIssueCode
from maops_pydevops.core.log_parsers import parse_auto_line


def test_jsonl_detection() -> None:
    line = json.dumps({"message": "hello"})
    event, issue = parse_auto_line(line, 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.input_format is LogInputFormat.JSONL


def test_syslog_detection() -> None:
    line = "2026-08-06T10:30:00Z host app[1]: hello"
    event, issue = parse_auto_line(line, 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.input_format is LogInputFormat.SYSLOG


def test_mixed_input_in_one_stream() -> None:
    lines = [
        json.dumps({"message": "jsonl one"}),
        "2026-08-06T10:30:00Z host app[1]: syslog one",
        json.dumps({"message": "jsonl two"}),
    ]
    formats = []
    for i, line in enumerate(lines, start=1):
        event, issue = parse_auto_line(line, i, redact=True)
        assert issue is None
        assert event is not None
        formats.append(event.input_format)
    assert formats == [LogInputFormat.JSONL, LogInputFormat.SYSLOG, LogInputFormat.JSONL]


def test_malformed_json_looking_line_does_not_fall_back_to_syslog() -> None:
    line = "{this looks like json but is not valid"
    event, issue = parse_auto_line(line, 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_leading_whitespace_before_brace_still_detected_as_jsonl() -> None:
    line = '   {"message": "indented"}'
    event, issue = parse_auto_line(line, 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.input_format is LogInputFormat.JSONL


def test_deterministic_detected_format_field() -> None:
    line = json.dumps({"message": "hello"})
    first_event, _ = parse_auto_line(line, 1, redact=True)
    second_event, _ = parse_auto_line(line, 1, redact=True)
    assert first_event is not None
    assert second_event is not None
    assert first_event.input_format == second_event.input_format == LogInputFormat.JSONL
