"""System inventory: local-metadata-only host/OS/CPU/memory/uptime facts.

Every ``gather_*`` function accepts injectable, keyword-only override
parameters for deterministic testing, following
:mod:`maops_pydevops.core.platform`'s style. This module never imports
``subprocess`` or ``socket``, never reads named environment variables, and
never performs network or DNS resolution -- collection is pure local
introspection via ``os``/``platform``/``pathlib``.
"""

from __future__ import annotations

import math
import os
import platform
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from maops_pydevops.core.inventory_models import (
    CpuInfo,
    DistributionInfo,
    HostInfo,
    InventoryIssue,
    MemoryInfo,
    SystemInventoryReport,
    SystemPythonInfo,
    UptimeInfo,
)
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.version import get_version


class _UnameLike(Protocol):
    """The subset of ``platform.uname_result`` this module depends on."""

    system: str
    release: str
    version: str
    machine: str


class _Unset:
    """Sentinel type distinguishing "no override" from an overridden ``None``.

    ``os.cpu_count()`` legitimately returns ``None`` on an indeterminate
    platform, so ``None`` cannot itself mean "not overridden" the way it
    does for every other gather function in this module.
    """


_UNSET = _Unset()


def gather_host_info(
    *,
    uname: _UnameLike | None = None,
    hostname: str | None = None,
) -> HostInfo:
    """Collect host/OS facts from ``platform.uname()``/``platform.node()``."""
    actual_uname = uname if uname is not None else platform.uname()
    actual_hostname = hostname if hostname is not None else platform.node()
    return HostInfo(
        hostname=actual_hostname or None,
        os_family=actual_uname.system,
        os_release=actual_uname.release,
        os_version=actual_uname.version or None,
        machine=actual_uname.machine,
    )


def gather_distribution_info(
    *,
    freedesktop_os_release: Callable[[], dict[str, str]] | None = None,
) -> tuple[DistributionInfo, InventoryIssue | None]:
    """Collect Linux distribution facts via ``platform.freedesktop_os_release()``."""
    fn = (
        freedesktop_os_release
        if freedesktop_os_release is not None
        else platform.freedesktop_os_release
    )
    try:
        data = fn()
    except OSError as exc:
        return (
            DistributionInfo(id=None, name=None, version_id=None, available=False),
            InventoryIssue(
                component="distribution",
                status=CheckStatus.WARN,
                detail=f"distribution metadata unavailable: {exc}",
            ),
        )
    return (
        DistributionInfo(
            id=data.get("ID"),
            name=data.get("NAME"),
            version_id=data.get("VERSION_ID"),
            available=True,
        ),
        None,
    )


def gather_python_info(
    *,
    version: str | None = None,
    implementation: str | None = None,
    executable: str | None = None,
) -> SystemPythonInfo:
    """Collect interpreter facts. These calls cannot fail."""
    return SystemPythonInfo(
        version=version if version is not None else platform.python_version(),
        implementation=(
            implementation if implementation is not None else platform.python_implementation()
        ),
        executable=executable if executable is not None else sys.executable,
    )


def gather_cpu_info(
    *,
    cpu_count: int | None | _Unset = _UNSET,
    getloadavg: Callable[[], tuple[float, float, float]] | None = None,
) -> tuple[CpuInfo, InventoryIssue | None]:
    """Collect logical CPU count and load averages.

    A ``None`` logical count is a normal, distinctly-represented null
    field (an indeterminate count is not itself a warning); only a
    load-average collection failure produces an issue.
    """
    actual_count = os.cpu_count() if isinstance(cpu_count, _Unset) else cpu_count

    if getloadavg is None and not hasattr(os, "getloadavg"):
        # os.getloadavg is a Unix-only attribute -- it does not exist on
        # os at all on Windows, so the lookup itself (not just the call)
        # must be guarded rather than relying on a try/except around the
        # call to catch an OSError that would never be raised.
        return (
            CpuInfo(
                logical_count=actual_count,
                load_average_1m=None,
                load_average_5m=None,
                load_average_15m=None,
            ),
            InventoryIssue(
                component="load_average",
                status=CheckStatus.WARN,
                detail="load averages are not supported on this platform",
            ),
        )
    active_getloadavg = getloadavg if getloadavg is not None else os.getloadavg

    try:
        load_1m, load_5m, load_15m = active_getloadavg()
    except OSError as exc:
        return (
            CpuInfo(
                logical_count=actual_count,
                load_average_1m=None,
                load_average_5m=None,
                load_average_15m=None,
            ),
            InventoryIssue(
                component="load_average",
                status=CheckStatus.WARN,
                detail=f"load averages unavailable: {exc}",
            ),
        )
    return (
        CpuInfo(
            logical_count=actual_count,
            load_average_1m=load_1m,
            load_average_5m=load_5m,
            load_average_15m=load_15m,
        ),
        None,
    )


