"""Bounded, read-only, deterministic filesystem scanner.

Never follows symbolic links, never crosses mount points, never reads
file content, never computes a hash, and never invokes an external
command. Traversal is built on ``os.scandir()`` with explicit,
hand-rolled depth/entry bookkeeping rather than any unbounded whole-tree
walk helper. This module never imports ``subprocess`` or ``socket``, and
never reads named environment variables.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field

from maops_pydevops.core.inventory_models import (
    FilesystemInventoryReport,
    FilesystemScanOptions,
    FilesystemScanSummary,
    InventoryIssue,
    LargestFileEntry,
)
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.version import get_version


@dataclass
class _ScanState:
    """Mutable accumulator for a single bounded traversal."""

    max_depth: int
    max_entries: int
    root_st_dev: int
    scanned_entries: int = 0
    directories: int = 0
    files: int = 0
    symlinks: int = 0
    other: int = 0
    total_file_bytes: int = 0
    skipped_entries: int = 0
    inaccessible_entries: int = 0
    different_filesystem_entries: int = 0
    max_depth_reached: bool = False
    truncated: bool = False
    size_candidates: list[tuple[int, str, str, int]] = field(default_factory=list)
    issues: list[InventoryIssue] = field(default_factory=list)


def _scan_directory(dir_path: str, depth: int, normalized_root: str, state: _ScanState) -> None:
    """Recursively scan ``dir_path`` (at ``depth``) into ``state``.

    The depth guard is checked once, here, before ``os.scandir`` is even
    attempted -- not at the point a parent directory decides whether to
    recurse into a just-found subdirectory entry. This means a directory
    entry itself is always counted by its parent's scan, but its own
    contents are never enumerated once ``depth + 1 > max_depth``: for
    ``max_depth=0`` this means the root's own ``os.scandir`` is never
    called at all.
    """
    if depth + 1 > state.max_depth:
        state.max_depth_reached = True
        return

    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
    except OSError as exc:
        relative = os.path.relpath(dir_path, normalized_root)
        state.issues.append(
            InventoryIssue(component=relative, status=CheckStatus.WARN, detail=str(exc))
        )
        if isinstance(exc, FileNotFoundError):
            state.skipped_entries += 1
        else:
            state.inaccessible_entries += 1
        return

    for entry in entries:
        if state.scanned_entries >= state.max_entries:
            state.truncated = True
            return

        entry_relative = os.path.relpath(entry.path, normalized_root)
        try:
            entry_stat = entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            state.skipped_entries += 1
            state.issues.append(
                InventoryIssue(
                    component=entry_relative,
                    status=CheckStatus.WARN,
                    detail="entry disappeared during scan",
                )
            )
            continue
        except PermissionError:
            state.inaccessible_entries += 1
            state.issues.append(
                InventoryIssue(
                    component=entry_relative, status=CheckStatus.WARN, detail="permission denied"
                )
            )
            continue
        except NotADirectoryError:
            state.skipped_entries += 1
            state.issues.append(
                InventoryIssue(
                    component=entry_relative,
                    status=CheckStatus.WARN,
                    detail="path component replaced during scan (not a directory)",
                )
            )
            continue
        except OSError as exc:
            state.inaccessible_entries += 1
            state.issues.append(
                InventoryIssue(component=entry_relative, status=CheckStatus.WARN, detail=str(exc))
            )
            continue

        state.scanned_entries += 1

        if entry.is_symlink():
            state.symlinks += 1
            continue

        if stat.S_ISDIR(entry_stat.st_mode):
            state.directories += 1
            if entry_stat.st_dev != state.root_st_dev:
                state.different_filesystem_entries += 1
                continue
            _scan_directory(entry.path, depth + 1, normalized_root, state)
            if state.truncated:
                return
        elif stat.S_ISREG(entry_stat.st_mode):
            state.files += 1
            state.total_file_bytes += entry_stat.st_size
            state.size_candidates.append(
                (entry_stat.st_size, entry.path, entry_relative, entry_stat.st_mtime_ns)
            )
        else:
            state.other += 1


def _build_options(max_depth: int, max_entries: int, top: int) -> FilesystemScanOptions:
    return FilesystemScanOptions(max_depth=max_depth, max_entries=max_entries, top=top)


def _largest_files(
    candidates: list[tuple[int, str, str, int]], top: int
) -> tuple[LargestFileEntry, ...]:
    if top <= 0:
        return ()
    ordered = sorted(candidates, key=lambda c: (-c[0], c[1]))
    return tuple(
        LargestFileEntry(path=path, relative_path=relative, size_bytes=size, modified_ns=mtime_ns)
        for size, path, relative, mtime_ns in ordered[:top]
    )


def build_filesystem_report(
    root_arg: str | None,
    *,
    max_depth: int,
    max_entries: int,
    top: int,
    cwd: str | None = None,
) -> tuple[FilesystemInventoryReport | None, str | None]:
    """Build a bounded filesystem inventory report.

    Returns ``(report, None)`` on success -- always, regardless of any
    per-entry issues encountered -- or ``(None, error)`` if the root
    itself cannot be classified at all (nonexistent or inaccessible),
    which is the only condition that maps to an operational failure.
    """
    raw_root = root_arg if root_arg is not None else (cwd if cwd is not None else os.getcwd())
    normalized_root = os.path.abspath(raw_root)

    try:
        root_lstat = os.lstat(normalized_root)
    except FileNotFoundError:
        return None, f"path not found: {raw_root}"
    except PermissionError:
        return None, f"permission denied: {raw_root}"
    except OSError as exc:
        return None, f"cannot access {raw_root}: {exc}"

    options = _build_options(max_depth, max_entries, top)
    root_st_dev = root_lstat.st_dev

    if stat.S_ISLNK(root_lstat.st_mode):
        summary = FilesystemScanSummary(
            scanned_entries=1,
            directories=0,
            files=0,
            symlinks=1,
            other=0,
            total_file_bytes=0,
            skipped_entries=0,
            inaccessible_entries=0,
            different_filesystem_entries=0,
        )
        return (
            FilesystemInventoryReport(
                version=get_version(),
                root=normalized_root,
                options=options,
                summary=summary,
                largest_files=(),
                issues=(),
                max_depth_reached=False,
                truncated=False,
                overall=CheckStatus.PASS,
            ),
            None,
        )

    if stat.S_ISREG(root_lstat.st_mode):
        summary = FilesystemScanSummary(
            scanned_entries=1,
            directories=0,
            files=1,
            symlinks=0,
            other=0,
            total_file_bytes=root_lstat.st_size,
            skipped_entries=0,
            inaccessible_entries=0,
            different_filesystem_entries=0,
        )
        largest_files = (
            (
                LargestFileEntry(
                    path=normalized_root,
                    relative_path=".",
                    size_bytes=root_lstat.st_size,
                    modified_ns=root_lstat.st_mtime_ns,
                ),
            )
            if top > 0
            else ()
        )
        return (
            FilesystemInventoryReport(
                version=get_version(),
                root=normalized_root,
                options=options,
                summary=summary,
                largest_files=largest_files,
                issues=(),
                max_depth_reached=False,
                truncated=False,
                overall=CheckStatus.PASS,
            ),
            None,
        )

    if not stat.S_ISDIR(root_lstat.st_mode):
        summary = FilesystemScanSummary(
            scanned_entries=1,
            directories=0,
            files=0,
            symlinks=0,
            other=1,
            total_file_bytes=0,
            skipped_entries=0,
            inaccessible_entries=0,
            different_filesystem_entries=0,
        )
        return (
            FilesystemInventoryReport(
                version=get_version(),
                root=normalized_root,
                options=options,
                summary=summary,
                largest_files=(),
                issues=(),
                max_depth_reached=False,
                truncated=False,
                overall=CheckStatus.PASS,
            ),
            None,
        )

    state = _ScanState(max_depth=max_depth, max_entries=max_entries, root_st_dev=root_st_dev)
    _scan_directory(normalized_root, 0, normalized_root, state)

    summary = FilesystemScanSummary(
        scanned_entries=state.scanned_entries,
        directories=state.directories,
        files=state.files,
        symlinks=state.symlinks,
        other=state.other,
        total_file_bytes=state.total_file_bytes,
        skipped_entries=state.skipped_entries,
        inaccessible_entries=state.inaccessible_entries,
        different_filesystem_entries=state.different_filesystem_entries,
    )
    issues = tuple(state.issues)
    overall = CheckStatus.WARN if issues else CheckStatus.PASS

    return (
        FilesystemInventoryReport(
            version=get_version(),
            root=normalized_root,
            options=options,
            summary=summary,
            largest_files=_largest_files(state.size_candidates, top),
            issues=issues,
            max_depth_reached=state.max_depth_reached,
            truncated=state.truncated,
            overall=overall,
        ),
        None,
    )
