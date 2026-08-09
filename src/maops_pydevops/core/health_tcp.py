"""Bounded, connect-only TCP availability checks.

One of two modules in this package permitted to make network connections
(the other is ``core/health_http.py``); the sole module permitted to
import ``socket`` for the TCP path. Every attempt is exactly
``socket.create_connection(...)`` followed by ``getpeername()`` and
``close()`` -- no application data is ever sent, no banner is ever read,
and no TLS handshake is ever performed for a generic TCP check. See
``docs/http-health-safety.md`` and ``docs/health-checks.md`` for the full
contract.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from maops_pydevops.core.health_models import (
    TcpAttempt,
    TcpFailureReason,
    TcpOptions,
    TcpTargetResult,
)
from maops_pydevops.core.models import CheckStatus

#: Raw C0 control characters or whitespace anywhere in a supplied target
#: are rejected before any parsing is attempted.
_CONTROL_OR_WHITESPACE = re.compile(r"[\x00-\x1f\x7f\s]")

#: ``[host]:port`` -- host is validated as a genuine IPv6 literal below.
_BRACKETED_IPV6_RE = re.compile(r"^\[(?P<host>[0-9A-Fa-f:]+)\]:(?P<port>\d{1,5})$")

#: ``host:port`` for a hostname or IPv4 literal. The host class excludes
#: ``:``, ``/``, and whitespace, so this alone structurally rejects an
#: unbracketed IPv6 literal (embedded colons), CIDR notation (``/``), and
#: -- combined with the anchored full match -- comma-separated ports and
#: port ranges: none of those can match this pattern at all.
_HOST_PORT_RE = re.compile(r"^(?P<host>[^:\s/]+):(?P<port>\d{1,5})$")


@dataclass(frozen=True)
class ValidatedTcpTarget:
    """One syntactically and semantically validated TCP target."""

    index: int
    host: str
    port: int
    display: str


@dataclass(frozen=True)
class _AttemptOutcome:
    """Internal single-attempt result, before wrapping into a report model."""

    success: bool
    peer_ip: str | None
    failure_reason: TcpFailureReason | None
    detail: str | None
    duration_ms: int
    retryable: bool

    def to_attempt(self, attempt_number: int) -> TcpAttempt:
        return TcpAttempt(
            attempt=attempt_number,
            duration_ms=self.duration_ms,
            peer_ip=self.peer_ip,
            failure_reason=self.failure_reason,
            detail=self.detail,
        )


def validate_tcp_target(raw: str, *, index: int) -> tuple[ValidatedTcpTarget | None, str | None]:
    """Validate one CLI-supplied ``host:port`` / ``IPv4:port`` / ``[IPv6]:port`` target.

    Returns ``(target, None)`` on success or ``(None, error)`` on any
    validation failure -- callers must reject the whole invocation (exit
    2) before any target in the list is used to open a connection.
    """
    if _CONTROL_OR_WHITESPACE.search(raw):
        return None, f"target {index}: target contains control characters or whitespace"

    if raw.startswith("["):
        bracket_match = _BRACKETED_IPV6_RE.match(raw)
        if bracket_match is None:
            return None, f"target {index}: invalid bracketed IPv6 target syntax"
        host = bracket_match.group("host")
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None, f"target {index}: invalid IPv6 address"
        port_str = bracket_match.group("port")
    else:
        host_port_match = _HOST_PORT_RE.match(raw)
        if host_port_match is None:
            return None, f"target {index}: invalid target syntax, expected host:port"
        host = host_port_match.group("host")
        port_str = host_port_match.group("port")

    port = int(port_str)
    if not (1 <= port <= 65535):
        return None, f"target {index}: port out of range"

    return ValidatedTcpTarget(index=index, host=host, port=port, display=raw), None


def _duration_ms(clock: Callable[[], float], start: float) -> int:
    return max(0, round((clock() - start) * 1000))


def _outcome(
    reason: TcpFailureReason, detail: str, clock: Callable[[], float], start: float
) -> _AttemptOutcome:
    return _AttemptOutcome(
        success=False,
        peer_ip=None,
        failure_reason=reason,
        detail=detail,
        duration_ms=_duration_ms(clock, start),
        retryable=True,
    )


def _perform_tcp_attempt(
    target: ValidatedTcpTarget, *, timeout_seconds: float, clock: Callable[[], float]
) -> _AttemptOutcome:
    """Perform exactly one connect-only TCP attempt.

    The function body contains exactly ``create_connection`` ->
    ``getpeername()`` -> (implicit) ``close()`` -- no ``send``/``recv``/
    ``sendall`` is ever called. Only the exceptions in the ``except``
    clauses below are converted into a structured failure. ``UnicodeError``
    is caught separately from the ``OSError`` family below: ``str`` hosts
    are always run through the ``idna`` codec by ``socket.getaddrinfo()``,
    so a malformed label (e.g. an empty segment from a stray double dot)
    raises ``UnicodeError`` for ordinary, non-malicious operator input, not
    a programming error. Any other exception (a genuine programming error)
    propagates uncaught.
    """
    start = clock()
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((target.host, target.port), timeout=timeout_seconds)
        peer_ip = str(sock.getpeername()[0])
        return _AttemptOutcome(
            success=True,
            peer_ip=peer_ip,
            failure_reason=None,
            detail=None,
            duration_ms=_duration_ms(clock, start),
            retryable=False,
        )
    except socket.gaierror:
        return _outcome(TcpFailureReason.DNS_ERROR, "DNS resolution failed", clock, start)
    except UnicodeError:
        return _outcome(
            TcpFailureReason.INVALID_TARGET_ENCODING,
            "target hostname could not be encoded",
            clock,
            start,
        )
    except TimeoutError:
        return _outcome(TcpFailureReason.TIMEOUT, "connection timed out", clock, start)
    except ConnectionRefusedError:
        return _outcome(TcpFailureReason.CONNECTION_REFUSED, "connection refused", clock, start)
    except OSError:
        return _outcome(TcpFailureReason.CONNECTION_ERROR, "connection error", clock, start)
    finally:
        if sock is not None:
            sock.close()


def _derive_target_status(attempts: Sequence[TcpAttempt]) -> CheckStatus:
    if attempts[0].failure_reason is None:
        return CheckStatus.PASS
    if any(attempt.failure_reason is None for attempt in attempts[1:]):
        return CheckStatus.WARN
    return CheckStatus.FAIL


def run_tcp_target_with_retries(
    target: ValidatedTcpTarget,
    *,
    options: TcpOptions,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> TcpTargetResult:
    """Run one target's full attempt sequence: ``attempts = retries + 1``.

    Retries happen entirely within this function, sequentially -- this is
    the whole callable a worker thread runs once. Never sleeps after the
    final attempt.
    """
    attempts: list[TcpAttempt] = []
    max_attempts = options.retries + 1
    total_start = clock()
    for attempt_number in range(1, max_attempts + 1):
        outcome = _perform_tcp_attempt(target, timeout_seconds=options.timeout_seconds, clock=clock)
        attempts.append(outcome.to_attempt(attempt_number))
        if outcome.success or not outcome.retryable:
            break
        if attempt_number == max_attempts:
            break
        sleep(options.retry_delay_seconds)

    total_duration_ms = _duration_ms(clock, total_start)
    status = _derive_target_status(attempts)
    final = attempts[-1]
    return TcpTargetResult(
        index=target.index,
        target=target.display,
        host=target.host,
        port=target.port,
        status=status,
        attempts_used=len(attempts),
        total_duration_ms=total_duration_ms,
        peer_ip=final.peer_ip,
        attempts=tuple(attempts),
    )
