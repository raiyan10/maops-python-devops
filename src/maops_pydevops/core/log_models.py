"""Typed data models for bounded log parsing and operational analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from maops_pydevops.core.models import CheckStatus


class LogSeverity(StrEnum):
    """Canonical, normalized log severity. Unknown strings become UNKNOWN."""

    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    ALERT = "alert"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


class LogInputFormat(StrEnum):
    """Supported log input formats."""

    AUTO = "auto"
    JSONL = "jsonl"
    SYSLOG = "syslog"


class LogParseIssueCode(StrEnum):
    """Closed set of structured, per-line parse issue reasons."""

    MALFORMED_JSON = "malformed_json"
    MALFORMED_LINE = "malformed_line"
    INVALID_FIELD_TYPE = "invalid_field_type"
    INVALID_TIMESTAMP = "invalid_timestamp"
    OVERLONG_LINE = "overlong_line"
    TRUNCATED_FRAGMENT = "truncated_fragment"


class LogAnalysisFindingCode(StrEnum):
    """Closed set of deterministic, advisory analysis finding reasons."""

    TRUNCATED_INPUT = "truncated_input"
    MALFORMED_LINES = "malformed_lines"
    OVERLONG_LINES = "overlong_lines"
    ERROR_VOLUME = "error_volume"
    UNKNOWN_SEVERITY = "unknown_severity"
    OUT_OF_ORDER_TIMESTAMPS = "out_of_order_timestamps"
    REPEATED_SIGNATURE = "repeated_signature"


@dataclass(frozen=True)
class LogEvent:
    """A single canonical, redacted (unless disabled) parsed log event."""

    line_number: int
    input_format: LogInputFormat
    timestamp: str | None
    timestamp_raw: str | None
    hostname: str | None
    source: str | None
    pid: int | None
    severity: LogSeverity
    message: str
    redacted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "input_format": self.input_format.value,
            "timestamp": self.timestamp,
            "timestamp_raw": self.timestamp_raw,
            "hostname": self.hostname,
            "source": self.source,
            "pid": self.pid,
            "severity": self.severity.value,
            "message": self.message,
            "redacted": self.redacted,
        }


@dataclass(frozen=True)
class LogParseIssue:
    """A structured, per-line parse issue. Never echoes a complete raw line."""

    line_number: int
    code: LogParseIssueCode
    status: CheckStatus
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "line_number": self.line_number,
            "code": self.code.value,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class LogParseOptions:
    """The effective options in force for a ``logs parse`` run."""

    input_format: LogInputFormat
    max_lines: int
    max_bytes: int
    max_line_bytes: int
    max_events: int
    redact: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "input_format": self.input_format.value,
            "max_lines": self.max_lines,
            "max_bytes": self.max_bytes,
            "max_line_bytes": self.max_line_bytes,
            "max_events": self.max_events,
            "redact": self.redact,
        }


@dataclass(frozen=True)
class LogParseSummary:
    """Aggregate counters for a ``logs parse`` run."""

    bytes_read: int
    lines_read: int
    blank_lines: int
    events_parsed: int
    events_emitted: int
    malformed_lines: int
    overlong_lines: int

    def to_dict(self) -> dict[str, object]:
        return {
            "bytes_read": self.bytes_read,
            "lines_read": self.lines_read,
            "blank_lines": self.blank_lines,
            "events_parsed": self.events_parsed,
            "events_emitted": self.events_emitted,
            "malformed_lines": self.malformed_lines,
            "overlong_lines": self.overlong_lines,
        }


@dataclass(frozen=True)
class LogParseReport:
    """The full report rendered by ``maops-py logs parse``."""

    version: str
    path: str
    options: LogParseOptions
    summary: LogParseSummary
    events: tuple[LogEvent, ...]
    issues: tuple[LogParseIssue, ...]
    line_limit_reached: bool
    byte_limit_reached: bool
    truncated: bool
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "path": self.path,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "issues": [issue.to_dict() for issue in self.issues],
            "line_limit_reached": self.line_limit_reached,
            "byte_limit_reached": self.byte_limit_reached,
            "truncated": self.truncated,
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


@dataclass(frozen=True)
class SourceCount:
    """A single source's occurrence count, for ``logs analyze``'s ``source_counts``."""

    source: str
    count: int

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source, "count": self.count}


@dataclass(frozen=True)
class SignatureEntry:
    """A single normalized message signature's aggregate statistics."""

    signature: str
    count: int
    first_line: int
    last_line: int
    severity_counts: tuple[tuple[LogSeverity, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "signature": self.signature,
            "count": self.count,
            "first_line": self.first_line,
            "last_line": self.last_line,
            "severity_counts": {severity.value: count for severity, count in self.severity_counts},
        }


@dataclass(frozen=True)
class LogAnalysisTime:
    """Timestamp range, ordering, and peak-bucket facts for ``logs analyze``."""

    timestamped_events: int
    first_timestamp: str | None
    last_timestamp: str | None
    out_of_order_events: int
    bucket_seconds: int
    peak_bucket_start: str | None
    peak_bucket_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamped_events": self.timestamped_events,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "out_of_order_events": self.out_of_order_events,
            "bucket_seconds": self.bucket_seconds,
            "peak_bucket_start": self.peak_bucket_start,
            "peak_bucket_count": self.peak_bucket_count,
        }


