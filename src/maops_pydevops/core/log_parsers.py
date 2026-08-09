"""Per-line JSONL, syslog, and auto-detected log parsing.

None of the functions in this module ever raise on malformed input --
every JSON, regex, or timestamp failure is caught narrowly and converted
into a structured :class:`~maops_pydevops.core.log_models.LogParseIssue`
instead. Detection in ``auto`` mode is per-line, not sticky across a
file, so a file mixing JSONL and syslog lines degrades gracefully rather
than committing to one guess from an early line.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from maops_pydevops.core.log_models import (
    LogEvent,
    LogInputFormat,
    LogParseIssue,
    LogParseIssueCode,
    LogSeverity,
    normalize_severity,
)
from maops_pydevops.core.log_redaction import redact_message
from maops_pydevops.core.models import CheckStatus

_TIMESTAMP_KEYS: tuple[str, ...] = ("timestamp", "time", "ts")
_SEVERITY_KEYS: tuple[str, ...] = ("severity", "level", "log_level")
_HOSTNAME_KEYS: tuple[str, ...] = ("hostname", "host")
_SOURCE_KEYS: tuple[str, ...] = ("source", "service", "app", "logger")
_MESSAGE_KEYS: tuple[str, ...] = ("message", "msg", "event")
_PID_KEYS: tuple[str, ...] = ("pid", "process_id")

_PRI_RE = re.compile(r"^<(\d{1,3})>")
_RFC3339_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:?\d{2}))(?=\s|$)"
)

#: RFC 3339 sec. 5.6 permits a lowercase trailing ``z`` (and lowercase
#: ``t`` date/time separator, already handled above) as equivalent to
#: uppercase -- both normalize to the same UTC offset representation.
_MAX_PID = 2_147_483_647
_BSD_TS_RE = re.compile(r"^([A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})(?=\s|$)")
_HEADER_TAIL_RE = re.compile(r"^(?P<source>[^\s\[:]+)(?:\[(?P<pid>\d+)\])?:\s?(?P<message>.*)$")

#: RFC 5424 severity == PRI % 8, facility ignored (Day 4 does not model
#: facilities). Index 0 is severity 0 (emergency) through index 7 (debug).
_PRI_SEVERITY_BY_MOD8: tuple[LogSeverity, ...] = (
    LogSeverity.EMERGENCY,
    LogSeverity.ALERT,
    LogSeverity.CRITICAL,
    LogSeverity.ERROR,
    LogSeverity.WARNING,
    LogSeverity.NOTICE,
    LogSeverity.INFO,
    LogSeverity.DEBUG,
)


def _normalize_timestamp(raw: str) -> tuple[str | None, LogParseIssueCode | None]:
    """Normalize an aware ISO-8601/RFC3339 timestamp string to UTC.

    Returns ``(normalized, None)`` for a valid aware timestamp,
    ``(None, None)`` for a syntactically valid but naive timestamp (an
    expected null case, not an issue), or ``(None,
    LogParseIssueCode.INVALID_TIMESTAMP)`` for a string that could not be
    parsed at all. Never infers a missing year, date, or timezone, and
    never uses the current clock to repair an invalid value.
    """
    candidate = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None, LogParseIssueCode.INVALID_TIMESTAMP
    if parsed.utcoffset() is None:
        return None, None
    try:
        return parsed.astimezone(UTC).isoformat(), None
    except OverflowError:
        # A syntactically valid timestamp (e.g. year 9999 with a large
        # offset) can still overflow datetime's representable range once
        # converted to UTC -- not a ValueError, so it needs its own catch.
        return None, LogParseIssueCode.INVALID_TIMESTAMP


def _first_present(obj: dict[str, object], keys: tuple[str, ...]) -> object | None:
    """Return the value of the first key (by name, regardless of value) present."""
    for key in keys:
        if key in obj:
            return obj[key]
    return None


def parse_jsonl_line(
    text: str, line_number: int, *, redact: bool
) -> tuple[LogEvent | None, LogParseIssue | None]:
    """Parse one JSONL line into a canonical event, or a structured issue.

    Rejects arrays, strings, numbers, booleans, and ``null`` as top-level
    log events. ``message`` must resolve to a string; every other field
    degrades to ``None``/``unknown`` plus a warning issue rather than
    failing the whole event. Extra JSON keys are never read or copied
    into output.
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, RecursionError, ValueError):
        # ValueError also covers CPython's integer-string-conversion digit
        # limit (raised by json.loads itself while tokenizing any oversized
        # numeric literal, including one this package never reads), and
        # RecursionError covers pathologically deep nesting -- neither is a
        # JSONDecodeError, but both are equally "invalid JSON" from this
        # module's perspective.
        return None, LogParseIssue(
            line_number, LogParseIssueCode.MALFORMED_JSON, CheckStatus.WARN, "invalid JSON"
        )
    if not isinstance(obj, dict):
        return None, LogParseIssue(
            line_number,
            LogParseIssueCode.MALFORMED_JSON,
            CheckStatus.WARN,
            "top-level JSON value is not an object",
        )

    message_raw = _first_present(obj, _MESSAGE_KEYS)
    if not isinstance(message_raw, str):
        return None, LogParseIssue(
            line_number,
            LogParseIssueCode.INVALID_FIELD_TYPE,
            CheckStatus.WARN,
            "message field missing or not a string",
        )

    issue: LogParseIssue | None = None

    severity_raw = _first_present(obj, _SEVERITY_KEYS)
    if severity_raw is None:
        severity = LogSeverity.UNKNOWN
    elif isinstance(severity_raw, str):
        severity = normalize_severity(severity_raw)
    else:
        severity = LogSeverity.UNKNOWN
        issue = LogParseIssue(
            line_number,
            LogParseIssueCode.INVALID_FIELD_TYPE,
            CheckStatus.WARN,
            "severity field is not a string",
        )

    hostname_raw = _first_present(obj, _HOSTNAME_KEYS)
    hostname: str | None
    if hostname_raw is None:
        hostname = None
    elif isinstance(hostname_raw, str):
        hostname = hostname_raw
    else:
        hostname = None
        if issue is None:
            issue = LogParseIssue(
                line_number,
                LogParseIssueCode.INVALID_FIELD_TYPE,
                CheckStatus.WARN,
                "hostname field is not a string",
            )

    source_raw = _first_present(obj, _SOURCE_KEYS)
    source: str | None
    if source_raw is None:
        source = None
    elif isinstance(source_raw, str):
        source = source_raw
    else:
        source = None
        if issue is None:
            issue = LogParseIssue(
                line_number,
                LogParseIssueCode.INVALID_FIELD_TYPE,
                CheckStatus.WARN,
                "source field is not a string",
            )

    pid_raw = _first_present(obj, _PID_KEYS)
    pid: int | None
    if pid_raw is None:
        pid = None
    elif type(pid_raw) is int and 0 <= pid_raw <= _MAX_PID:
        pid = pid_raw
    else:
        pid = None
        if issue is None:
            issue = LogParseIssue(
                line_number,
                LogParseIssueCode.INVALID_FIELD_TYPE,
                CheckStatus.WARN,
                f"pid field is not an integer in range 0-{_MAX_PID}",
            )

    timestamp_raw_value = _first_present(obj, _TIMESTAMP_KEYS)
    timestamp: str | None = None
    timestamp_raw: str | None = None
    if timestamp_raw_value is not None:
        if isinstance(timestamp_raw_value, str):
            timestamp_raw = timestamp_raw_value
            timestamp, ts_issue_code = _normalize_timestamp(timestamp_raw_value)
            if ts_issue_code is not None and issue is None:
                issue = LogParseIssue(
                    line_number, ts_issue_code, CheckStatus.WARN, "timestamp could not be parsed"
                )
        else:
            timestamp_raw = json.dumps(timestamp_raw_value)
            if issue is None:
                issue = LogParseIssue(
                    line_number,
                    LogParseIssueCode.INVALID_FIELD_TYPE,
                    CheckStatus.WARN,
                    "timestamp field is not a string",
                )

    message = message_raw
    redacted = False
    if redact:
        message, redacted = redact_message(message_raw)

    event = LogEvent(
        line_number=line_number,
        input_format=LogInputFormat.JSONL,
        timestamp=timestamp,
        timestamp_raw=timestamp_raw,
        hostname=hostname,
        source=source,
        pid=pid,
        severity=severity,
        message=message,
        redacted=redacted,
    )
    return event, issue


