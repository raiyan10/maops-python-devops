"""Partial per-entry warnings never affect the exit code; only an
operational root failure (exit 1) does. FAIL never appears in a
successfully-produced filesystem report's overall.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import maops_pydevops.core.filesystem_inventory as filesystem_inventory_module
from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, main
from maops_pydevops.core.models import CheckStatus


class _FakeEntry:
    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path

    def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
        raise PermissionError("denied")

    def is_symlink(self) -> bool:
        return False


def test_partial_warning_still_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = str(tmp_path)
    real_scandir = os.scandir

    def _fake_scandir(path: str = ".") -> object:
        if str(path) == root:
            return iter([_FakeEntry("locked", f"{root}/locked")])
        return real_scandir(path)

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)
    report, error = filesystem_inventory_module.build_filesystem_report(
        root, max_depth=5, max_entries=100, top=5
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.WARN
    assert len(report.issues) == 1

    exit_code = main(["inventory", "filesystem", root])
    assert exit_code == EXIT_SUCCESS


def test_fatal_root_failure_exits_one(tmp_path: Path) -> None:
    missing = str(tmp_path / "does-not-exist")
    exit_code = main(["inventory", "filesystem", missing])
    assert exit_code == EXIT_FAILURE


def test_clean_scan_overall_is_pass(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    report, error = filesystem_inventory_module.build_filesystem_report(
        str(tmp_path), max_depth=5, max_entries=100, top=5
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.PASS
