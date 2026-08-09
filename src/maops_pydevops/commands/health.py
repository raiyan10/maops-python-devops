"""CLI-facing HTTP/TCP health-check orchestration.

Real orchestration lives here (validate every target -> run bounded
parallel checks -> assemble a frozen report), mirroring
``commands/logs.py`` rather than ``commands/inventory.py``'s
re-export-shim pattern, since ``health http``/``health tcp`` need genuine
per-command coordination between :mod:`maops_pydevops.core.health_http`,
:mod:`maops_pydevops.core.health_tcp`, and
:mod:`maops_pydevops.core.health_runner`. No network implementation lives
here -- only orchestration and option/summary assembly.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence

from maops_pydevops.core.health_http import (
    ValidatedHttpTarget,
    run_http_target_with_retries,
    validate_http_target,
)
from maops_pydevops.core.health_models import (
    HealthProtocol,
    HttpMethod,
    HttpOptions,
    HttpReport,
    HttpSummary,
    HttpTargetResult,
    TcpOptions,
    TcpReport,
    TcpSummary,
    TcpTargetResult,
)
from maops_pydevops.core.health_runner import run_bounded_parallel
from maops_pydevops.core.health_tcp import (
    ValidatedTcpTarget,
    run_tcp_target_with_retries,
    validate_tcp_target,
)
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.version import get_version

#: Target-count bound shared by both protocols (spec section 3).
MIN_TARGETS = 1
MAX_TARGETS = 100


def build_health_http_report(
    raw_targets: Sequence[str],
    *,
    method: HttpMethod,
    expected_status_min: int,
    expected_status_max: int,
    timeout_seconds: float,
    retries: int,
    retry_delay_seconds: float,
    workers: int,
) -> tuple[HttpReport | None, str | None]:
    """Validate every target, run bounded parallel checks, assemble a report.

    Returns ``(None, error)`` only for a usage/target-validation failure
    (too many/few targets, or the first syntactically/semantically invalid
    target) -- this is checked, and short-circuits, entirely before the
    executor is ever constructed, so no invalid target ever reaches a
    socket. A fully-built report (even one containing FAIL targets) never
    returns ``None``; genuine network failures are folded into per-target
    results instead.
    """
    if not (MIN_TARGETS <= len(raw_targets) <= MAX_TARGETS):
        return None, (
            f"target count must be between {MIN_TARGETS} and {MAX_TARGETS}, got {len(raw_targets)}"
        )

    validated: list[ValidatedHttpTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        target, error = validate_http_target(raw, index=index)
        if target is None:
            return None, error
        validated.append(target)

    options = HttpOptions(
        method=method,
        expected_status_min=expected_status_min,
        expected_status_max=expected_status_max,
        timeout_seconds=timeout_seconds,
        retries=retries,
        retry_delay_seconds=retry_delay_seconds,
        workers=workers,
        follow_redirects=False,
        tls_verify=True,
    )

    worker_fn = functools.partial(run_http_target_with_retries, options=options)
    results: tuple[HttpTargetResult, ...] = run_bounded_parallel(
        validated, worker_fn, max_workers=workers
    )

    passed = sum(1 for result in results if result.status is CheckStatus.PASS)
    warned = sum(1 for result in results if result.status is CheckStatus.WARN)
    failed = sum(1 for result in results if result.status is CheckStatus.FAIL)
    total_attempts = sum(result.attempts_used for result in results)

    if failed > 0:
        overall = CheckStatus.FAIL
    elif warned > 0:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    report = HttpReport(
        version=get_version(),
        protocol=HealthProtocol.HTTP,
        options=options,
        summary=HttpSummary(
            targets=len(results),
            passed=passed,
            warned=warned,
            failed=failed,
            attempts=total_attempts,
        ),
        results=results,
        overall=overall,
    )
    return report, None


def build_health_tcp_report(
    raw_targets: Sequence[str],
    *,
    timeout_seconds: float,
    retries: int,
    retry_delay_seconds: float,
    workers: int,
) -> tuple[TcpReport | None, str | None]:
    """Validate every target, run bounded parallel checks, assemble a report.

    Mirrors :func:`build_health_http_report`'s contract exactly.
    """
    if not (MIN_TARGETS <= len(raw_targets) <= MAX_TARGETS):
        return None, (
            f"target count must be between {MIN_TARGETS} and {MAX_TARGETS}, got {len(raw_targets)}"
        )

    validated: list[ValidatedTcpTarget] = []
    for index, raw in enumerate(raw_targets, start=1):
        target, error = validate_tcp_target(raw, index=index)
        if target is None:
            return None, error
        validated.append(target)

    options = TcpOptions(
        timeout_seconds=timeout_seconds,
        retries=retries,
        retry_delay_seconds=retry_delay_seconds,
        workers=workers,
    )

    worker_fn = functools.partial(run_tcp_target_with_retries, options=options)
    results: tuple[TcpTargetResult, ...] = run_bounded_parallel(
        validated, worker_fn, max_workers=workers
    )

    passed = sum(1 for result in results if result.status is CheckStatus.PASS)
    warned = sum(1 for result in results if result.status is CheckStatus.WARN)
    failed = sum(1 for result in results if result.status is CheckStatus.FAIL)
    total_attempts = sum(result.attempts_used for result in results)

    if failed > 0:
        overall = CheckStatus.FAIL
    elif warned > 0:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    report = TcpReport(
        version=get_version(),
        protocol=HealthProtocol.TCP,
        options=options,
        summary=TcpSummary(
            targets=len(results),
            passed=passed,
            warned=warned,
            failed=failed,
            attempts=total_attempts,
        ),
        results=results,
        overall=overall,
    )
    return report, None
