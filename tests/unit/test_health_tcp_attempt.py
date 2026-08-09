"""Single TCP attempt: connect-only behavior, peer IP, exception mapping.

Uses an injected fake in place of ``socket.create_connection`` -- no real
sockets. The fake raises if ``send``/``recv`` are ever called, proving the
connect-only guarantee structurally rather than merely by absence of a
positive test.
"""

from __future__ import annotations

import socket

import pytest

from maops_pydevops.core.health_models import TcpFailureReason
from maops_pydevops.core.health_tcp import _perform_tcp_attempt, validate_tcp_target


class _NoDataSocket:
    def __init__(self, peer_ip: str) -> None:
        self._peer_ip = peer_ip
        self.closed = False

    def getpeername(self) -> tuple[str, int]:
        return (self._peer_ip, 0)

    def send(self, *args: object, **kwargs: object) -> int:
        raise AssertionError("no application data may ever be sent on a TCP health check")

    def sendall(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("no application data may ever be sent on a TCP health check")

    def recv(self, *args: object, **kwargs: object) -> bytes:
        raise AssertionError("no banner may ever be read on a TCP health check")

    def close(self) -> None:
        self.closed = True


def _clock(*values: float) -> object:
    remaining = iter(values)
    return lambda: next(remaining)


def _target(raw: str = "127.0.0.1:8080"):
    target, error = validate_tcp_target(raw, index=1)
    assert error is None
    assert target is not None
    return target


def test_successful_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = _NoDataSocket("127.0.0.1")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: fake_socket)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.success is True
    assert outcome.retryable is False
    assert outcome.failure_reason is None
    assert outcome.detail is None
    assert outcome.peer_ip == "127.0.0.1"
    assert fake_socket.closed is True


def test_peer_ip_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = _NoDataSocket("203.0.113.9")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: fake_socket)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.peer_ip == "203.0.113.9"


def test_connection_refused_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(socket, "create_connection", _raise)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is TcpFailureReason.CONNECTION_REFUSED
    assert outcome.peer_ip is None


def test_timeout_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise TimeoutError("timed out")

    monkeypatch.setattr(socket, "create_connection", _raise)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.failure_reason is TcpFailureReason.TIMEOUT
    assert outcome.retryable is True


def test_dns_failure_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(socket, "create_connection", _raise)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.failure_reason is TcpFailureReason.DNS_ERROR
    assert outcome.retryable is True


def test_generic_os_error_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise OSError("network is unreachable")

    monkeypatch.setattr(socket, "create_connection", _raise)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert outcome.failure_reason is TcpFailureReason.CONNECTION_ERROR
    assert outcome.retryable is True


def test_malformed_label_hostname_encoding_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    # socket.getaddrinfo() always runs a str hostname through the idna
    # codec, even for purely-ASCII input -- an empty DNS label (a stray
    # double dot) raises UnicodeError from socket.create_connection(), not
    # an OSError subclass. This must degrade to a structured failure, not
    # crash the whole multi-target run.
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise UnicodeError("label empty or too long")

    monkeypatch.setattr(socket, "create_connection", _raise)
    outcome = _perform_tcp_attempt(
        _target("example..com:80"), timeout_seconds=3.0, clock=_clock(0.0, 0.002)
    )
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is TcpFailureReason.INVALID_TARGET_ENCODING
    assert outcome.peer_ip is None


def test_unexpected_programming_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> socket.socket:
        raise TypeError("programming error")

    monkeypatch.setattr(socket, "create_connection", _raise)
    with pytest.raises(TypeError):
        _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))


def test_socket_closed_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = _NoDataSocket("127.0.0.1")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: fake_socket)
    _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.002))
    assert fake_socket.closed is True


def test_duration_ms_is_integer_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = _NoDataSocket("127.0.0.1")
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: fake_socket)
    outcome = _perform_tcp_attempt(_target(), timeout_seconds=3.0, clock=_clock(0.0, 0.004))
    assert outcome.duration_ms == 4
    assert isinstance(outcome.duration_ms, int)


def test_timeout_value_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _capture(address: tuple[str, int], timeout: float | None = None) -> socket.socket:
        captured["address"] = address
        captured["timeout"] = timeout
        return _NoDataSocket("127.0.0.1")  # type: ignore[return-value]

    monkeypatch.setattr(socket, "create_connection", _capture)
    _perform_tcp_attempt(_target("example.com:443"), timeout_seconds=7.5, clock=_clock(0.0, 0.002))
    assert captured["address"] == ("example.com", 443)
    assert captured["timeout"] == 7.5
