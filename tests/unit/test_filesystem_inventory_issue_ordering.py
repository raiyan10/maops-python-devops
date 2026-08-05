"""Filesystem issues are collected in natural traversal/discovery order."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import maops_pydevops.core.filesystem_inventory as filesystem_inventory_module
from maops_pydevops.core.filesystem_inventory import build_filesystem_report


class _FakeEntry:
    def __init__(self, name: str, path: str, *, raises: BaseException) -> None:
        self.name = name
        self.path = path
        self._raises = raises

    def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
        raise self._raises

    def is_symlink(self) -> bool:
        return False


def test_issues_appear_in_name_ascending_traversal_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = str(tmp_path)
    entries = [
        _FakeEntry("a_broken", f"{root}/a_broken", raises=PermissionError()),
        _FakeEntry("b_broken", f"{root}/b_broken", raises=FileNotFoundError()),
        _FakeEntry("c_broken", f"{root}/c_broken", raises=PermissionError()),
    ]
    real_scandir = os.scandir

    def _fake_scandir(path: str = ".") -> object:
        if str(path) == root:
            return iter(entries)
        return real_scandir(path)

    monkeypatch.setattr(filesystem_inventory_module.os, "scandir", _fake_scandir)

    report, error = build_filesystem_report(root, max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    components = [issue.component for issue in report.issues]
    assert components == ["a_broken", "b_broken", "c_broken"]
