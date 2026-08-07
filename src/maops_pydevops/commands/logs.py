"""CLI-facing log parsing and analysis orchestration.

Real orchestration lives here (open -> dispatch per line -> assemble a
frozen report), mirroring ``commands/doctor.py``/``commands/tools.py``
rather than ``commands/inventory.py``'s re-export-shim pattern, since
``logs parse``/``logs analyze`` need genuine per-command coordination
between :mod:`maops_pydevops.core.log_reader`,
:mod:`maops_pydevops.core.log_parsers`, and
:mod:`maops_pydevops.core.log_analysis`.
"""

from __future__ import annotations

from collections.abc import Callable

from maops_pydevops.core.log_analysis import (
    LogAnalysisState,
    build_findings,
    finalize_severity_counts,
    finalize_source_counts,
    finalize_time,
    finalize_top_signatures,
)
from maops_pydevops.core.log_models import (
    LogAnalysisOptions,
    LogAnalysisReport,
    LogAnalysisSummary,
    LogEvent,
    LogInputFormat,
    LogParseIssue,
    LogParseIssueCode,
    LogParseOptions,
    LogParseReport,
    LogParseSummary,
)
from maops_pydevops.core.log_parsers import parse_auto_line, parse_jsonl_line, parse_syslog_line
from maops_pydevops.core.log_reader import open_bounded_log_file
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.version import get_version

_LineParser = Callable[..., tuple[LogEvent | None, LogParseIssue | None]]

_PARSERS: dict[LogInputFormat, _LineParser] = {
    LogInputFormat.JSONL: parse_jsonl_line,
    LogInputFormat.SYSLOG: parse_syslog_line,
    LogInputFormat.AUTO: parse_auto_line,
}


def build_log_parse_report(
    path_arg: str,
    *,
    input_format: LogInputFormat,
    max_lines: int,
    max_bytes: int,
    max_line_bytes: int,
    max_events: int,
    redact: bool,
) -> tuple[LogParseReport | None, str | None]:
    """Parse ``path_arg`` into a structured :class:`LogParseReport`.

    Returns ``(None, error)`` only when the file itself cannot be opened
    at all (missing, directory, symlink, special file, race). Every
    other degraded condition (malformed lines, overlong lines, invalid
    timestamps) is folded into the report's ``issues`` list with
    ``overall`` reflecting it -- never a build failure.
    """
    reader, _failure_reason, failure_detail = open_bounded_log_file(
        path_arg, max_lines=max_lines, max_bytes=max_bytes, max_line_bytes=max_line_bytes
    )
    if reader is None:
        return None, f"{failure_detail}: {path_arg}"

    parse_line = _PARSERS[input_format]

    events: list[LogEvent] = []
    issues: list[LogParseIssue] = []
    blank_lines = 0
    events_parsed = 0
    malformed_lines = 0
    overlong_lines = 0

    try:
        for raw_line in reader.read_lines():
            if raw_line.overlong:
                overlong_lines += 1
                issues.append(
                    LogParseIssue(
                        raw_line.line_number,
                        LogParseIssueCode.OVERLONG_LINE,
                        CheckStatus.WARN,
                        "line exceeds max-line-bytes and was skipped",
                    )
                )
                continue
            if raw_line.text.strip() == "":
                blank_lines += 1
                continue

            event, issue = parse_line(raw_line.text, raw_line.line_number, redact=redact)
            if issue is not None:
                issues.append(issue)
            if event is None:
                malformed_lines += 1
                continue

            events_parsed += 1
            if len(events) < max_events:
                events.append(event)
    finally:
        reader.close()

    non_blank_lines = reader.lines_read - blank_lines
    if non_blank_lines == 0:
        overall = CheckStatus.WARN if (issues or reader.truncated) else CheckStatus.PASS
    elif events_parsed == 0:
        overall = CheckStatus.FAIL
    elif issues or reader.truncated:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    report = LogParseReport(
        version=get_version(),
        path=reader.path,
        options=LogParseOptions(
            input_format=input_format,
            max_lines=max_lines,
            max_bytes=max_bytes,
            max_line_bytes=max_line_bytes,
            max_events=max_events,
            redact=redact,
        ),
        summary=LogParseSummary(
            bytes_read=reader.bytes_read,
            lines_read=reader.lines_read,
            blank_lines=blank_lines,
            events_parsed=events_parsed,
            events_emitted=len(events),
            malformed_lines=malformed_lines,
            overlong_lines=overlong_lines,
        ),
        events=tuple(events),
        issues=tuple(issues),
        line_limit_reached=reader.line_limit_reached,
        byte_limit_reached=reader.byte_limit_reached,
        truncated=reader.truncated,
        overall=overall,
    )
    return report, None


