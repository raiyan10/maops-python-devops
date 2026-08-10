"""Assert the Python/JSON type of every documented health-report field."""

from __future__ import annotations

import json

import pytest

import maops_pydevops.core.health_http as health_http
import maops_pydevops.core.health_tcp as health_tcp
from maops_pydevops.commands.health import build_health_http_report, build_health_tcp_report
from maops_pydevops.core.health_http import _AttemptOutcome as HttpOutcome
from maops_pydevops.core.health_models import HttpMethod
from maops_pydevops.core.health_tcp import _AttemptOutcome as TcpOutcome


def _fail_http(*args: object, **kwargs: object) -> HttpOutcome:
    return HttpOutcome(
        success=False,
        http_status=None,
        peer_ip=None,
        failure_reason=health_http.HttpFailureReason.DNS_ERROR,
        detail="DNS resolution failed",
        duration_ms=3,
        retryable=True,
    )


def _fail_tcp(*args: object, **kwargs: object) -> TcpOutcome:
    return TcpOutcome(
        success=False,
        peer_ip=None,
        failure_reason=health_tcp.TcpFailureReason.CONNECTION_REFUSED,
        detail="connection refused",
        duration_ms=2,
        retryable=False,
    )


def test_http_report_json_field_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _fail_http)
    report, error = build_health_http_report(
        ["http://example.invalid/"],
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=1.0,
        retries=0,
        retry_delay_seconds=0.1,
        workers=1,
    )
    assert error is None
    assert report is not None
    data = json.loads(report.to_json())

    assert isinstance(data["version"], str)
    assert isinstance(data["protocol"], str)
    assert isinstance(data["options"], dict)
    options = data["options"]
    assert isinstance(options["method"], str)
    assert isinstance(options["expected_status_min"], int)
    assert isinstance(options["expected_status_max"], int)
    assert isinstance(options["timeout_seconds"], float)
    assert isinstance(options["retries"], int)
    assert isinstance(options["retry_delay_seconds"], float)
    assert isinstance(options["workers"], int)
    assert isinstance(options["follow_redirects"], bool)
    assert isinstance(options["tls_verify"], bool)
    assert isinstance(data["summary"], dict)
    summary = data["summary"]
    assert isinstance(summary["targets"], int)
    assert isinstance(summary["passed"], int)
    assert isinstance(summary["warned"], int)
    assert isinstance(summary["failed"], int)
    assert isinstance(summary["attempts"], int)
    assert isinstance(data["results"], list)

    result = data["results"][0]
    assert isinstance(result["index"], int)
    assert isinstance(result["target"], str)
    assert isinstance(result["status"], str)
    assert isinstance(result["attempts_used"], int)
    assert isinstance(result["total_duration_ms"], int)
    assert result["final_http_status"] is None
    assert result["peer_ip"] is None
    assert isinstance(result["attempts"], list)

    attempt = result["attempts"][0]
    assert isinstance(attempt["attempt"], int)
    assert isinstance(attempt["duration_ms"], int)
    assert attempt["http_status"] is None
    assert attempt["peer_ip"] is None
    assert attempt["failure_reason"] == "dns_error"
    assert isinstance(attempt["detail"], str)
    assert isinstance(data["overall"], str)


def test_tcp_report_json_field_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _fail_tcp)
    report, error = build_health_tcp_report(
        ["example.invalid:443"], timeout_seconds=1.0, retries=0, retry_delay_seconds=0.1, workers=1
    )
    assert error is None
    assert report is not None
    data = json.loads(report.to_json())

    assert isinstance(data["options"], dict)
    options = data["options"]
    assert isinstance(options["timeout_seconds"], float)
    assert isinstance(options["retries"], int)
    assert isinstance(options["retry_delay_seconds"], float)
    assert isinstance(options["workers"], int)
    assert isinstance(data["summary"], dict)
    summary = data["summary"]
    assert isinstance(summary["targets"], int)
    assert isinstance(summary["passed"], int)
    assert isinstance(summary["warned"], int)
    assert isinstance(summary["failed"], int)
    assert isinstance(summary["attempts"], int)

    result = data["results"][0]
    assert isinstance(result["host"], str)
    assert isinstance(result["port"], int)
    assert result["peer_ip"] is None

    attempt = result["attempts"][0]
    assert attempt["peer_ip"] is None
    assert attempt["failure_reason"] == "connection_refused"
    assert isinstance(attempt["detail"], str)


def test_http_success_has_null_failure_reason_and_detail(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ["http://example.invalid/"],
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=1.0,
        retries=0,
        retry_delay_seconds=0.1,
        workers=1,
    )
    assert error is None
    assert report is not None
    data = json.loads(report.to_json())
    attempt = data["results"][0]["attempts"][0]
    assert attempt["failure_reason"] is None
    assert attempt["detail"] is None
    assert attempt["http_status"] == 200
    assert attempt["peer_ip"] == "127.0.0.1"