def _parse_meminfo(lines: Sequence[str]) -> tuple[int | None, int | None, list[str]]:
    """Parse ``MemTotal``/``MemAvailable`` (kB) from ``/proc/meminfo`` lines.

    Returns ``(total_bytes, available_bytes, warnings)``. Never raises;
    malformed, negative, or internally inconsistent values are rejected
    and reported as warnings rather than fabricated. ``MemFree`` is never
    read as a substitute for a missing ``MemAvailable`` -- that would be a
    different, undocumented metric.
    """
    total_kb: int | None = None
    available_kb: int | None = None
    warnings: list[str] = []

    for line in lines:
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key not in ("MemTotal", "MemAvailable"):
            continue
        if key == "MemTotal" and total_kb is not None:
            continue
        if key == "MemAvailable" and available_kb is not None:
            continue

        tokens = rest.split()
        if len(tokens) != 2 or tokens[1] != "kB":
            warnings.append(f"unparseable {key} line")
            continue
        try:
            value = int(tokens[0])
        except ValueError:
            warnings.append(f"unparseable {key} value")
            continue
        if value < 0:
            warnings.append(f"{key} is negative")
            continue

        if key == "MemTotal":
            total_kb = value
        else:
            available_kb = value

    if total_kb is None:
        warnings.append("MemTotal missing or unparseable")
        total_bytes = None
    else:
        total_bytes = total_kb * 1024

    if available_kb is None:
        warnings.append("MemAvailable missing or unparseable")
        available_bytes = None
    elif total_bytes is not None and available_kb * 1024 > total_bytes:
        warnings.append("MemAvailable exceeds MemTotal")
        available_bytes = None
    else:
        available_bytes = available_kb * 1024

    return total_bytes, available_bytes, warnings


def gather_memory_info(
    *,
    meminfo_lines: Sequence[str] | None = None,
    os_family: str | None = None,
) -> tuple[MemoryInfo, InventoryIssue | None]:
    """Collect Linux memory facts from ``/proc/meminfo``."""
    actual_os_family = os_family if os_family is not None else platform.system()
    if actual_os_family != "Linux":
        return (
            MemoryInfo(
                available=False,
                total_bytes=None,
                available_bytes=None,
                used_bytes=None,
                used_percent=None,
            ),
            InventoryIssue(
                component="memory",
                status=CheckStatus.WARN,
                detail="memory metadata is only available on Linux",
            ),
        )

    if meminfo_lines is not None:
        lines: Sequence[str] = meminfo_lines
    else:
        try:
            lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return (
                MemoryInfo(
                    available=False,
                    total_bytes=None,
                    available_bytes=None,
                    used_bytes=None,
                    used_percent=None,
                ),
                InventoryIssue(
                    component="memory",
                    status=CheckStatus.WARN,
                    detail=f"/proc/meminfo unavailable: {exc}",
                ),
            )

    total_bytes, available_bytes, warnings = _parse_meminfo(lines)

    used_bytes: int | None = None
    used_percent: float | None = None
    if total_bytes is not None and available_bytes is not None:
        if total_bytes == 0:
            warnings.append("MemTotal is zero")
        else:
            used_bytes = total_bytes - available_bytes
            used_percent = max(0.0, min(100.0, round((used_bytes / total_bytes) * 100, 2)))

    issue = (
        InventoryIssue(component="memory", status=CheckStatus.WARN, detail="; ".join(warnings))
        if warnings
        else None
    )
    return (
        MemoryInfo(
            available=True,
            total_bytes=total_bytes,
            available_bytes=available_bytes,
            used_bytes=used_bytes,
            used_percent=used_percent,
        ),
        issue,
    )


