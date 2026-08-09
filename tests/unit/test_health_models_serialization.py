"""Explicit serialization of every health model: to_dict()/to_json(), explicit nulls."""

from __future__ import annotations

import json
from pathlib import Path

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
    TcpFailureReason,
    TcpOptions,
    TcpReport,
    TcpSummary,
    TcpTargetResult,
)
from maops_pydevops.core.models import CheckStatus


def _http_report() -> HttpReport:
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
    attempt_ok = HttpAttempt(
        attempt=1,
        duration_ms=5,
        http_status=200,
        peer_ip="127.0.0.1",
        failure_reason=None,
        detail=None,
    )
    attempt_fail = HttpAttempt(
        attempt=1,
        duration_ms=3,
        http_status=None,
        peer_ip=None,
        failure_reason=HttpFailureReason.DNS_ERROR,
        detail="DNS resolution failed",
    )
    result_ok = HttpTargetResult(
        index=1,
        target="http://example.com/",
        status=CheckStatus.PASS,
        attempts_used=1,
        total_duration_ms=5,
        final_http_status=200,
        peer_ip="127.0.0.1",
        attempts=(attempt_ok,),
    )
    result_fail = HttpTargetResult(
        index=2,
        target="http://bad.example/",
        status=CheckStatus.FAIL,
        attempts_used=1,
        total_duration_ms=3,
        final_http_status=None,
        peer_ip=None,
        attempts=(attempt_fail,),
    )
    summary = HttpSummary(targets=2, passed=1, warned=0, failed=1, attempts=2)
    return HttpReport(
        version="0.5.0",
        protocol=HealthProtocol.HTTP,
        options=options,
        summary=summary,
        results=(result_ok, result_fail),
        overall=CheckStatus.FAIL,
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


def test_http_report_to_dict_field_shape() -> None:
    report = _http_report()
    data = report.to_dict()
    assert data["version"] == "0.5.0"
    assert data["protocol"] == "http"
    assert data["overall"] == "fail"
    assert data["options"]["method"] == "GET"
    assert data["summary"]["targets"] == 2
    assert len(data["results"]) == 2
    assert data["results"][1]["peer_ip"] is None
    assert data["results"][1]["final_http_status"] is None
    assert data["results"][1]["attempts"][0]["failure_reason"] == "dns_error"


def test_http_report_to_json_round_trips_through_to_dict() -> None:
    report = _http_report()
    assert json.loads(report.to_json()) == report.to_dict()


def test_tcp_report_to_dict_field_shape() -> None:
    report = _tcp_report()
    data = report.to_dict()
    assert data["protocol"] == "tcp"
    assert data["results"][0]["host"] == "127.0.0.1"
    assert data["results"][0]["port"] == 3306
    assert data["options"] == {
        "timeout_seconds": 3.0,
        "retries": 1,
        "retry_delay_seconds": 0.25,
        "workers": 4,
    }


def test_tcp_report_to_json_round_trips_through_to_dict() -> None:
    report = _tcp_report()
    assert json.loads(report.to_json()) == report.to_dict()


def test_http_attempt_success_has_explicit_nulls() -> None:
    attempt = HttpAttempt(
        attempt=1,
        duration_ms=1,
        http_status=200,
        peer_ip="1.2.3.4",
        failure_reason=None,
        detail=None,
    )
    data = attempt.to_dict()
    assert data["failure_reason"] is None
    assert data["detail"] is None
    assert "failure_reason" in data
    assert "detail" in data


def test_tcp_attempt_failure_serializes_enum_value() -> None:
    attempt = TcpAttempt(
        attempt=2,
        duration_ms=4,
        peer_ip=None,
        failure_reason=TcpFailureReason.CONNECTION_REFUSED,
        detail="connection refused",
    )
    data = attempt.to_dict()
    assert data["failure_reason"] == "connection_refused"
    assert data["peer_ip"] is None


def test_no_dataclasses_asdict_used_in_health_models() -> None:
    source = Path("src/maops_pydevops/core/health_models.py").read_text(encoding="utf-8")
    assert "asdict" not in source


def test_no_dataclasses_asdict_used_anywhere_in_health_modules() -> None:
    for name in ("health_http.py", "health_tcp.py", "health_runner.py", "health_models.py"):
        source = Path(f"src/maops_pydevops/core/{name}").read_text(encoding="utf-8")
        assert "asdict" not in source, name
    source = Path("src/maops_pydevops/commands/health.py").read_text(encoding="utf-8")
    assert "asdict" not in source
