"""Streaming, bounded operational analysis over parsed log events.

Deterministic parsing, aggregation, and threshold comparisons only -- no
machine learning, no behavioral profiling, and no general anomaly
detection. Individual events are never retained for analysis; only
small, per-distinct-value aggregates (per severity, per source, per
message signature, per time bucket) are kept in memory via
:class:`LogAnalysisState`, regardless of how many events are streamed
through :meth:`LogAnalysisState.process_event`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from maops_pydevops.core.log_models import (
    ERROR_VOLUME_SEVERITIES,
    SEVERITY_ORDER,
    LogAnalysisFinding,
    LogAnalysisFindingCode,
    LogAnalysisTime,
    LogEvent,
    LogSeverity,
    SignatureEntry,
    SourceCount,
)
from maops_pydevops.core.models import CheckStatus

#: Display value for an absent or empty source, per spec section 9.
UNKNOWN_SOURCE = "<unknown>"

_SIGNATURE_MAX_LENGTH = 256
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
#: Requires at least one true hex letter (a-f/A-F) via lookahead, so a
#: purely decimal 8+-digit token (e.g. an order ID) is never misclassified
#: as hex -- decimal digits alone are also matched by this character
#: class, but should normalize to <num> instead (Day 4 finding).
_HEX_RE = re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{8,}\b")
_INT_RE = re.compile(r"(?<![\w.])\d+(?![\w.])")
_WHITESPACE_RE = re.compile(r"\s+")


def compute_signature(message: str) -> str:
    """Normalize an already-redacted message into a deterministic signature.

    Fixed order: UUID (must run before the hex rule, since a UUID's
    dash-broken hex runs would otherwise partially match it), IPv4, long
    hexadecimal identifiers, decimal integers, whitespace collapse,
    Unicode-preserving casefold, then a 256-character cap. Derived only
    from ``message`` as given -- callers must pass an already-redacted
    message; this function never sees or restores an unredacted value.
    """
    text = _UUID_RE.sub("<uuid>", message)
    text = _IPV4_RE.sub("<ip>", text)
    text = _INT_RE.sub("<num>", text)
    text = _HEX_RE.sub("<hex>", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = text.casefold()
    return text[:_SIGNATURE_MAX_LENGTH]


@dataclass
class _SignatureAggregate:
    """Small, fixed-size per-signature accumulator -- never a per-event list."""

    first_line: int
    last_line: int
    count: int = 0
    severity_counts: dict[LogSeverity, int] = field(default_factory=dict)


@dataclass
class LogAnalysisState:
    """Mutable streaming accumulator for ``logs analyze``.

    Constructed with the run's ``bucket_seconds`` (needed at insertion
    time to place each timestamped event into its bucket without
    retaining raw epoch values). Never accumulates a list of events --
    only per-distinct-value aggregates, whose size is bounded by the
    number of distinct severities/sources/signatures/buckets seen, not
    by the number of events processed.
    """

    bucket_seconds: int
    severity_counts: dict[LogSeverity, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    signatures: dict[str, _SignatureAggregate] = field(default_factory=dict)
    buckets: dict[int, int] = field(default_factory=dict)
    timestamped_events: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    out_of_order_events: int = 0
    _max_epoch_seen: int | None = field(default=None, repr=False)

    def process_event(self, event: LogEvent) -> None:
        """Fold one event into the running aggregates. O(1) amortized."""
        self.severity_counts[event.severity] = self.severity_counts.get(event.severity, 0) + 1

        source = event.source if event.source else UNKNOWN_SOURCE
        self.source_counts[source] = self.source_counts.get(source, 0) + 1

        signature = compute_signature(event.message)
        aggregate = self.signatures.get(signature)
        if aggregate is None:
            aggregate = _SignatureAggregate(
                first_line=event.line_number, last_line=event.line_number
            )
            self.signatures[signature] = aggregate
        aggregate.count += 1
        aggregate.last_line = event.line_number
        aggregate.severity_counts[event.severity] = (
            aggregate.severity_counts.get(event.severity, 0) + 1
        )

        if event.timestamp is None:
            return

        if self.timestamped_events == 0:
            self.first_timestamp = event.timestamp
        self.last_timestamp = event.timestamp
        self.timestamped_events += 1

        epoch_seconds = int(datetime.fromisoformat(event.timestamp).timestamp())
        if self._max_epoch_seen is not None and epoch_seconds < self._max_epoch_seen:
            self.out_of_order_events += 1
        else:
            self._max_epoch_seen = epoch_seconds

        bucket_start = (epoch_seconds // self.bucket_seconds) * self.bucket_seconds
        self.buckets[bucket_start] = self.buckets.get(bucket_start, 0) + 1


def finalize_severity_counts(state: LogAnalysisState) -> tuple[tuple[LogSeverity, int], ...]:
    """All 10 canonical severities, in fixed declaration order, never sorted by count."""
    return tuple((severity, state.severity_counts.get(severity, 0)) for severity in SEVERITY_ORDER)


def finalize_source_counts(state: LogAnalysisState) -> tuple[SourceCount, ...]:
    """Source counts ordered count descending, then source name ascending."""
    ordered = sorted(state.source_counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(SourceCount(source=source, count=count) for source, count in ordered)


def _sorted_signature_items(
    signatures: dict[str, _SignatureAggregate],
) -> list[tuple[str, _SignatureAggregate]]:
    """Every distinct signature, ordered count descending, signature ascending for ties."""
    return sorted(signatures.items(), key=lambda item: (-item[1].count, item[0]))


def _to_signature_entry(signature: str, aggregate: _SignatureAggregate) -> SignatureEntry:
    severity_counts = tuple(
        (severity, count)
        for severity in SEVERITY_ORDER
        if (count := aggregate.severity_counts.get(severity, 0)) > 0
    )
    return SignatureEntry(
        signature=signature,
        count=aggregate.count,
        first_line=aggregate.first_line,
        last_line=aggregate.last_line,
        severity_counts=severity_counts,
    )


def finalize_top_signatures(state: LogAnalysisState, *, top: int) -> tuple[SignatureEntry, ...]:
    """The ``top`` largest/most-frequent signatures, for report display only.

    ``top`` bounds the display list only -- it never limits which
    signatures are scanned for the repeated-signature finding (see
    :func:`build_findings`), so a small ``--top`` value cannot hide a
    real repeated-signature finding.
    """
    ordered = _sorted_signature_items(state.signatures)
    return tuple(
        _to_signature_entry(signature, aggregate) for signature, aggregate in ordered[:top]
    )


def _peak_bucket(buckets: dict[int, int]) -> tuple[int | None, int]:
    """Earliest bucket wins ties; ``sorted()`` walks epoch order, not insertion order,
    since the input stream itself can be out of order."""
    if not buckets:
        return None, 0
    best_start: int | None = None
    best_count = -1
    for start in sorted(buckets):
        count = buckets[start]
        if count > best_count:
            best_start, best_count = start, count
    return best_start, best_count


def finalize_time(state: LogAnalysisState) -> LogAnalysisTime:
    """Assemble the report's ``time`` section from the running state."""
    peak_start_epoch, peak_count = _peak_bucket(state.buckets)
    peak_start = (
        datetime.fromtimestamp(peak_start_epoch, tz=UTC).isoformat()
        if peak_start_epoch is not None
        else None
    )
    return LogAnalysisTime(
        timestamped_events=state.timestamped_events,
        first_timestamp=state.first_timestamp,
        last_timestamp=state.last_timestamp,
        out_of_order_events=state.out_of_order_events,
        bucket_seconds=state.bucket_seconds,
        peak_bucket_start=peak_start,
        peak_bucket_count=peak_count,
    )


