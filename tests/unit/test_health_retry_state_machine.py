"""Deterministic retry state machine: attempt counts, sleep injection, PASS/WARN/FAIL.

Exercises ``run_http_target_with_retries``/``run_tcp_target_with_retries``
with the single-attempt primitive monkeypatched to return scripted
outcomes, and injected ``sleep``/``clock`` collaborators -- no real time
or network involved.
"""

from __future__ import annotations

import pytest

import maops_pydevops.core.health_http as health_http
import maops_pydevops.core.health_tcp as health_tcp
from maops_pydevops.core.health_http import ValidatedHttpTarget, run_http_target_with_retries
from maops_pydevops.core.health_http import _AttemptOutcome as HttpOutcome
from maops_pydevops.core.health_models import (
    HttpFailureReason,
    HttpMethod,
    HttpOptions,
    TcpFailureReason,
    TcpOptions,
)
from maops_pydevops.core.health_tcp import ValidatedTcpTarget, run_tcp_target_with_retries
from maops_pydevops.core.health_tcp import _AttemptOutcome as TcpOutcome
from maops_pydevops.core.models import CheckStatus


def _http_target() -> ValidatedHttpTarget:
    return ValidatedHttpTarget(
        index=1,
        scheme="http",
        hostname="example.com",
        port=None,
        request_target="/",
        display_url="http://example.com/",
    )


def _tcp_target() -> ValidatedTcpTarget:
    return ValidatedTcpTarget(index=1, host="example.com", port=443, display="example.com:443")


def _http_options(*, retries: int = 1, retry_delay_seconds: float = 0.25) -> HttpOptions:
    return HttpOptions(
        method=HttpMethod.GET,
        expected_status_min=200,
        expected_status_max=399,
        timeout_seconds=3.0,
        retries=retries,
        retry_delay_seconds=retry_delay_seconds,
        workers=1,
        follow_redirects=False,
        tls_verify=True,
    )


def _tcp_options(*, retries: int = 1, retry_delay_seconds: float = 0.25) -> TcpOptions:
    return TcpOptions(
        timeout_seconds=3.0, retries=retries, retry_delay_seconds=retry_delay_seconds, workers=1
    )


def _success_http() -> HttpOutcome:
    return HttpOutcome(
        success=True,
        http_status=200,
        peer_ip="127.0.0.1",
        failure_reason=None,
        detail=None,
        duration_ms=1,
        retryable=False,
    )


def _retryable_failure_http() -> HttpOutcome:
    return HttpOutcome(
        success=False,
        http_status=503,
        peer_ip="127.0.0.1",
        failure_reason=HttpFailureReason.UNEXPECTED_STATUS,
        detail="d",
        duration_ms=1,
        retryable=True,
    )


def _non_retryable_failure_http() -> HttpOutcome:
    return HttpOutcome(
        success=False,
        http_status=404,
        peer_ip="127.0.0.1",
        failure_reason=HttpFailureReason.UNEXPECTED_STATUS,
        detail="d",
        duration_ms=1,
        retryable=False,
    )


def _success_tcp() -> TcpOutcome:
    return TcpOutcome(
        success=True,
        peer_ip="127.0.0.1",
        failure_reason=None,
        detail=None,
        duration_ms=1,
        retryable=False,
    )


def _retryable_failure_tcp() -> TcpOutcome:
    return TcpOutcome(
        success=False,
        peer_ip=None,
        failure_reason=TcpFailureReason.CONNECTION_REFUSED,
        detail="d",
        duration_ms=1,
        retryable=True,
    )


def _scripted_http(monkeypatch: pytest.MonkeyPatch, outcomes: list[HttpOutcome]) -> list[int]:
    calls: list[int] = []

    def _fake(
        target: object,
        *,
        method: object,
        timeout_seconds: object,
        expected_range: object,
        clock: object,
    ) -> HttpOutcome:
        calls.append(1)
        return outcomes.pop(0)

    monkeypatch.setattr(health_http, "_perform_http_attempt", _fake)
    return calls


def _scripted_tcp(monkeypatch: pytest.MonkeyPatch, outcomes: list[TcpOutcome]) -> list[int]:
    calls: list[int] = []

    def _fake(target: object, *, timeout_seconds: object, clock: object) -> TcpOutcome:
        calls.append(1)
        return outcomes.pop(0)

    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _fake)
    return calls


def test_retries_0_means_one_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _scripted_http(monkeypatch, [_retryable_failure_http()])
    sleep_calls: list[float] = []
    result = run_http_target_with_retries(
        _http_target(),
        options=_http_options(retries=0),
        sleep=sleep_calls.append,
        clock=iter([0.0, 0.01]).__next__,
    )
    assert len(calls) == 1
    assert result.attempts_used == 1
    assert sleep_calls == []


def test_retries_n_means_maximum_n_plus_1_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [_retryable_failure_http() for _ in range(4)]
    calls = _scripted_http(monkeypatch, outcomes)
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=3), sleep=sleep_calls.append, clock=clock
    )
    assert len(calls) == 4
    assert result.attempts_used == 4
    assert result.status is CheckStatus.FAIL


def test_no_sleep_after_final_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [_retryable_failure_http(), _retryable_failure_http()]
    _scripted_http(monkeypatch, outcomes)
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    run_http_target_with_retries(
        _http_target(), options=_http_options(retries=1), sleep=sleep_calls.append, clock=clock
    )
    # 2 attempts total (retries=1) -- exactly 1 sleep between them, never
    # a sleep after the second (final) attempt.
    assert sleep_calls == [0.25]


