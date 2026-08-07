"""Streaming operational analysis: signature normalization, ordering,
time buckets, and deterministic findings.
"""

from __future__ import annotations

from maops_pydevops.core.log_analysis import (
    UNKNOWN_SOURCE,
    LogAnalysisState,
    build_findings,
    compute_signature,
    finalize_severity_counts,
    finalize_source_counts,
    finalize_time,
    finalize_top_signatures,
)
from maops_pydevops.core.log_models import LogEvent, LogInputFormat, LogSeverity


def _event(
    line: int,
    *,
    ts: str | None = None,
    severity: LogSeverity = LogSeverity.INFO,
    source: str | None = "svc",
    message: str = "message",
) -> LogEvent:
    return LogEvent(
        line_number=line,
        input_format=LogInputFormat.JSONL,
        timestamp=ts,
        timestamp_raw=ts,
        hostname=None,
        source=source,
        pid=None,
        severity=severity,
        message=message,
        redacted=False,
    )


def test_uuid_normalization() -> None:
    signature = compute_signature("request id 550e8400-e29b-41d4-a716-446655440000 failed")
    assert signature == "request id <uuid> failed"


def test_ipv4_normalization() -> None:
    signature = compute_signature("connection to 192.168.1.100 refused")
    assert signature == "connection to <ip> refused"


def test_hex_normalization() -> None:
    signature = compute_signature("checksum deadbeefcafe1234 mismatch")
    assert signature == "checksum <hex> mismatch"


def test_integer_normalization() -> None:
    signature = compute_signature("retry attempt 42 of 5")
    assert signature == "retry attempt <num> of <num>"


def test_whitespace_collapse() -> None:
    signature = compute_signature("too    many     spaces")
    assert signature == "too many spaces"


def test_unicode_casefold_preserving() -> None:
    # .casefold() (not .lower()) is used deliberately: it performs full
    # Unicode case folding, so e.g. German "ß" becomes "ss" -- this is
    # the correct, spec-mandated behavior, not a lossy transliteration.
    signature = compute_signature("FEHLER GROSSE Straße")
    assert signature == "fehler grosse strasse"
    assert compute_signature("CAFÉ") == "café"


def test_signature_length_cap_at_256() -> None:
    signature = compute_signature("x" * 500)
    assert len(signature) == 256


def test_uuid_normalized_before_hex_rule() -> None:
    # A UUID's dash-broken hex runs must not be partially matched by the
    # standalone hex rule; the whole UUID should collapse to one <uuid>.
    signature = compute_signature("id=550e8400-e29b-41d4-a716-446655440000")
    assert signature.count("<uuid>") == 1
    assert "<hex>" not in signature


def test_severity_counts_fixed_order_not_sorted_by_count() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, severity=LogSeverity.ERROR))
    state.process_event(_event(2, severity=LogSeverity.DEBUG))
    counts = finalize_severity_counts(state)
    assert [severity.value for severity, _count in counts] == [
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
    ]


def test_source_counts_count_desc_name_asc_tie() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, source="zeta"))
    state.process_event(_event(2, source="alpha"))
    state.process_event(_event(3, source="alpha"))
    counts = finalize_source_counts(state)
    assert [(c.source, c.count) for c in counts] == [("alpha", 2), ("zeta", 1)]


def test_unknown_source_bucket() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, source=None))
    counts = finalize_source_counts(state)
    assert counts[0].source == UNKNOWN_SOURCE


def test_top_signatures_count_desc_signature_asc_tie() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, message="zzz message"))
    state.process_event(_event(2, message="aaa message"))
    state.process_event(_event(3, message="aaa message"))
    signatures = finalize_top_signatures(state, top=10)
    assert signatures[0].signature == "aaa message"
    assert signatures[0].count == 2
    assert signatures[1].signature == "zzz message"
    assert signatures[1].count == 1


def test_top_zero_returns_empty() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1))
    assert finalize_top_signatures(state, top=0) == ()


def test_top_boundary_returns_exactly_n() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    for word in ("alpha", "bravo", "charlie", "delta", "echo"):
        state.process_event(_event(1, message=f"distinct {word} message"))
    signatures = finalize_top_signatures(state, top=3)
    assert len(signatures) == 3


def test_first_and_last_line_tracking() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(2, message="repeat"))
    state.process_event(_event(9, message="repeat"))
    state.process_event(_event(5, message="repeat"))
    signatures = finalize_top_signatures(state, top=10)
    assert signatures[0].first_line == 2
    assert signatures[0].last_line == 5


def test_timestamp_range_and_ordering() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:00:00+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:05:00+00:00"))
    time_info = finalize_time(state)
    assert time_info.timestamped_events == 2
    assert time_info.first_timestamp == "2026-01-01T00:00:00+00:00"
    assert time_info.last_timestamp == "2026-01-01T00:05:00+00:00"
    assert time_info.out_of_order_events == 0


