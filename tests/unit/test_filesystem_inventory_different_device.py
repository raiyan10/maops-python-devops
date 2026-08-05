"""A directory entry on a different st_dev is counted but never recursed into.

Bind-mount-based testing is impractical in CI, so this monkeypatches the
per-entry ``stat()`` result's ``st_dev`` to simulate a mount-point
boundary deterministically.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import maops_pydevops.core.filesystem_inventory as filesystem_inventory_module


def test_different_device_directory_not_recursed_into(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount_point = tmp_path / "other_fs"
    mount_point.mkdir()
    (mount_point / "inside.txt").write_text("data", encoding="utf-8")

    root_dev = os.stat(tmp_path).st_dev
    real_scandir = os.scandir

    class _WrappedEntry:
        def __init__(self, entry: os.DirEntry[str]) -> None:
            self._entry = entry
            self.name = entry.name
            self.path = entry.path

        def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
            real_stat = self._entry.stat(follow_symlinks=follow_symlinks)
            if self._entry.path == str(mount_point):
                return os.stat_result(
                    (
                        real_stat.st_mode,
                        real_stat.st_ino,
                        root_dev + 1,
                        real_stat.st_nlink,
                        real_stat.st_uid,
                        real_stat.st_gid,
                        real_stat.st_size,
                        real_stat.st_atime,
                        real_stat.st_mtime,
                        real_stat.st_ctime,
                    )
                )
            return real_stat

        def is_symlink(self) -> bool:
            return self._entry.is_symlink()

    def _fake_scandir(path: str = ".") -> object:
        return iter(_WrappedEntry(e) for e in real_scandir(path))

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)

    report, error = filesystem_inventory_module.build_filesystem_report(
        str(tmp_path), max_depth=5, max_entries=100, top=5
    )
    assert error is None
    assert report is not None
    assert report.summary.directories == 1
    assert report.summary.different_filesystem_entries == 1
    # The mount point's own contents are never enumerated.
    assert report.summary.files == 0
    assert report.summary.scanned_entries == 1
