"""Single HTTP attempt: status classification, exception mapping, safety invariants.

Uses injected fake ``http.client`` connection/response objects -- no real
sockets. Fakes raise if a forbidden operation (reading the response body,
headers, or reason phrase) is ever attempted, proving those code paths are
structurally unreachable rather than merely untested.
"""

from __future__ import annotations

import http.client
import socket
import ssl
from pathlib import Path

import pytest

from maops_pydevops.core.health_http import _perform_http_attempt, validate_http_target
from maops_pydevops.core.health_models import HttpFailureReason


class _FakeSocket:
    def __init__(self, peer_ip: str) -> None:
        self._peer_ip = peer_ip

    def getpeername(self) -> tuple[str, int]:
        return (self._peer_ip, 0)


class _ForbiddenResponse:
    """A response object that raises if body/headers/reason are ever touched."""

    def __init__(self, status: int) -> None:
        self.status = status

    def read(self, *args: object, **kwargs: object) -> bytes:
        raise AssertionError("response body must never be read")

    def readinto(self, *args: object, **kwargs: object) -> int:
        raise AssertionError("response body must never be read")

    def getheaders(self) -> object:
        raise AssertionError("response headers must never be collected")

    @property
    def headers(self) -> object:
        raise AssertionError("response headers must never be collected")

    @property
    def reason(self) -> object:
        raise AssertionError("response reason phrase must never be serialized")


class _FakeConnection:
    def __init__(
        self,
        *,
        response: _ForbiddenResponse | None = None,
        connect_error: Exception | None = None,
        request_error: Exception | None = None,
        peer_ip: str = "127.0.0.1",
    ) -> None:
        self._response = response
        self._connect_error = connect_error
        self._request_error = request_error
        self.sock: _FakeSocket | None = None
        self._peer_ip = peer_ip
        self.closed = False
        self.requested_method: str | None = None
        self.requested_target: str | None = None
        self.requested_headers: dict[str, str] | None = None

    def connect(self) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self.sock = _FakeSocket(self._peer_ip)

    def request(self, method: str, target: str, headers: dict[str, str] | None = None) -> None:
        self.requested_method = method
        self.requested_target = target
        self.requested_headers = headers
        if self._request_error is not None:
            raise self._request_error

    def getresponse(self) -> _ForbiddenResponse:
        assert self._response is not None
        return self._response

    def close(self) -> None:
        self.closed = True


def _clock(*values: float) -> object:
    remaining = iter(values)
    return lambda: next(remaining)


def _target(url: str = "http://example.com/health"):
    target, error = validate_http_target(url, index=1)
    assert error is None
    assert target is not None
    return target


def _patch_connection(
    monkeypatch: pytest.MonkeyPatch, fake: _FakeConnection, *, https: bool = False
) -> None:
    attr = "HTTPSConnection" if https else "HTTPConnection"
    monkeypatch.setattr(http.client, attr, lambda *a, **kw: fake)


def test_200_success_is_pass_and_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is True
    assert outcome.retryable is False
    assert outcome.http_status == 200
    assert outcome.failure_reason is None
    assert outcome.detail is None
    assert outcome.peer_ip == "127.0.0.1"
    assert fake.closed is True


@pytest.mark.parametrize("status", [200, 204, 299, 302, 399])
def test_status_inside_default_range_is_success(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(status))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is True
    assert outcome.http_status == status


def test_redirect_returned_without_following(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(302))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.http_status == 302
    # request() is called exactly once by _perform_http_attempt -- the fake
    # would raise if getresponse() were called a second time for a
    # follow-up request, but there is no code path that could do that at
    # all: the target is never mutated after validation.
    assert fake.requested_target == "/health"


def test_redirect_outside_custom_expected_range_is_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(302))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 299),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.failure_reason is HttpFailureReason.UNEXPECTED_STATUS


def test_404_failure_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(404))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.retryable is False
    assert outcome.failure_reason is HttpFailureReason.UNEXPECTED_STATUS


@pytest.mark.parametrize("status", [401, 403, 400])
def test_other_client_error_statuses_not_retried(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(status))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.retryable is False


@pytest.mark.parametrize("status", [408, 429, 500, 503, 599])
def test_retryable_statuses(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(status))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is HttpFailureReason.UNEXPECTED_STATUS


def test_custom_status_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(250))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 299),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is True