def parse_syslog_line(
    text: str, line_number: int, *, redact: bool
) -> tuple[LogEvent | None, LogParseIssue | None]:
    """Parse one syslog line into a canonical event, or a structured issue.

    Supports an optional ``<PRI>`` prefix, an RFC3339/ISO-8601 or BSD
    ``MMM DD HH:MM:SS`` timestamp, a hostname, a ``source[pid]: message``
    tail, and nothing else -- no multiline or stack-trace continuation.
    A BSD timestamp is preserved verbatim in ``timestamp_raw`` with
    ``timestamp=None`` and no issue: this is documented, expected
    behavior, never an inferred year/timezone.
    """
    remainder = text
    severity = LogSeverity.UNKNOWN

    pri_match = _PRI_RE.match(remainder)
    if pri_match is not None:
        pri_value = int(pri_match.group(1))
        if pri_value > 191:
            return None, LogParseIssue(
                line_number,
                LogParseIssueCode.MALFORMED_LINE,
                CheckStatus.WARN,
                "PRI value out of range",
            )
        severity = _PRI_SEVERITY_BY_MOD8[pri_value % 8]
        remainder = remainder[pri_match.end() :]

    timestamp: str | None = None
    timestamp_raw: str | None = None
    ts_issue_code: LogParseIssueCode | None = None

    rfc_match = _RFC3339_RE.match(remainder)
    if rfc_match is not None:
        timestamp_raw = rfc_match.group(1)
        remainder = remainder[rfc_match.end() :].lstrip(" ")
        timestamp, ts_issue_code = _normalize_timestamp(timestamp_raw)
    else:
        bsd_match = _BSD_TS_RE.match(remainder)
        if bsd_match is not None:
            timestamp_raw = bsd_match.group(1)
            remainder = remainder[bsd_match.end() :].lstrip(" ")
        else:
            return None, LogParseIssue(
                line_number,
                LogParseIssueCode.MALFORMED_LINE,
                CheckStatus.WARN,
                "no recognizable timestamp",
            )

    hostname, _sep, tail = remainder.partition(" ")
    if not hostname:
        return None, LogParseIssue(
            line_number, LogParseIssueCode.MALFORMED_LINE, CheckStatus.WARN, "missing hostname"
        )

    header_match = _HEADER_TAIL_RE.match(tail)
    if header_match is None:
        return None, LogParseIssue(
            line_number,
            LogParseIssueCode.MALFORMED_LINE,
            CheckStatus.WARN,
            "missing source/message separator",
        )

    source = header_match.group("source")
    pid_str = header_match.group("pid")
    pid: int | None
    pid_issue: LogParseIssue | None = None
    if pid_str is None:
        pid = None
    else:
        try:
            pid = int(pid_str)
        except ValueError:
            # The `[pid]` capture group is an unbounded `\d+`, so a digit
            # run past CPython's integer-string-conversion limit raises
            # here rather than in the regex match itself -- degrade the
            # field instead of rejecting an otherwise well-formed line.
            pid = None
            pid_issue = LogParseIssue(
                line_number,
                LogParseIssueCode.INVALID_FIELD_TYPE,
                CheckStatus.WARN,
                "pid field is not representable as an integer",
            )
        else:
            if pid > _MAX_PID:
                pid = None
                pid_issue = LogParseIssue(
                    line_number,
                    LogParseIssueCode.INVALID_FIELD_TYPE,
                    CheckStatus.WARN,
                    f"pid field is out of range 0-{_MAX_PID}",
                )
    message_raw = header_match.group("message")

    message = message_raw
    redacted = False
    if redact:
        message, redacted = redact_message(message_raw)

    issue: LogParseIssue | None = None
    if ts_issue_code is not None:
        issue = LogParseIssue(
            line_number, ts_issue_code, CheckStatus.WARN, "timestamp could not be parsed"
        )
    if pid_issue is not None and issue is None:
        issue = pid_issue

    event = LogEvent(
        line_number=line_number,
        input_format=LogInputFormat.SYSLOG,
        timestamp=timestamp,
        timestamp_raw=timestamp_raw,
        hostname=hostname,
        source=source,
        pid=pid,
        severity=severity,
        message=message,
        redacted=redacted,
    )
    return event, issue


def parse_auto_line(
    text: str, line_number: int, *, redact: bool
) -> tuple[LogEvent | None, LogParseIssue | None]:
    """Detect and parse one line, inspecting only that line's own content.

    If the first non-whitespace character is ``{``, JSONL parsing is
    attempted; otherwise syslog parsing is attempted. Detection is
    per-line, not sticky across a file, so mixed input degrades
    gracefully. A malformed ``{``-prefixed line stays a JSON parse
    issue -- it never silently falls back to syslog parsing.
    """
    if text.lstrip().startswith("{"):
        return parse_jsonl_line(text, line_number, redact=redact)
    return parse_syslog_line(text, line_number, redact=redact)