def build_log_analysis_report(
    path_arg: str,
    *,
    input_format: LogInputFormat,
    max_lines: int,
    max_bytes: int,
    max_line_bytes: int,
    top: int,
    bucket_seconds: int,
    repeat_threshold: int,
    error_threshold: int,
    redact: bool,
) -> tuple[LogAnalysisReport | None, str | None]:
    """Stream ``path_arg`` into a structured :class:`LogAnalysisReport`.

    No individual event is ever retained -- events are folded into
    :class:`~maops_pydevops.core.log_analysis.LogAnalysisState` one at a
    time and discarded. Returns ``(None, error)`` only when the file
    itself cannot be opened at all, mirroring
    :func:`build_log_parse_report`.
    """
    reader, _failure_reason, failure_detail = open_bounded_log_file(
        path_arg, max_lines=max_lines, max_bytes=max_bytes, max_line_bytes=max_line_bytes
    )
    if reader is None:
        return None, f"{failure_detail}: {path_arg}"

    parse_line = _PARSERS[input_format]
    state = LogAnalysisState(bucket_seconds=bucket_seconds)

    issues: list[LogParseIssue] = []
    blank_lines = 0
    events_parsed = 0
    malformed_lines = 0
    overlong_lines = 0

    try:
        for raw_line in reader.read_lines():
            if raw_line.overlong:
                overlong_lines += 1
                issues.append(
                    LogParseIssue(
                        raw_line.line_number,
                        LogParseIssueCode.OVERLONG_LINE,
                        CheckStatus.WARN,
                        "line exceeds max-line-bytes and was skipped",
                    )
                )
                continue
            if raw_line.text.strip() == "":
                blank_lines += 1
                continue

            event, issue = parse_line(raw_line.text, raw_line.line_number, redact=redact)
            if issue is not None:
                issues.append(issue)
            if event is None:
                malformed_lines += 1
                continue

            events_parsed += 1
            state.process_event(event)
    finally:
        reader.close()

    findings = build_findings(
        state,
        malformed_lines=malformed_lines,
        overlong_lines=overlong_lines,
        truncated=reader.truncated,
        repeat_threshold=repeat_threshold,
        error_threshold=error_threshold,
    )

    non_blank_lines = reader.lines_read - blank_lines
    if non_blank_lines == 0:
        overall = CheckStatus.WARN if (issues or reader.truncated or findings) else CheckStatus.PASS
    elif events_parsed == 0:
        overall = CheckStatus.FAIL
    elif issues or reader.truncated or findings:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    report = LogAnalysisReport(
        version=get_version(),
        path=reader.path,
        options=LogAnalysisOptions(
            input_format=input_format,
            max_lines=max_lines,
            max_bytes=max_bytes,
            max_line_bytes=max_line_bytes,
            top=top,
            bucket_seconds=bucket_seconds,
            repeat_threshold=repeat_threshold,
            error_threshold=error_threshold,
            redact=redact,
        ),
        summary=LogAnalysisSummary(
            bytes_read=reader.bytes_read,
            lines_read=reader.lines_read,
            events_parsed=events_parsed,
            malformed_lines=malformed_lines,
            overlong_lines=overlong_lines,
        ),
        severity_counts=finalize_severity_counts(state),
        source_counts=finalize_source_counts(state),
        top_signatures=finalize_top_signatures(state, top=top),
        time=finalize_time(state),
        findings=findings,
        issues=tuple(issues),
        line_limit_reached=reader.line_limit_reached,
        byte_limit_reached=reader.byte_limit_reached,
        truncated=reader.truncated,
        overall=overall,
    )
    return report, None
