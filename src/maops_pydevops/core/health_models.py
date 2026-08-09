"""Typed data models for HTTP and TCP health checks.

Every optional field is explicit ``X | None`` and always present in
``to_dict()`` -- never omitted. Enum values match their CLI-facing
spelling exactly: :class:`HttpMethod` is uppercase (``--method`` is
CLI-spelled uppercase), every other enum here is lowercase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from maops_pydevops.core.models import CheckStatus


class HealthProtocol(StrEnum):
    """Which health-check protocol a report describes."""

    HTTP = "http"
    TCP = "tcp"


class HttpMethod(StrEnum):
    """Supported HTTP request methods. Uppercase to match ``--method``."""

    GET = "GET"
    HEAD = "HEAD"


class HttpFailureReason(StrEnum):
    """Closed set of deterministic HTTP attempt failure reasons."""

    DNS_ERROR = "dns_error"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_ERROR = "connection_error"
    TLS_ERROR = "tls_error"
    HTTP_PROTOCOL_ERROR = "http_protocol_error"
    UNEXPECTED_STATUS = "unexpected_status"
    INVALID_TARGET_ENCODING = "invalid_target_encoding"


class TcpFailureReason(StrEnum):
    """Closed set of deterministic TCP attempt failure reasons."""

    DNS_ERROR = "dns_error"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_ERROR = "connection_error"
    INVALID_TARGET_ENCODING = "invalid_target_encoding"


@dataclass(frozen=True)
class HttpOptions:
    """The effective options in force for a ``health http`` run."""

    method: HttpMethod
    expected_status_min: int
    expected_status_max: int
    timeout_seconds: float
    retries: int
    retry_delay_seconds: float
    workers: int
    follow_redirects: bool
    tls_verify: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method.value,
            "expected_status_min": self.expected_status_min,
            "expected_status_max": self.expected_status_max,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "workers": self.workers,
            "follow_redirects": self.follow_redirects,
            "tls_verify": self.tls_verify,
        }


@dataclass(frozen=True)
class HttpAttempt:
    """One HTTP connection attempt for a single target."""

    attempt: int
    duration_ms: int
    http_status: int | None
    peer_ip: str | None
    failure_reason: HttpFailureReason | None
    detail: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "duration_ms": self.duration_ms,
            "http_status": self.http_status,
            "peer_ip": self.peer_ip,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HttpTargetResult:
    """The retry-sequence outcome for one HTTP target."""

    index: int
    target: str
    status: CheckStatus
    attempts_used: int
    total_duration_ms: int
    final_http_status: int | None
    peer_ip: str | None
    attempts: tuple[HttpAttempt, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "target": self.target,
            "status": self.status.value,
            "attempts_used": self.attempts_used,
            "total_duration_ms": self.total_duration_ms,
            "final_http_status": self.final_http_status,
            "peer_ip": self.peer_ip,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


@dataclass(frozen=True)
class HttpSummary:
    """Aggregate counters for a ``health http`` run."""

    targets: int
    passed: int
    warned: int
    failed: int
    attempts: int

    def to_dict(self) -> dict[str, object]:
        return {
            "targets": self.targets,
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class HttpReport:
    """The full report rendered by ``maops-py health http``."""

    version: str
    protocol: HealthProtocol
    options: HttpOptions
    summary: HttpSummary
    results: tuple[HttpTargetResult, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "protocol": self.protocol.value,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "results": [result.to_dict() for result in self.results],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


@dataclass(frozen=True)
class TcpOptions:
    """The effective options in force for a ``health tcp`` run."""

    timeout_seconds: float
    retries: int
    retry_delay_seconds: float
    workers: int

    def to_dict(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "workers": self.workers,
        }


@dataclass(frozen=True)
class TcpAttempt:
    """One TCP connect attempt for a single target."""

    attempt: int
    duration_ms: int
    peer_ip: str | None
    failure_reason: TcpFailureReason | None
    detail: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "duration_ms": self.duration_ms,
            "peer_ip": self.peer_ip,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TcpTargetResult:
    """The retry-sequence outcome for one TCP target."""

    index: int
    target: str
    host: str
    port: int
    status: CheckStatus
    attempts_used: int
    total_duration_ms: int
    peer_ip: str | None
    attempts: tuple[TcpAttempt, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "target": self.target,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "attempts_used": self.attempts_used,
            "total_duration_ms": self.total_duration_ms,
            "peer_ip": self.peer_ip,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


@dataclass(frozen=True)
class TcpSummary:
    """Aggregate counters for a ``health tcp`` run."""

    targets: int
    passed: int
    warned: int
    failed: int
    attempts: int

    def to_dict(self) -> dict[str, object]:
        return {
            "targets": self.targets,
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class TcpReport:
    """The full report rendered by ``maops-py health tcp``."""

    version: str
    protocol: HealthProtocol
    options: TcpOptions
    summary: TcpSummary
    results: tuple[TcpTargetResult, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "protocol": self.protocol.value,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "results": [result.to_dict() for result in self.results],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