def build_findings(
    state: LogAnalysisState,
    *,
    malformed_lines: int,
    overlong_lines: int,
    truncated: bool,
    repeat_threshold: int,
    error_threshold: int,
) -> tuple[LogAnalysisFinding, ...]:
    """Deterministic, advisory findings in a fixed emission order.

    All findings carry :data:`CheckStatus.WARN` -- they are advisory and
    never affect exit code by themselves. Emission order: truncated
    input, malformed lines, overlong lines, error volume, unknown
    severity, out-of-order timestamps, then one entry per repeated
    signature (count descending, signature ascending for ties).
    """
    findings: list[LogAnalysisFinding] = []

    if truncated:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.TRUNCATED_INPUT,
                CheckStatus.WARN,
                "input was truncated by a configured line, byte, or line-length limit",
            )
        )
    if malformed_lines > 0:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.MALFORMED_LINES,
                CheckStatus.WARN,
                f"{malformed_lines} line(s) could not be parsed",
            )
        )
    if overlong_lines > 0:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.OVERLONG_LINES,
                CheckStatus.WARN,
                f"{overlong_lines} line(s) exceeded max-line-bytes and were skipped",
            )
        )

    error_volume = sum(
        count
        for severity, count in state.severity_counts.items()
        if severity in ERROR_VOLUME_SEVERITIES
    )
    if error_volume >= error_threshold:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.ERROR_VOLUME,
                CheckStatus.WARN,
                f"{error_volume} error-level event(s) at or above threshold {error_threshold}",
            )
        )

    unknown_count = state.severity_counts.get(LogSeverity.UNKNOWN, 0)
    if unknown_count > 0:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.UNKNOWN_SEVERITY,
                CheckStatus.WARN,
                f"{unknown_count} event(s) had an unrecognized severity",
            )
        )

    if state.out_of_order_events > 0:
        findings.append(
            LogAnalysisFinding(
                LogAnalysisFindingCode.OUT_OF_ORDER_TIMESTAMPS,
                CheckStatus.WARN,
                f"{state.out_of_order_events} event(s) had an out-of-order normalized timestamp",
            )
        )

    for signature, aggregate in _sorted_signature_items(state.signatures):
        if aggregate.count >= repeat_threshold:
            findings.append(
                LogAnalysisFinding(
                    LogAnalysisFindingCode.REPEATED_SIGNATURE,
                    CheckStatus.WARN,
                    f"signature repeated {aggregate.count} time(s) "
                    f"(at or above threshold {repeat_threshold}): {signature!r}",
                )
            )

    return tuple(findings)