def test_no_sleep_after_immediate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_http(monkeypatch, [_success_http()])
    sleep_calls: list[float] = []
    clock = iter([0.0, 0.01]).__next__
    run_http_target_with_retries(
        _http_target(), options=_http_options(retries=3), sleep=sleep_calls.append, clock=clock
    )
    assert sleep_calls == []


def test_fixed_delay_called_exact_number_of_times(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [_retryable_failure_http() for _ in range(5)]
    _scripted_http(monkeypatch, outcomes)
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    run_http_target_with_retries(
        _http_target(),
        options=_http_options(retries=4, retry_delay_seconds=0.5),
        sleep=sleep_calls.append,
        clock=clock,
    )
    assert sleep_calls == [0.5, 0.5, 0.5, 0.5]


def test_expected_status_short_circuits_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _scripted_http(monkeypatch, [_success_http()])
    sleep_calls: list[float] = []
    clock = iter([0.0, 0.01]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=3), sleep=sleep_calls.append, clock=clock
    )
    assert len(calls) == 1
    assert result.status is CheckStatus.PASS


def test_non_retriable_status_short_circuits_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _scripted_http(monkeypatch, [_non_retryable_failure_http()])
    sleep_calls: list[float] = []
    clock = iter([0.0, 0.01]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=3), sleep=sleep_calls.append, clock=clock
    )
    assert len(calls) == 1
    assert sleep_calls == []
    assert result.status is CheckStatus.FAIL


def test_first_attempt_success_is_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_http(monkeypatch, [_success_http()])
    clock = iter([0.0, 0.01]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=1), sleep=lambda s: None, clock=clock
    )
    assert result.status is CheckStatus.PASS


def test_fail_then_success_is_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_http(monkeypatch, [_retryable_failure_http(), _success_http()])
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=1), sleep=lambda s: None, clock=clock
    )
    assert result.status is CheckStatus.WARN


def test_exhausted_retries_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_http(monkeypatch, [_retryable_failure_http(), _retryable_failure_http()])
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=1), sleep=lambda s: None, clock=clock
    )
    assert result.status is CheckStatus.FAIL


def test_retries_5_is_true_maximum_six_attempts_never_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --retries is bounded to 0-5 by _parse_retries (cli.py); 5 is the true
    # documented ceiling (attempts = retries + 1 = 6). Every prior test in
    # this file scripts at most 4 retries and none asserts exhaustion at
    # the real maximum.
    outcomes = [_retryable_failure_http() for _ in range(6)]
    calls = _scripted_http(monkeypatch, outcomes)
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_http_target_with_retries(
        _http_target(),
        options=_http_options(retries=5, retry_delay_seconds=0.5),
        sleep=sleep_calls.append,
        clock=clock,
    )
    assert len(calls) == 6
    assert result.attempts_used == 6
    assert result.status is CheckStatus.FAIL
    assert sleep_calls == [0.5, 0.5, 0.5, 0.5, 0.5]


def test_tcp_retries_5_is_true_maximum_six_attempts_never_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = [_retryable_failure_tcp() for _ in range(6)]
    calls = _scripted_tcp(monkeypatch, outcomes)
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_tcp_target_with_retries(
        _tcp_target(),
        options=_tcp_options(retries=5, retry_delay_seconds=0.5),
        sleep=sleep_calls.append,
        clock=clock,
    )
    assert len(calls) == 6
    assert result.attempts_used == 6
    assert result.status is CheckStatus.FAIL
    assert sleep_calls == [0.5, 0.5, 0.5, 0.5, 0.5]


def test_tcp_retries_0_means_one_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _scripted_tcp(monkeypatch, [_retryable_failure_tcp()])
    result = run_tcp_target_with_retries(
        _tcp_target(),
        options=_tcp_options(retries=0),
        sleep=lambda s: None,
        clock=iter([0.0, 0.01]).__next__,
    )
    assert len(calls) == 1
    assert result.status is CheckStatus.FAIL


def test_tcp_retry_recovery_is_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_tcp(monkeypatch, [_retryable_failure_tcp(), _success_tcp()])
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_tcp_target_with_retries(
        _tcp_target(), options=_tcp_options(retries=1), sleep=lambda s: None, clock=clock
    )
    assert result.status is CheckStatus.WARN


def test_tcp_retry_exhaustion_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_tcp(monkeypatch, [_retryable_failure_tcp(), _retryable_failure_tcp()])
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_tcp_target_with_retries(
        _tcp_target(), options=_tcp_options(retries=1), sleep=lambda s: None, clock=clock
    )
    assert result.status is CheckStatus.FAIL


def test_tcp_no_sleep_after_final_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_tcp(monkeypatch, [_retryable_failure_tcp(), _retryable_failure_tcp()])
    sleep_calls: list[float] = []
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    run_tcp_target_with_retries(
        _tcp_target(), options=_tcp_options(retries=1), sleep=sleep_calls.append, clock=clock
    )
    assert sleep_calls == [0.25]


def test_attempts_used_matches_attempts_list_length(monkeypatch: pytest.MonkeyPatch) -> None:
    _scripted_http(monkeypatch, [_retryable_failure_http(), _success_http()])
    clock = iter([float(i) * 0.01 for i in range(20)]).__next__
    result = run_http_target_with_retries(
        _http_target(), options=_http_options(retries=3), sleep=lambda s: None, clock=clock
    )
    assert result.attempts_used == len(result.attempts) == 2