@dataclass(frozen=True)
class LogAnalysisFinding:
    """A single deterministic, advisory analysis finding."""

    code: LogAnalysisFindingCode
    status: CheckStatus
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class LogAnalysisOptions:
    """The effective options in force for a ``logs analyze`` run."""

    input_format: LogInputFormat
    max_lines: int
    max_bytes: int
    max_line_bytes: int
    top: int
    bucket_seconds: int
    repeat_threshold: int
    error_threshold: int
    redact: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "input_format": self.input_format.value,
            "max_lines": self.max_lines,
            "max_bytes": self.max_bytes,
            "max_line_bytes": self.max_line_bytes,
            "top": self.top,
            "bucket_seconds": self.bucket_seconds,
            "repeat_threshold": self.repeat_threshold,
            "error_threshold": self.error_threshold,
            "redact": self.redact,
        }


@dataclass(frozen=True)
class LogAnalysisSummary:
    """Aggregate counters for a ``logs analyze`` run."""

    bytes_read: int
    lines_read: int
    events_parsed: int
    malformed_lines: int
    overlong_lines: int

    def to_dict(self) -> dict[str, object]:
        return {
            "bytes_read": self.bytes_read,
            "lines_read": self.lines_read,
            "events_parsed": self.events_parsed,
            "malformed_lines": self.malformed_lines,
            "overlong_lines": self.overlong_lines,
        }


@dataclass(frozen=True)
class LogAnalysisReport:
    """The full report rendered by ``maops-py logs analyze``."""

    version: str
    path: str
    options: LogAnalysisOptions
    summary: LogAnalysisSummary
    severity_counts: tuple[tuple[LogSeverity, int], ...]
    source_counts: tuple[SourceCount, ...]
    top_signatures: tuple[SignatureEntry, ...]
    time: LogAnalysisTime
    findings: tuple[LogAnalysisFinding, ...]
    issues: tuple[LogParseIssue, ...]
    line_limit_reached: bool
    byte_limit_reached: bool
    truncated: bool
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "path": self.path,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "severity_counts": {severity.value: count for severity, count in self.severity_counts},
            "source_counts": [source.to_dict() for source in self.source_counts],
            "top_signatures": [signature.to_dict() for signature in self.top_signatures],
            "time": self.time.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "issues": [issue.to_dict() for issue in self.issues],
            "line_limit_reached": self.line_limit_reached,
            "byte_limit_reached": self.byte_limit_reached,
            "truncated": self.truncated,
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


_SEVERITY_ALIASES: dict[str, LogSeverity] = {
    "warn": LogSeverity.WARNING,
    "err": LogSeverity.ERROR,
    "crit": LogSeverity.CRITICAL,
    "fatal": LogSeverity.CRITICAL,
    "emerg": LogSeverity.EMERGENCY,
    "information": LogSeverity.INFO,
}

#: Canonical severities in fixed declaration order, used for stable
#: severity_counts ordering (never sorted by count).
SEVERITY_ORDER: tuple[LogSeverity, ...] = tuple(LogSeverity)

#: Severities counted toward "error volume" for analysis findings.
ERROR_VOLUME_SEVERITIES: frozenset[LogSeverity] = frozenset(
    {LogSeverity.ERROR, LogSeverity.CRITICAL, LogSeverity.ALERT, LogSeverity.EMERGENCY}
)


def normalize_severity(raw: str) -> LogSeverity:
    """Normalize a raw severity string via aliasing, falling back to UNKNOWN.

    Never raises: any string not recognized as a canonical value or a
    known alias becomes :data:`LogSeverity.UNKNOWN` rather than failing
    the whole event.
    """
    candidate = raw.strip().casefold()
    if candidate in _SEVERITY_ALIASES:
        return _SEVERITY_ALIASES[candidate]
    try:
        return LogSeverity(candidate)
    except ValueError:
        return LogSeverity.UNKNOWN