def _parse_uptime(line: str) -> tuple[float | None, str | None]:
    """Parse the first numeric token of ``/proc/uptime``.

    Returns ``(seconds, warning)``. Never raises; malformed, negative,
    NaN, or infinite values are rejected.
    """
    tokens = line.strip().split()
    if not tokens:
        return None, "empty /proc/uptime content"
    try:
        value = float(tokens[0])
    except ValueError:
        return None, f"unparseable uptime value: {tokens[0]!r}"
    if math.isnan(value) or math.isinf(value):
        return None, "uptime value is NaN or infinite"
    if value < 0:
        return None, "uptime value is negative"
    return value, None


def gather_uptime_info(
    *,
    uptime_line: str | None = None,
    os_family: str | None = None,
) -> tuple[UptimeInfo, InventoryIssue | None]:
    """Collect Linux system uptime from ``/proc/uptime``."""
    actual_os_family = os_family if os_family is not None else platform.system()
    if actual_os_family != "Linux":
        return (
            UptimeInfo(available=False, seconds=None),
            InventoryIssue(
                component="uptime",
                status=CheckStatus.WARN,
                detail="uptime is only available on Linux",
            ),
        )

    if uptime_line is not None:
        line = uptime_line
    else:
        try:
            line = Path("/proc/uptime").read_text(encoding="utf-8")
        except OSError as exc:
            return (
                UptimeInfo(available=False, seconds=None),
                InventoryIssue(
                    component="uptime",
                    status=CheckStatus.WARN,
                    detail=f"/proc/uptime unavailable: {exc}",
                ),
            )

    seconds, warning = _parse_uptime(line)
    if warning is not None:
        return (
            UptimeInfo(available=False, seconds=None),
            InventoryIssue(component="uptime", status=CheckStatus.WARN, detail=warning),
        )
    return UptimeInfo(available=True, seconds=seconds), None


def _compute_overall(issues: tuple[InventoryIssue, ...]) -> CheckStatus:
    if any(issue.status is CheckStatus.FAIL for issue in issues):
        return CheckStatus.FAIL
    if issues:
        return CheckStatus.WARN
    return CheckStatus.PASS


def build_system_report(
    *,
    uname: _UnameLike | None = None,
    hostname: str | None = None,
    freedesktop_os_release: Callable[[], dict[str, str]] | None = None,
    python_version: str | None = None,
    python_implementation: str | None = None,
    python_executable: str | None = None,
    cpu_count: int | None | _Unset = _UNSET,
    getloadavg: Callable[[], tuple[float, float, float]] | None = None,
    meminfo_lines: Sequence[str] | None = None,
    memory_os_family: str | None = None,
    uptime_line: str | None = None,
    uptime_os_family: str | None = None,
) -> SystemInventoryReport:
    """Assemble the full system inventory report.

    Gather functions run in a fixed declared order -- host, distribution,
    python, cpu, memory, uptime -- and any collected issues are appended
    in that same order (host and python never emit issues), so the
    resulting ``issues`` sequence is always deterministic.
    """
    host = gather_host_info(uname=uname, hostname=hostname)
    distribution, distribution_issue = gather_distribution_info(
        freedesktop_os_release=freedesktop_os_release
    )
    python = gather_python_info(
        version=python_version,
        implementation=python_implementation,
        executable=python_executable,
    )
    cpu, cpu_issue = gather_cpu_info(cpu_count=cpu_count, getloadavg=getloadavg)
    memory, memory_issue = gather_memory_info(
        meminfo_lines=meminfo_lines, os_family=memory_os_family
    )
    uptime, uptime_issue = gather_uptime_info(uptime_line=uptime_line, os_family=uptime_os_family)

    issues = tuple(
        issue
        for issue in (distribution_issue, cpu_issue, memory_issue, uptime_issue)
        if issue is not None
    )

    return SystemInventoryReport(
        version=get_version(),
        host=host,
        distribution=distribution,
        python=python,
        cpu=cpu,
        memory=memory,
        uptime=uptime,
        issues=issues,
        overall=_compute_overall(issues),
    )
