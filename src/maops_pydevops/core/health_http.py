"""Bounded, connect-only-adjacent HTTP availability checks.

One of two modules in this package permitted to make network connections
(the other is ``core/health_tcp.py``); the sole module permitted to import
``http.client``/``ssl`` for the HTTP path. Uses ``http.client`` directly,
never ``urllib.request`` -- ``urllib.request`` would consult
``HTTP_PROXY``/``HTTPS_PROXY`` and can follow redirects implicitly, neither
of which is wanted here. HTTPS always validates certificates and hostnames
via ``ssl.create_default_context()`` with zero attribute relaxation -- no
``--insecure`` option exists. A response's body is never read
(``.read()``/``.readinto()``/iteration are never called anywhere in this
module) and its headers/reason phrase are never accessed -- only the
status line and connection-level peer IP are ever extracted. Redirects are
never followed: a 3xx response is reported as-is, using the same
expected-status logic as any other status. See ``docs/http-health-safety.md``
for the full contract.
"""

from __future__ import annotations

import http.client
import re
import socket
import ssl
import time
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from maops_pydevops.core.health_models import (
    HttpAttempt,
    HttpFailureReason,
    HttpOptions,
    HttpTargetResult,
)
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.version import get_version

#: Raw C0 control characters or whitespace anywhere in a supplied URL are
#: rejected before any parsing is attempted. Percent-encoded sequences
#: (e.g. "%20") are unaffected -- only literal characters are checked.
_CONTROL_OR_WHITESPACE = re.compile(r"[\x00-\x1f\x7f\s]")

#: HTTP statuses that are always retried when outside --expect-status.
_RETRYABLE_STATUSES = frozenset({408, 429})


@dataclass(frozen=True)
class ValidatedHttpTarget:
    """One syntactically and semantically validated HTTP target."""

    index: int
    scheme: str
    hostname: str
    port: int | None
    request_target: str
    display_url: str


@dataclass(frozen=True)
class _AttemptOutcome:
    """Internal single-attempt result, before wrapping into a report model."""

    success: bool
    http_status: int | None
    peer_ip: str | None
    failure_reason: HttpFailureReason | None
    detail: str | None
    duration_ms: int
    retryable: bool

    def to_attempt(self, attempt_number: int) -> HttpAttempt:
        return HttpAttempt(
            attempt=attempt_number,
            duration_ms=self.duration_ms,
            http_status=self.http_status,
            peer_ip=self.peer_ip,
            failure_reason=self.failure_reason,
            detail=self.detail,
        )


def _redact_query(query: str) -> str:
    """Redact every query VALUE while preserving exact key text and order.

    Deliberately a manual ``split("&")``/``partition("=")`` transform
    rather than ``urllib.parse.parse_qsl``/``urlencode`` -- that would
    risk re-encoding or reordering keys; this is a direct, auditable
    string transform with no round-trip through a general query codec.
    """
    if not query:
        return ""
    segments: list[str] = []
    for pair in query.split("&"):
        if pair == "":
            continue
        key, sep, _value = pair.partition("=")
        segments.append(f"{key}={'[REDACTED]' if sep else ''}" if sep else key)
    return "&".join(segments)


def _build_display_url(scheme: str, hostname: str, port: int | None, path: str, query: str) -> str:
    """Build the only URL string ever stored on a validated target.

    Userinfo is never present (rejected earlier, at validation time) and
    the fragment is never included (read by the caller and discarded) --
    so this is the sole URL representation that ever reaches a report or
    text line; the original raw string supplied on the command line is
    never retained anywhere.
    """
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        netloc += f":{port}"
    url = f"{scheme}://{netloc}{path}"
    redacted_query = _redact_query(query)
    if redacted_query:
        url += f"?{redacted_query}"
    return url


