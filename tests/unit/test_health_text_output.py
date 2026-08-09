"""Text rendering for health reports: sanitization, no ANSI, stable structure."""

from __future__ import annotations

from maops_pydevops.core.health_models import (
    HealthProtocol,
    HttpAttempt,
    HttpFailureReason,
    HttpMethod,
    HttpOptions,
    HttpReport,
    HttpSummary,
    HttpTargetResult,
    TcpAttempt,
    TcpOptions,
    TcpReport,
    TcpSummary,
    TcpTargetResult,
)
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.output import render_health_http_text, render_health_tcp_text


def _http_report(target: str = "http://example.com/", detail: str | None = None) -> HttpReport:
    options = HttpOptions(
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=3.0,
        retries=1,
        retry_delay_seconds=0.25,
        workers=4,
        follow_redirects=False,
        tls_verify=True,
    )
    attempt = HttpAttempt(
        attempt=1,
        duration_ms=5,
        http_status=200 if detail is None else None,
        peer_ip="127.0.0.1" if detail is None else None,
        failure_reason=None if detail is None else HttpFailureReason.DNS_ERROR,
        detail=detail,
    )
    result = HttpTargetResult(
        index=1,
        target=target,
        status=CheckStatus.PASS if detail is None else CheckStatus.FAIL,
        attempts_used=1,
        total_duration_ms=5,
        final_http_status=200 if detail is None else None,
        peer_ip="127.0.0.1" if detail is None else None,
        attempts=(attempt,),
    )
    summary = HttpSummary(
        targets=1,
        passed=1 if detail is None else 0,
        warned=0,
        failed=0 if detail is None else 1,
        attempts=1,
    )
    return HttpReport(
        version="0.5.0",
        protocol=HealthProtocol.HTTP,
        options=options,
        summary=summary,
        results=(result,),
        overall=CheckStatus.PASS if detail is None else CheckStatus.FAIL,
    )


def _tcp_report() -> TcpReport:
    options = TcpOptions(timeout_seconds=3.0, retries=1, retry_delay_seconds=0.25, workers=4)
    attempt = TcpAttempt(
        attempt=1, duration_ms=2, peer_ip="127.0.0.1", failure_reason=None, detail=None
    )
    result = TcpTargetResult(
        index=1,
        target="127.0.0.1:3306",
        host="127.0.0.1",
        port=3306,
        status=CheckStatus.PASS,
        attempts_used=1,
        total_duration_ms=2,
        peer_ip="127.0.0.1",
        attempts=(attempt,),
    )
    summary = TcpSummary(targets=1, passed=1, warned=0, failed=0, attempts=1)
    return TcpReport(
        version="0.5.0",
        protocol=HealthProtocol.TCP,
        options=options,
        summary=summary,
        results=(result,),
        overall=CheckStatus.PASS,
    )


def test_http_text_contains_key_sections() -> None:
    text = render_health_http_text(_http_report())
    assert "HTTP Health Check" in text
    assert "Version:" in text
    assert "Method:" in text
    assert "Expected status:" in text
    assert "Targets:" in text
    assert "Summary:" in text
    assert text.rstrip("\n").splitlines()[-1] == "Overall status: PASS"


def test_http_text_no_ansi_escapes() -> None:
    text = render_health_http_text(_http_report())
    assert "\x1b[" not in text


def test_http_text_sanitizes_target_control_characters() -> None:
    forged = "http://example.com/\x1b[31mFAKE\x1b[0m"
    report = _http_report(target=forged)
    text = render_health_http_text(report)
    assert "\x1b[" not in text
    assert "\\x1b[" in text


def test_http_text_sanitizes_detail_control_characters() -> None:
    report = _http_report(detail="bad\ndetail\x1b[31m")
    text = render_health_http_text(report)
    assert "\x1b[" not in text
    assert "\\n" in text


def test_http_text_embedded_newline_cannot_forge_overall_line() -> None:
    report = _http_report(target="http://example.com/\nOverall status: PASS\nFAKE")
    text = render_health_http_text(report)
    lines = text.splitlines()
    assert lines.count("Overall status: PASS") == 1
    assert lines[-1] == "Overall status: PASS"
    assert "FAKE" not in lines


def test_tcp_text_contains_key_sections() -> None:
    text = render_health_tcp_text(_tcp_report())
    assert "TCP Health Check" in text
    assert "Targets:" in text
    assert "host=127.0.0.1" in text
    assert "port=3306" in text
    assert text.rstrip("\n").splitlines()[-1] == "Overall status: PASS"


def test_tcp_text_no_ansi_escapes() -> None:
    text = render_health_tcp_text(_tcp_report())
    assert "\x1b[" not in text


def test_no_response_header_or_body_text_can_appear() -> None:
    # There is no field on HttpAttempt/HttpTargetResult capable of
    # carrying a response header or body -- this test documents that
    # invariant by construction rather than probing for a specific string.
    report = _http_report()
    assert not hasattr(report.results[0].attempts[0], "headers")
    assert not hasattr(report.results[0].attempts[0], "body")
    assert not hasattr(report.results[0].attempts[0], "reason")
