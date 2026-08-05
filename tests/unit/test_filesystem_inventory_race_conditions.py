"""Per-entry races (FileNotFoundError, PermissionError, NotADirectoryError,
other OSError) become structured issues and do not crash the scan.

Real filesystem races between ``os.scandir()`` and a per-entry ``stat()``
are inherently flaky to reproduce on a live filesystem, so this uses a
fake ``os.DirEntry``-like seam that raises deterministically on demand.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import maops_pydevops.core.filesystem_inventory as filesystem_inventory_module
from maops_pydevops.core.filesystem_inventory import build_filesystem_report
from maops_pydevops.core.models import CheckStatus


class _FakeEntry:
    def __init__(self, name: str, path: str, *, raises: BaseException | None = None) -> None:
        self.name = name
        self.path = path
        self._raises = raises

    def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
        if self._raises is not None:
            raise self._raises
        raise AssertionError("unexpected real stat() call on a fake entry")

    def is_symlink(self) -> bool:
        return False


def _patch_scandir(monkeypatch: pytest.MonkeyPatch, root: str, entries: list[_FakeEntry]) -> None:
    real_scandir = os.scandir

    def _fake_scandir(path: str = ".") -> object:
        if str(path) == root:
            return iter(entries)
        return real_scandir(path)

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)


def test_file_not_found_race_becomes_skipped_entry_with_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(tmp_path)
    entry = _FakeEntry("vanished.txt", f"{root}/vanished.txt", raises=FileNotFoundError())
    _patch_scandir(monkeypatch, root, [entry])

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.skipped_entries == 1
    assert report.summary.scanned_entries == 0
    assert len(report.issues) == 1
    assert report.issues[0].status is CheckStatus.WARN
    assert report.overall is CheckStatus.WARN


def test_permission_error_race_becomes_inaccessible_entry_with_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(tmp_path)
    entry = _FakeEntry("locked.txt", f"{root}/locked.txt", raises=PermissionError())
    _patch_scandir(monkeypatch, root, [entry])

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.inaccessible_entries == 1
    assert "permission denied" in report.issues[0].detail


def test_not_a_directory_race_becomes_skipped_entry_with_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(tmp_path)
    entry = _FakeEntry("replaced", f"{root}/replaced", raises=NotADirectoryError())
    _patch_scandir(monkeypatch, root, [entry])

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.skipped_entries == 1
    assert "not a directory" in report.issues[0].detail


def test_generic_os_error_race_becomes_inaccessible_entry_with_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(tmp_path)
    entry = _FakeEntry("weird", f"{root}/weird", raises=OSError("device error"))
    _patch_scandir(monkeypatch, root, [entry])

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.inaccessible_entries == 1


def test_unexpected_non_os_error_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine programming error must never be silently swallowed."""
    root = str(tmp_path)
    entry = _FakeEntry("boom", f"{root}/boom", raises=ValueError("not an OSError"))
    _patch_scandir(monkeypatch, root, [entry])

    with pytest.raises(ValueError, match="not an OSError"):
        build_filesystem_report(root, max_depth=5, max_entries=100, top=5)


def test_directory_scandir_failure_is_a_race_issue_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    root = str(tmp_path)
    real_scandir = os.scandir

    def _fake_scandir(path: str = ".") -> object:
        if str(path) == str(sub):
            raise PermissionError("cannot list directory")
        return real_scandir(path)

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.directories == 1
    assert report.summary.inaccessible_entries == 1
    assert len(report.issues) == 1


def test_directory_vanishing_before_scandir_is_skipped_not_inaccessible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    root = str(tmp_path)
    real_scandir = os.scandir

    def _fake_scandir(path: str = ".") -> object:
        if str(path) == str(sub):
            raise FileNotFoundError("directory vanished")
        return real_scandir(path)

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.skipped_entries == 1
    assert report.summary.inaccessible_entries == 0


def test_root_lstat_generic_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_lstat(path: str) -> os.stat_result:
        raise OSError("device error")

    monkeypatch.setattr(filesystem_inventory_module.os, "lstat", _raise_lstat)
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert report is None
    assert error is not None
    assert "cannot access" in error
