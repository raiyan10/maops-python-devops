"""JSONL line parsing: alias precedence, type validation, timestamps, severities."""

from __future__ import annotations

import json

from maops_pydevops.core.log_models import LogInputFormat, LogParseIssueCode, LogSeverity
from maops_pydevops.core.log_parsers import parse_jsonl_line


def test_complete_valid_event() -> None:
    payload = {
        "timestamp": "2026-08-06T10:30:00+06:00",
        "severity": "error",
        "hostname": "app01",
        "source": "api",
        "pid": 123,
        "message": "database connection failed",
    }
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.line_number == 1
    assert event.input_format is LogInputFormat.JSONL
    assert event.timestamp == "2026-08-06T04:30:00+00:00"
    assert event.timestamp_raw == "2026-08-06T10:30:00+06:00"
    assert event.hostname == "app01"
    assert event.source == "api"
    assert event.pid == 123
    assert event.severity is LogSeverity.ERROR
    assert event.message == "database connection failed"
    assert event.redacted is False


def test_alias_precedence_timestamp() -> None:
    payload = {"timestamp": "2026-01-01T00:00:00Z", "time": "wrong", "message": "m"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.timestamp_raw == "2026-01-01T00:00:00Z"


def test_alias_precedence_severity() -> None:
    payload = {"severity": "error", "level": "warning", "message": "m"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.severity is LogSeverity.ERROR


def test_alias_precedence_hostname() -> None:
    payload = {"hostname": "h1", "host": "h2", "message": "m"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.hostname == "h1"


def test_alias_precedence_source() -> None:
    payload = {"service": "svc", "app": "myapp", "message": "m"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.source == "svc"


def test_alias_precedence_message() -> None:
    payload = {"msg": "from msg", "event": "from event"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.message == "from msg"


def test_alias_precedence_pid() -> None:
    payload = {"pid": 1, "process_id": 2, "message": "m"}
    event, _issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.pid == 1


def test_minimum_message_only_event() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "just a message"}), 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.message == "just a message"
    assert event.severity is LogSeverity.UNKNOWN
    assert event.timestamp is None
    assert event.hostname is None
    assert event.source is None
    assert event.pid is None


def test_invalid_json_becomes_issue() -> None:
    event, issue = parse_jsonl_line("{not valid json", 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_deeply_nested_json_does_not_raise_recursion_error() -> None:
    # A 60,000-byte deeply-nested array is well inside the default
    # --max-line-bytes (65536) budget; json.loads's recursive-descent
    # parser hits CPython's default recursion limit long before that.
    event, issue = parse_jsonl_line("[" * 60000, 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_oversized_integer_literal_does_not_raise_value_error() -> None:
    # json.loads must tokenize the whole document before this module's
    # field-level code ever runs, so an oversized integer anywhere in
    # the object -- including a field this package never reads --
    # crashes json.loads itself (CPython 3.11+'s integer-string-
    # conversion digit limit), not just the `pid` field specifically.
    payload = '{"message":"x","trace_id":' + "9" * 5000 + "}"
    event, issue = parse_jsonl_line(payload, 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_oversized_pid_integer_literal_does_not_raise_value_error() -> None:
    payload = '{"message":"m","pid":' + "9" * 5000 + "}"
    event, issue = parse_jsonl_line(payload, 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_rfc3339_timestamp_overflowing_utc_conversion_does_not_raise() -> None:
    # Syntactically valid per RFC3339, but astimezone(UTC) overflows
    # datetime's representable range for a far-future year with a large
    # negative offset.
    payload = json.dumps({"message": "edge", "timestamp": "9999-12-31T23:59:59-14:00"})
    event, issue = parse_jsonl_line(payload, 1, redact=True)
    assert event is not None
    assert event.timestamp is None
    assert event.timestamp_raw == "9999-12-31T23:59:59-14:00"
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_TIMESTAMP


def test_non_object_json_rejected() -> None:
    for candidate in ("[1, 2, 3]", '"just a string"', "42", "true", "false", "null"):
        event, issue = parse_jsonl_line(candidate, 1, redact=True)
        assert event is None, candidate
        assert issue is not None
        assert issue.code is LogParseIssueCode.MALFORMED_JSON


def test_missing_message_becomes_issue() -> None:
    event, issue = parse_jsonl_line(json.dumps({"severity": "info"}), 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_non_string_message_becomes_issue() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": 123}), 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_non_string_timestamp_becomes_issue_but_event_still_emitted() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "timestamp": 123}), 1, redact=True)
    assert event is not None
    assert event.timestamp is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_non_string_severity_becomes_issue_but_event_still_emitted() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "severity": 5}), 1, redact=True)
    assert event is not None
    assert event.severity is LogSeverity.UNKNOWN
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_invalid_pid_type_becomes_issue() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "pid": "abc"}), 1, redact=True)
    assert event is not None
    assert event.pid is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_negative_pid_rejected() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "pid": -1}), 1, redact=True)
    assert event is not None
    assert event.pid is None
    assert issue is not None