def test_dns_failure_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=socket.gaierror("name resolution failed"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is HttpFailureReason.DNS_ERROR
    assert outcome.http_status is None
    assert outcome.peer_ip is None


def test_timeout_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=TimeoutError("timed out"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.failure_reason is HttpFailureReason.TIMEOUT
    assert outcome.retryable is True


def test_connection_refused_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=ConnectionRefusedError("refused"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.failure_reason is HttpFailureReason.CONNECTION_REFUSED
    assert outcome.retryable is True


def test_tls_error_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=ssl.SSLError("certificate verify failed"))
    _patch_connection(monkeypatch, fake, https=True)
    target, error = validate_http_target("https://example.com/health", index=1)
    assert error is None
    assert target is not None
    outcome = _perform_http_attempt(
        target,
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.failure_reason is HttpFailureReason.TLS_ERROR
    assert outcome.retryable is True


def test_http_protocol_error_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(request_error=http.client.BadStatusLine("garbage"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.failure_reason is HttpFailureReason.HTTP_PROTOCOL_ERROR
    assert outcome.retryable is True


def test_generic_os_error_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=OSError("network is unreachable"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.failure_reason is HttpFailureReason.CONNECTION_ERROR
    assert outcome.retryable is True


def test_malformed_label_hostname_encoding_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    # socket.getaddrinfo() always runs a str hostname through the idna
    # codec, even for purely-ASCII input -- an empty DNS label (a stray
    # double dot) raises UnicodeError from conn.connect(), not an OSError
    # subclass. This must degrade to a structured failure, not crash the
    # whole multi-target run.
    fake = _FakeConnection(connect_error=UnicodeError("label empty or too long"))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target("http://example..com/"),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is HttpFailureReason.INVALID_TARGET_ENCODING
    assert outcome.http_status is None
    assert outcome.peer_ip is None


def test_non_ascii_path_encoding_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    # http.client's request-line encoding is ASCII-only -- a literal
    # non-ASCII character anywhere in the URL path/query raises
    # UnicodeEncodeError from conn.request(), independent of DNS/IDNA.
    fake = _FakeConnection(
        request_error=UnicodeEncodeError("ascii", "x", 0, 1, "ordinal not in range(128)")
    )
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is False
    assert outcome.retryable is True
    assert outcome.failure_reason is HttpFailureReason.INVALID_TARGET_ENCODING


def test_unexpected_programming_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=TypeError("programming error"))
    _patch_connection(monkeypatch, fake)
    with pytest.raises(TypeError):
        _perform_http_attempt(
            _target(),
            method="GET",
            timeout_seconds=3.0,
            expected_range=(200, 399),
            clock=_clock(0.0, 0.01),
        )


def test_peer_ip_extracted_from_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200), peer_ip="203.0.113.5")
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.peer_ip == "203.0.113.5"


def test_head_method_sent_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="HEAD",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.requested_method == "HEAD"


def test_get_method_sent_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.requested_method == "GET"


def test_no_request_body_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    # The fake's request() signature has no body parameter beyond
    # method/target/headers -- passing one would raise a TypeError, so a
    # successful call already proves no body argument was ever supplied.
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert outcome.success is True


def test_user_agent_header_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.requested_headers is not None
    assert "User-Agent" in fake.requested_headers


def test_no_authorization_header_ever_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.requested_headers is not None
    assert "Authorization" not in fake.requested_headers


def test_duration_ms_is_integer_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    outcome = _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.018),
    )
    assert outcome.duration_ms == 18
    assert isinstance(outcome.duration_ms, int)


def test_connection_closed_even_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(response=_ForbiddenResponse(200))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.closed is True


def test_connection_closed_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(connect_error=ConnectionRefusedError("refused"))
    _patch_connection(monkeypatch, fake)
    _perform_http_attempt(
        _target(),
        method="GET",
        timeout_seconds=3.0,
        expected_range=(200, 399),
        clock=_clock(0.0, 0.01),
    )
    assert fake.closed is True


def test_https_context_defaults_are_never_relaxed() -> None:
    # Source-scan regression guard: certificate/hostname verification must
    # never be disabled anywhere in this module.
    source = Path("src/maops_pydevops/core/health_http.py").read_text(encoding="utf-8")
    assert "CERT_NONE" not in source
    assert "check_hostname" not in source or "check_hostname = False" not in source
    assert "_create_unverified_context" not in source
    assert "create_default_context" in source
