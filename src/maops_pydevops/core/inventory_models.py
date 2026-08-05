"""Typed data models for system and filesystem inventory reports."""

from __future__ import annotations

import json
from dataclasses import dataclass

from maops_pydevops.core.models import CheckStatus


@dataclass(frozen=True)
class InventoryIssue:
    """A single degraded-data or traversal issue attached to an inventory report."""

    component: str
    status: CheckStatus
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "component": self.component,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostInfo:
    """Local host/OS facts, collected without any subprocess or DNS lookup."""

    hostname: str | None
    os_family: str
    os_release: str
    os_version: str | None
    machine: str

    def to_dict(self) -> dict[str, object]:
        return {
            "hostname": self.hostname,
            "os_family": self.os_family,
            "os_release": self.os_release,
            "os_version": self.os_version,
            "machine": self.machine,
        }


@dataclass(frozen=True)
class DistributionInfo:
    """Linux distribution facts from ``platform.freedesktop_os_release()``."""

    id: str | None
    name: str | None
    version_id: str | None
    available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "version_id": self.version_id,
            "available": self.available,
        }


@dataclass(frozen=True)
class SystemPythonInfo:
    """Interpreter facts reported by the inventory command.

    Distinct from :class:`maops_pydevops.core.models.PythonInfo`: this
    report has no notion of "supported," only observed facts.
    """

    version: str
    implementation: str
    executable: str

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "implementation": self.implementation,
            "executable": self.executable,
        }


@dataclass(frozen=True)
class CpuInfo:
    """Logical CPU count and load averages."""

    logical_count: int | None
    load_average_1m: float | None
    load_average_5m: float | None
    load_average_15m: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_count": self.logical_count,
            "load_average_1m": self.load_average_1m,
            "load_average_5m": self.load_average_5m,
            "load_average_15m": self.load_average_15m,
        }


@dataclass(frozen=True)
class MemoryInfo:
    """Linux ``/proc/meminfo``-derived memory facts.

    ``available`` is ``True`` iff ``/proc/meminfo`` itself was read
    successfully on Linux, independent of whether individual fields below
    ended up ``None`` (e.g. ``total_bytes`` can be populated while
    ``used_bytes``/``used_percent`` are simultaneously ``None`` if only
    ``MemAvailable`` failed to parse).
    """

    available: bool
    total_bytes: int | None
    available_bytes: int | None
    used_bytes: int | None
    used_percent: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "used_bytes": self.used_bytes,
            "used_percent": self.used_percent,
        }


@dataclass(frozen=True)
class UptimeInfo:
    """Linux ``/proc/uptime``-derived system uptime."""

    available: bool
    seconds: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "seconds": self.seconds,
        }


@dataclass(frozen=True)
class SystemInventoryReport:
    """The full report rendered by ``maops-py inventory system``.

    ``overall`` reflects the severity of collected ``issues`` (``warn`` if
    any optional field degraded, ``pass`` otherwise); it is deliberately
    decoupled from the command's exit code, which is always ``0`` unless
    the report could not be constructed at all.
    """

    version: str
    host: HostInfo
    distribution: DistributionInfo
    python: SystemPythonInfo
    cpu: CpuInfo
    memory: MemoryInfo
    uptime: UptimeInfo
    issues: tuple[InventoryIssue, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "host": self.host.to_dict(),
            "distribution": self.distribution.to_dict(),
            "python": self.python.to_dict(),
            "cpu": self.cpu.to_dict(),
            "memory": self.memory.to_dict(),
            "uptime": self.uptime.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


@dataclass(frozen=True)
class FilesystemScanOptions:
    """The scan limits and fixed safety policy in effect for a filesystem scan."""

    max_depth: int
    max_entries: int
    top: int
    follow_symlinks: bool = False
    same_filesystem: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "max_depth": self.max_depth,
            "max_entries": self.max_entries,
            "top": self.top,
            "follow_symlinks": self.follow_symlinks,
            "same_filesystem": self.same_filesystem,
        }


@dataclass(frozen=True)
class FilesystemScanSummary:
    """Entry counts observed during a bounded filesystem scan."""

    scanned_entries: int
    directories: int
    files: int
    symlinks: int
    other: int
    total_file_bytes: int
    skipped_entries: int
    inaccessible_entries: int
    different_filesystem_entries: int

    def to_dict(self) -> dict[str, object]:
        return {
            "scanned_entries": self.scanned_entries,
            "directories": self.directories,
            "files": self.files,
            "symlinks": self.symlinks,
            "other": self.other,
            "total_file_bytes": self.total_file_bytes,
            "skipped_entries": self.skipped_entries,
            "inaccessible_entries": self.inaccessible_entries,
            "different_filesystem_entries": self.different_filesystem_entries,
        }


@dataclass(frozen=True)
class LargestFileEntry:
    """A single entry in the largest-files list."""

    path: str
    relative_path: str
    size_bytes: int
    modified_ns: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "modified_ns": self.modified_ns,
        }


@dataclass(frozen=True)
class FilesystemInventoryReport:
    """The full report rendered by ``maops-py inventory filesystem``.

    ``overall`` is ``warn`` if any per-entry ``issues`` were collected
    during an otherwise-successful scan, ``pass`` otherwise; it never
    reflects ``fail`` in a successfully-produced report -- a root that
    cannot be classified at all never reaches this type (see
    ``commands/inventory.py``'s ``(report | None, error)`` return shape).
    """

    version: str
    root: str
    options: FilesystemScanOptions
    summary: FilesystemScanSummary
    largest_files: tuple[LargestFileEntry, ...]
    issues: tuple[InventoryIssue, ...]
    max_depth_reached: bool
    truncated: bool
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "root": self.root,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "largest_files": [entry.to_dict() for entry in self.largest_files],
            "issues": [issue.to_dict() for issue in self.issues],
            "max_depth_reached": self.max_depth_reached,
            "truncated": self.truncated,
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