def test_bool_pid_rejected() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "pid": True}), 1, redact=True)
    assert event is not None
    assert event.pid is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_extra_fields_ignored_and_never_serialized() -> None:
    payload = {"message": "m", "unexpected_field": "should not appear", "another": 42}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert issue is None
    assert event is not None
    serialized = json.dumps(event.to_dict())
    assert "unexpected_field" not in serialized
    assert "another" not in serialized


def test_unknown_severity_string_becomes_unknown_not_a_failure() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "severity": "weird"}), 1, redact=True
    )
    assert issue is None
    assert event is not None
    assert event.severity is LogSeverity.UNKNOWN


def test_severity_aliases() -> None:
    aliases = {
        "warn": LogSeverity.WARNING,
        "err": LogSeverity.ERROR,
        "crit": LogSeverity.CRITICAL,
        "fatal": LogSeverity.CRITICAL,
        "emerg": LogSeverity.EMERGENCY,
        "information": LogSeverity.INFO,
    }
    for alias, expected in aliases.items():
        event, _issue = parse_jsonl_line(
            json.dumps({"message": "m", "severity": alias}), 1, redact=True
        )
        assert event is not None
        assert event.severity is expected, alias


def test_valid_aware_timestamp() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "timestamp": "2026-01-01T12:00:00+02:00"}), 1, redact=True
    )
    assert issue is None
    assert event is not None
    assert event.timestamp == "2026-01-01T10:00:00+00:00"


def test_trailing_z_timestamp() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "timestamp": "2026-01-01T12:00:00Z"}), 1, redact=True
    )
    assert issue is None
    assert event is not None
    assert event.timestamp == "2026-01-01T12:00:00+00:00"


def test_naive_timestamp_stays_null_without_issue() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "timestamp": "2026-01-01T12:00:00"}), 1, redact=True
    )
    assert issue is None
    assert event is not None
    assert event.timestamp is None
    assert event.timestamp_raw == "2026-01-01T12:00:00"


def test_invalid_timestamp_string_becomes_issue() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "timestamp": "not-a-timestamp"}), 1, redact=True
    )
    assert event is not None
    assert event.timestamp is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_TIMESTAMP


def test_non_string_hostname_becomes_issue_but_event_still_emitted() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "hostname": 123}), 1, redact=True)
    assert event is not None
    assert event.hostname is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_non_string_source_becomes_issue_but_event_still_emitted() -> None:
    event, issue = parse_jsonl_line(json.dumps({"message": "m", "source": [1, 2]}), 1, redact=True)
    assert event is not None
    assert event.source is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_non_string_timestamp_value_is_json_stringified_in_raw() -> None:
    event, issue = parse_jsonl_line(
        json.dumps({"message": "m", "timestamp": 12345}), 1, redact=True
    )
    assert event is not None
    assert event.timestamp is None
    assert event.timestamp_raw == "12345"
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_only_first_issue_kept_when_multiple_fields_invalid() -> None:
    # Fixed priority order: severity issue is checked before hostname,
    # so only one issue is ever returned per line.
    payload = {"message": "m", "severity": 1, "hostname": 2}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert issue is not None
    assert issue.detail == "severity field is not a string"


def test_only_first_issue_kept_hostname_before_source() -> None:
    payload = {"message": "m", "hostname": 1, "source": [1]}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert issue is not None
    assert issue.detail == "hostname field is not a string"


def test_only_first_issue_kept_source_before_pid() -> None:
    payload = {"message": "m", "source": [1], "pid": "abc"}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert issue is not None
    assert issue.detail == "source field is not a string"


def test_only_first_issue_kept_pid_before_timestamp() -> None:
    payload = {"message": "m", "pid": "abc", "timestamp": "not-a-timestamp"}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert issue is not None
    assert issue.detail == "pid field is not a non-negative integer"


def test_only_first_issue_kept_pid_before_non_string_timestamp() -> None:
    # A non-string timestamp value takes a different code branch than an
    # invalid-but-string timestamp -- exercise it too so the "issue
    # already set" guard is covered for both timestamp branches.
    payload = {"message": "m", "pid": "abc", "timestamp": 12345}
    event, issue = parse_jsonl_line(json.dumps(payload), 1, redact=True)
    assert event is not None
    assert event.timestamp_raw == "12345"
    assert issue is not None
    assert issue.detail == "pid field is not a non-negative integer"


def test_no_arbitrary_field_serialization_only_documented_fields() -> None:
    event, _issue = parse_jsonl_line(json.dumps({"message": "m"}), 1, redact=True)
    assert event is not None
    expected_keys = {
        "line_number",
        "input_format",
        "timestamp",
        "timestamp_raw",
        "hostname",
        "source",
        "pid",
        "severity",
        "message",
        "redacted",
    }
    assert set(event.to_dict().keys()) == expected_keys