def validate_http_target(raw: str, *, index: int) -> tuple[ValidatedHttpTarget | None, str | None]:
    """Validate and privacy-sanitize one CLI-supplied HTTP target string.

    Returns ``(target, None)`` on success or ``(None, error)`` on any
    validation failure -- callers must reject the whole invocation (exit
    2) before any target in the list is used to open a connection.
    """
    if _CONTROL_OR_WHITESPACE.search(raw):
        return None, f"target {index}: URL contains control characters or whitespace"

    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return None, f"target {index}: URL could not be parsed"

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        return None, f"target {index}: unsupported URL scheme"

    if "@" in parts.netloc:
        return None, f"target {index}: URL userinfo is not permitted"

    try:
        hostname = parts.hostname
    except ValueError:
        return None, f"target {index}: invalid URL host"
    if not hostname:
        return None, f"target {index}: URL host is required"

    try:
        port = parts.port
    except ValueError:
        return None, f"target {index}: invalid URL port"
    if port is not None and not (1 <= port <= 65535):
        return None, f"target {index}: URL port out of range"

    path = parts.path or "/"
    request_target = path + (f"?{parts.query}" if parts.query else "")
    display_url = _build_display_url(scheme, hostname, port, path, parts.query)

    target = ValidatedHttpTarget(
        index=index,
        scheme=scheme,
        hostname=hostname,
        port=port,
        request_target=request_target,
        display_url=display_url,
    )
    return target, None


def _peer_ip(conn: http.client.HTTPConnection) -> str | None:
    sock = conn.sock
    if sock is None:
        return None
    try:
        return str(sock.getpeername()[0])
    except OSError:
        return None


def _duration_ms(clock: Callable[[], float], start: float) -> int:
    return max(0, round((clock() - start) * 1000))


def _outcome(
    reason: HttpFailureReason, detail: str, clock: Callable[[], float], start: float
) -> _AttemptOutcome:
    """Build a failed, always-retryable transport-layer outcome.

    Every exception this module catches (DNS, timeout, refused, TLS,
    protocol, generic connection error) is a transport-layer failure and
    is always retryable -- only an ``unexpected_status`` outcome (built
    separately, after a successful ``getresponse()``) has conditional
    retryability.
    """
    return _AttemptOutcome(
        success=False,
        http_status=None,
        peer_ip=None,
        failure_reason=reason,
        detail=detail,
        duration_ms=_duration_ms(clock, start),
        retryable=True,
    )