def test_out_of_order_detection() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:05:00+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:00:00+00:00"))
    time_info = finalize_time(state)
    assert time_info.out_of_order_events == 1


def test_time_bucket_boundaries_epoch_arithmetic() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:00:59+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:01:00+00:00"))
    assert len(state.buckets) == 2


def test_peak_bucket() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:00:00+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:00:10+00:00"))
    state.process_event(_event(3, ts="2026-01-01T00:05:00+00:00"))
    time_info = finalize_time(state)
    assert time_info.peak_bucket_start == "2026-01-01T00:00:00+00:00"
    assert time_info.peak_bucket_count == 2


def test_peak_bucket_tie_earliest_wins() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:05:00+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:00:00+00:00"))
    time_info = finalize_time(state)
    assert time_info.peak_bucket_start == "2026-01-01T00:00:00+00:00"


def test_no_timestamp_case_peak_bucket_null_and_zero() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts=None))
    time_info = finalize_time(state)
    assert time_info.peak_bucket_start is None
    assert time_info.peak_bucket_count == 0
    assert time_info.timestamped_events == 0


def test_bsd_style_null_timestamps_excluded_from_buckets() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts=None))  # simulates a BSD-syslog event
    state.process_event(_event(2, ts="2026-01-01T00:00:00+00:00"))
    assert len(state.buckets) == 1
    assert state.timestamped_events == 1


def test_repeated_event_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    for i in range(5):
        state.process_event(_event(i, message="same message"))
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "repeated_signature" in codes


def test_error_volume_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, severity=LogSeverity.ERROR))
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "error_volume" in codes


def test_error_volume_includes_all_four_severities() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    for sev in (LogSeverity.ERROR, LogSeverity.CRITICAL, LogSeverity.ALERT, LogSeverity.EMERGENCY):
        state.process_event(_event(1, severity=sev))
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=4,
    )
    detail = next(f.detail for f in findings if f.code.value == "error_volume")
    assert "4 error-level" in detail


def test_unknown_severity_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, severity=LogSeverity.UNKNOWN))
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "unknown_severity" in codes


def test_malformed_line_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    findings = build_findings(
        state,
        malformed_lines=3,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "malformed_lines" in codes


def test_overlong_line_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=2,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "overlong_lines" in codes


def test_truncation_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=True,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "truncated_input" in codes


def test_out_of_order_finding() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    state.process_event(_event(1, ts="2026-01-01T00:05:00+00:00"))
    state.process_event(_event(2, ts="2026-01-01T00:00:00+00:00"))
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "out_of_order_timestamps" in codes


def test_findings_fixed_emission_order() -> None:
    state = LogAnalysisState(bucket_seconds=60)
    for i in range(5):
        state.process_event(_event(i, severity=LogSeverity.ERROR, message="same"))
    state.process_event(_event(5, severity=LogSeverity.UNKNOWN))
    findings = build_findings(
        state,
        malformed_lines=1,
        overlong_lines=1,
        truncated=True,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert codes == [
        "truncated_input",
        "malformed_lines",
        "overlong_lines",
        "error_volume",
        "unknown_severity",
        "repeated_signature",
    ]


def test_repeated_signature_finding_not_limited_by_top() -> None:
    # A repeated signature must still trigger a finding even when --top
    # is small enough to hide it from the displayed top_signatures list.
    state = LogAnalysisState(bucket_seconds=60)
    for i in range(6):
        state.process_event(_event(i, message="frequent one"))
    for i in range(6, 12):
        state.process_event(_event(i, message=f"unique {i}"))
    top_signatures = finalize_top_signatures(state, top=0)
    assert top_signatures == ()
    findings = build_findings(
        state,
        malformed_lines=0,
        overlong_lines=0,
        truncated=False,
        repeat_threshold=5,
        error_threshold=1,
    )
    codes = [f.code.value for f in findings]
    assert "repeated_signature" in codes


def test_streaming_state_never_retains_full_event_list() -> None:
    import dataclasses

    state = LogAnalysisState(bucket_seconds=60)
    for i in range(100):
        state.process_event(_event(i, message="same message every time"))
    # Only one distinct signature aggregate should exist, not 100 events.
    assert len(state.signatures) == 1
    # Enumerate the dataclass's own fields rather than hasattr() on the
    # instance: no field may hold a per-event collection (list/tuple of
    # LogEvent), regardless of what it happens to be named.
    field_names = {f.name for f in dataclasses.fields(state)}
    assert "events" not in field_names
    for name in field_names:
        value = getattr(state, name)
        assert not isinstance(value, (list, tuple)), f"{name} is an unbounded per-event collection"
