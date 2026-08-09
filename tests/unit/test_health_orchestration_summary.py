"""``commands/health.py`` overall/summary computation across mixed target outcomes."""

from __future__ import annotations

import pytest

import maops_pydevops.core.health_http as health_http
import maops_pydevops.core.health_tcp as health_tcp
from maops_pydevops.commands.health import build_health_http_report, build_health_tcp_report
from maops_pydevops.core.health_http import _AttemptOutcome as HttpOutcome
from maops_pydevops.core.health_models import HttpMethod
from maops_pydevops.core.health_tcp import _AttemptOutcome as TcpOutcome


def test_mixed_pass_warn_fail_http_summary_and_overall(monkeypatch: pytest.MonkeyPatch) -> None:
    # target 1 -> PASS (succeeds first try), target 2 -> WARN (fails then
    # succeeds), target 3 -> FAIL (never succeeds).
    call_counts: dict[str, int] = {}

    def _scripted(target: object, **kwargs: object) -> HttpOutcome:
        hostname = target.hostname  # type: ignore[attr-defined]
        call_counts[hostname] = call_counts.get(hostname, 0) + 1
        if hostname == "pass.example":
            return HttpOutcome(
                success=True,
                http_status=200,
                peer_ip="127.0.0.1",
                failure_reason=None,
                detail=None,
                duration_ms=1,
                retryable=False,
            )
        if hostname == "warn.example":
            if call_counts[hostname] == 1:
                return HttpOutcome(
                    success=False,
                    http_status=503,
                    peer_ip="127.0.0.1",
                    failure_reason=health_http.HttpFailureReason.UNEXPECTED_STATUS,
                    detail="d",
                    duration_ms=1,
                    retryable=True,
                )
            return HttpOutcome(
                success=True,
                http_status=200,
                peer_ip="127.0.0.1",
                failure_reason=None,
                detail=None,
                duration_ms=1,
                retryable=False,
            )
        return HttpOutcome(
            success=False,
            http_status=None,
            peer_ip=None,
            failure_reason=health_http.HttpFailureReason.CONNECTION_REFUSED,
            detail="d",
            duration_ms=1,
            retryable=True,
        )

    monkeypatch.setattr(health_http, "_perform_http_attempt", _scripted)
    report, error = build_health_http_report(
        ["http://pass.example/", "http://warn.example/", "http://fail.example/"],
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=1.0,
        retries=1,
        retry_delay_seconds=0.01,
        workers=3,
    )
    assert error is None
    assert report is not None
    assert report.overall.value == "fail"
    assert report.summary.passed == 1
    assert report.summary.warned == 1
    assert report.summary.failed == 1
    assert report.summary.targets == 3


def test_all_pass_overall_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    def _ok(*args: object, **kwargs: object) -> HttpOutcome:
        return HttpOutcome(
            success=True,
            http_status=200,
            peer_ip="127.0.0.1",
            failure_reason=None,
            detail=None,
            duration_ms=1,
            retryable=False,
        )

    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    report, error = build_health_http_report(
        ["http://a.example/", "http://b.example/"],
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=1.0,
        retries=0,
        retry_delay_seconds=0.01,
        workers=2,
    )
    assert error is None
    assert report is not None
    assert report.overall.value == "pass"
    assert report.summary.failed == 0
    assert report.summary.warned == 0


def test_warn_only_no_fail_is_overall_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, int] = {}

    def _flaky_then_ok(target: object, **kwargs: object) -> HttpOutcome:
        calls["n"] = calls.get("n", 0) + 1
        if calls["n"] == 1:
            return HttpOutcome(
                success=False,
                http_status=503,
                peer_ip="127.0.0.1",
                failure_reason=health_http.HttpFailureReason.UNEXPECTED_STATUS,
                detail="d",
                duration_ms=1,
                retryable=True,
            )
        return HttpOutcome(
            success=True,
            http_status=200,
            peer_ip="127.0.0.1",
            failure_reason=None,
            detail=None,
            duration_ms=1,
            retryable=False,
        )

    monkeypatch.setattr(health_http, "_perform_http_attempt", _flaky_then_ok)
    report, error = build_health_http_report(
        ["http://a.example/"],
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=1.0,
        retries=1,
        retry_delay_seconds=0.01,
        workers=1,
    )
    assert error is None
    assert report is not None
    assert report.overall.value == "warn"
    assert report.summary.warned == 1
    assert report.summary.failed == 0


def test_mixed_pass_warn_fail_tcp_summary_and_overall(monkeypatch: pytest.MonkeyPatch) -> None:
    call_counts: dict[str, int] = {}

    def _scripted(target: object, **kwargs: object) -> TcpOutcome:
        host = target.host  # type: ignore[attr-defined]
        call_counts[host] = call_counts.get(host, 0) + 1
        if host == "pass.example":
            return TcpOutcome(
                success=True,
                peer_ip="127.0.0.1",
                failure_reason=None,
                detail=None,
                duration_ms=1,
                retryable=False,
            )
        if host == "warn.example":
            if call_counts[host] == 1:
                return TcpOutcome(
                    success=False,
                    peer_ip=None,
                    failure_reason=health_tcp.TcpFailureReason.CONNECTION_REFUSED,
                    detail="d",
                    duration_ms=1,
                    retryable=True,
                )
            return TcpOutcome(
                success=True,
                peer_ip="127.0.0.1",
                failure_reason=None,
                detail=None,
                duration_ms=1,
                retryable=False,
            )
        return TcpOutcome(
            success=False,
            peer_ip=None,
            failure_reason=health_tcp.TcpFailureReason.CONNECTION_REFUSED,
            detail="d",
            duration_ms=1,
            retryable=True,
        )

    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _scripted)
    report, error = build_health_tcp_report(
        ["pass.example:1", "warn.example:2", "fail.example:3"],
        timeout_seconds=1.0,
        retries=1,
        retry_delay_seconds=0.01,
        workers=3,
    )
    assert error is None
    assert report is not None
    assert report.overall.value == "fail"
    assert report.summary.passed == 1
    assert report.summary.warned == 1
    assert report.summary.failed == 1