def _perform_http_attempt(
    target: ValidatedHttpTarget,
    *,
    method: str,
    timeout_seconds: float,
    expected_range: tuple[int, int],
    clock: Callable[[], float],
) -> _AttemptOutcome:
    """Perform exactly one HTTP attempt. Never reads a response body.

    Only the exceptions in the ``except`` clauses below are converted
    into a structured failure -- order is load-bearing, since
    ``ConnectionRefusedError``, ``TimeoutError``, ``ssl.SSLError``, and
    ``http.client.HTTPException`` are all ``OSError`` subclasses and must
    be listed before the generic ``OSError`` catch. ``UnicodeError`` is a
    separate, non-``OSError`` hierarchy raised by two distinct stdlib call
    sites reachable from ordinary (non-malicious) operator input, not a
    programming error: ``conn.connect()`` runs a ``str`` hostname through
    the ``idna`` codec unconditionally, so a malformed label (an empty
    segment from a stray double dot, an over-length label) raises
    ``UnicodeError`` even for purely-ASCII input; ``conn.request(...)``
    requires the full request line to be ASCII, so a literal non-ASCII
    character anywhere in the URL path/query raises ``UnicodeEncodeError``
    (a ``UnicodeError`` subclass). Any other exception (a genuine
    programming error) propagates uncaught.
    """
    start = clock()
    conn: http.client.HTTPConnection | None = None
    headers = {"User-Agent": f"maops-py/{get_version()}"}
    try:
        if target.scheme == "https":
            context = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                target.hostname, target.port, timeout=timeout_seconds, context=context
            )
        else:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=timeout_seconds)
        # Connect explicitly (rather than letting request() connect
        # implicitly) so the peer IP can be captured right after the
        # TCP/TLS handshake completes. getresponse() closes the
        # connection internally -- setting conn.sock back to None --
        # whenever the response indicates it won't be kept alive (e.g.
        # any HTTP/1.0 response without explicit keep-alive), which is
        # common enough that reading peer_ip only after getresponse()
        # would silently lose it for a large share of real servers.
        conn.connect()
        peer_ip = _peer_ip(conn)
        conn.request(method, target.request_target, headers=headers)
        response = conn.getresponse()
        http_status = response.status
        duration_ms = _duration_ms(clock, start)
        low, high = expected_range
        if low <= http_status <= high:
            return _AttemptOutcome(
                success=True,
                http_status=http_status,
                peer_ip=peer_ip,
                failure_reason=None,
                detail=None,
                duration_ms=duration_ms,
                retryable=False,
            )
        retryable = http_status in _RETRYABLE_STATUSES or 500 <= http_status <= 599
        return _AttemptOutcome(
            success=False,
            http_status=http_status,
            peer_ip=peer_ip,
            failure_reason=HttpFailureReason.UNEXPECTED_STATUS,
            detail="HTTP status was outside the expected range",
            duration_ms=duration_ms,
            retryable=retryable,
        )
    except socket.gaierror:
        return _outcome(HttpFailureReason.DNS_ERROR, "DNS resolution failed", clock, start)
    except UnicodeError:
        return _outcome(
            HttpFailureReason.INVALID_TARGET_ENCODING,
            "target hostname or path could not be encoded",
            clock,
            start,
        )
    except TimeoutError:
        return _outcome(HttpFailureReason.TIMEOUT, "connection or read timed out", clock, start)
    except ConnectionRefusedError:
        return _outcome(HttpFailureReason.CONNECTION_REFUSED, "connection refused", clock, start)
    except ssl.SSLError:
        return _outcome(
            HttpFailureReason.TLS_ERROR,
            "TLS handshake or certificate verification failed",
            clock,
            start,
        )
    except http.client.HTTPException:
        return _outcome(
            HttpFailureReason.HTTP_PROTOCOL_ERROR,
            "malformed or unexpected HTTP response",
            clock,
            start,
        )
    except OSError:
        return _outcome(HttpFailureReason.CONNECTION_ERROR, "connection error", clock, start)
    finally:
        if conn is not None:
            conn.close()


def _derive_target_status(attempts: Sequence[HttpAttempt]) -> CheckStatus:
    if attempts[0].failure_reason is None:
        return CheckStatus.PASS
    if any(attempt.failure_reason is None for attempt in attempts[1:]):
        return CheckStatus.WARN
    return CheckStatus.FAIL


def run_http_target_with_retries(
    target: ValidatedHttpTarget,
    *,
    options: HttpOptions,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> HttpTargetResult:
    """Run one target's full attempt sequence: ``attempts = retries + 1``.

    Retries happen entirely within this function, sequentially -- this is
    the whole callable a worker thread runs once. Never sleeps after the
    final attempt.
    """
    attempts: list[HttpAttempt] = []
    max_attempts = options.retries + 1
    total_start = clock()
    for attempt_number in range(1, max_attempts + 1):
        outcome = _perform_http_attempt(
            target,
            method=options.method.value,
            timeout_seconds=options.timeout_seconds,
            expected_range=(options.expected_status_min, options.expected_status_max),
            clock=clock,
        )
        attempts.append(outcome.to_attempt(attempt_number))
        if outcome.success or not outcome.retryable:
            break
        if attempt_number == max_attempts:
            break
        sleep(options.retry_delay_seconds)

    total_duration_ms = _duration_ms(clock, total_start)
    status = _derive_target_status(attempts)
    final = attempts[-1]
    return HttpTargetResult(
        index=target.index,
        target=target.display_url,
        status=status,
        attempts_used=len(attempts),
        total_duration_ms=total_duration_ms,
        final_http_status=final.http_status,
        peer_ip=final.peer_ip,
        attempts=tuple(attempts),
    )
