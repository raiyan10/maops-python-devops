"""Syslog line parsing: PRI severities, timestamps, hostname/source/pid, malformed lines."""

from __future__ import annotations

from maops_pydevops.core.log_models import LogInputFormat, LogParseIssueCode, LogSeverity
from maops_pydevops.core.log_parsers import parse_syslog_line

_PRI_SEVERITIES: dict[int, LogSeverity] = {
    0: LogSeverity.EMERGENCY,
    1: LogSeverity.ALERT,
    2: LogSeverity.CRITICAL,
    3: LogSeverity.ERROR,
    4: LogSeverity.WARNING,
    5: LogSeverity.NOTICE,
    6: LogSeverity.INFO,
    7: LogSeverity.DEBUG,
}


def test_pri_with_each_severity() -> None:
    for pri, expected in _PRI_SEVERITIES.items():
        line = f"<{pri}>2026-08-06T10:30:00Z app01 myapp[1]: message body"
        event, issue = parse_syslog_line(line, 1, redact=True)
        assert issue is None, pri
        assert event is not None
        assert event.severity is expected, pri


def test_no_pri_gives_unknown_severity() -> None:
    line = "2026-08-06T10:30:00Z app01 myapp[1]: message body"
    event, issue = parse_syslog_line(line, 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.severity is LogSeverity.UNKNOWN


def test_pri_out_of_range_is_malformed() -> None:
    line = "<192>2026-08-06T10:30:00Z app01 myapp[1]: message body"
    event, issue = parse_syslog_line(line, 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_LINE


def test_rfc3339_timestamp() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00+02:00 app01 myapp[1]: m", 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.timestamp == "2026-08-06T08:30:00+00:00"
    assert event.timestamp_raw == "2026-08-06T10:30:00+02:00"


def test_trailing_z_timestamp() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00Z app01 myapp[1]: m", 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.timestamp == "2026-08-06T10:30:00+00:00"


def test_bsd_timestamp_has_no_year_and_stays_null() -> None:
    event, issue = parse_syslog_line("Aug  6 10:30:00 app01 myapp[1]: m", 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.timestamp is None
    assert event.timestamp_raw == "Aug  6 10:30:00"
    assert event.input_format is LogInputFormat.SYSLOG


def test_hostname_extracted() -> None:
    event, _issue = parse_syslog_line("2026-08-06T10:30:00Z myhost myapp[1]: m", 1, redact=True)
    assert event is not None
    assert event.hostname == "myhost"


def test_source_extracted() -> None:
    event, _issue = parse_syslog_line("2026-08-06T10:30:00Z host mysvc[1]: m", 1, redact=True)
    assert event is not None
    assert event.source == "mysvc"


def test_source_with_pid() -> None:
    event, _issue = parse_syslog_line("2026-08-06T10:30:00Z host mysvc[4242]: m", 1, redact=True)
    assert event is not None
    assert event.source == "mysvc"
    assert event.pid == 4242


def test_missing_pid_is_none() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00Z host mysvc: m", 1, redact=True)
    assert issue is None
    assert event is not None
    assert event.pid is None


def test_invalid_non_numeric_pid_is_malformed() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00Z host mysvc[abc]: m", 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_LINE


def test_oversized_pid_digit_run_does_not_raise_value_error() -> None:
    # The `[pid]` capture group is an unbounded `\d+`; a digit run past
    # CPython 3.11+'s integer-string-conversion limit must degrade the
    # field rather than crash the whole parse.
    line = "2026-08-06T10:30:00Z host mysvc[" + "9" * 5000 + "]: m"
    event, issue = parse_syslog_line(line, 1, redact=True)
    assert event is not None
    assert event.pid is None
    assert event.source == "mysvc"
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_FIELD_TYPE


def test_malformed_line_no_timestamp() -> None:
    event, issue = parse_syslog_line("this is not syslog at all", 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_LINE


def test_malformed_line_missing_source_separator() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00Z host", 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_LINE


def test_message_containing_colons_only_first_header_colon_splits() -> None:
    event, issue = parse_syslog_line(
        "2026-08-06T10:30:00Z host app[1]: error: nested: message: here", 1, redact=True
    )
    assert issue is None
    assert event is not None
    assert event.message == "error: nested: message: here"


def test_deterministic_parsing_same_input_same_output() -> None:
    line = "<11>2026-08-06T10:30:00Z host app[1]: repeatable message"
    first_event, first_issue = parse_syslog_line(line, 1, redact=True)
    second_event, second_issue = parse_syslog_line(line, 1, redact=True)
    assert first_event == second_event
    assert first_issue == second_issue


def test_bsd_timestamp_never_infers_a_year() -> None:
    event, _issue = parse_syslog_line("Jan  1 00:00:00 host app[1]: m", 1, redact=True)
    assert event is not None
    assert event.timestamp is None
    assert "2026" not in (event.timestamp_raw or "")


def test_missing_hostname_is_malformed() -> None:
    event, issue = parse_syslog_line("2026-08-06T10:30:00Z ", 1, redact=True)
    assert event is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.MALFORMED_LINE
    assert issue.detail == "missing hostname"


def test_syntactically_valid_but_semantically_invalid_timestamp_becomes_issue() -> None:
    # The RFC3339 regex matches the shape (digits in the right places)
    # even though month=13/day=45/hour=99 are not real calendar values --
    # fromisoformat() rejects it, producing an INVALID_TIMESTAMP issue
    # while the event is still emitted with timestamp=None.
    event, issue = parse_syslog_line("2026-13-45T99:99:99Z host app[1]: m", 1, redact=True)
    assert event is not None
    assert event.timestamp is None
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_TIMESTAMP


def test_rfc3339_timestamp_overflowing_utc_conversion_does_not_raise() -> None:
    # Shares _normalize_timestamp() with the JSONL parser: a far-future
    # year with a large negative offset overflows datetime's range on
    # astimezone(UTC), which is an OverflowError, not a ValueError.
    line = "9999-12-31T23:59:59-14:00 host app[1]: edge"
    event, issue = parse_syslog_line(line, 1, redact=True)
    assert event is not None
    assert event.timestamp is None
    assert event.timestamp_raw == "9999-12-31T23:59:59-14:00"
    assert issue is not None
    assert issue.code is LogParseIssueCode.INVALID_TIMESTAMP


def test_redaction_applied_to_syslog_message() -> None:
    event, _issue = parse_syslog_line(
        "2026-08-06T10:30:00Z host app[1]: password=hunter2 login failed", 1, redact=True
    )
    assert event is not None
    assert "hunter2" not in event.message
    assert event.redacted is True


def test_redaction_disabled_syslog_message() -> None:
    event, _issue = parse_syslog_line(
        "2026-08-06T10:30:00Z host app[1]: password=hunter2 login failed", 1, redact=False
    )
    assert event is not None
    assert "hunter2" in event.message
    assert event.redacted is False
