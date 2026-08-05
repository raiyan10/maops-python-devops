"""Root-type dispatch: regular file, symlink, special file, missing, unreadable."""

import os
import stat
import sys
from pathlib import Path

import pytest

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_regular_file_root_produces_one_file_report(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hello", encoding="utf-8")
    report, error = build_filesystem_report(str(target), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.files == 1
    assert report.summary.scanned_entries == 1
    assert report.summary.directories == 0
    assert len(report.largest_files) == 1
    assert report.largest_files[0].relative_path == "."


def test_symlink_root_to_file_is_reported_but_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hello world", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)
    report, error = build_filesystem_report(str(link), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.symlinks == 1
    assert report.summary.files == 0
    assert report.largest_files == ()


def test_symlink_root_to_directory_is_reported_but_not_followed(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "inside.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(sub)
    report, error = build_filesystem_report(str(link), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.symlinks == 1
    assert report.summary.directories == 0
    assert report.summary.files == 0


def test_broken_symlink_root_is_reported_without_error(tmp_path: Path) -> None:
    link = tmp_path / "broken"
    link.symlink_to(tmp_path / "does-not-exist")
    report, error = build_filesystem_report(str(link), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.symlinks == 1


@pytest.mark.skipif(sys.platform == "win32", reason="mkfifo unavailable on Windows")
def test_special_file_root_counted_as_other(tmp_path: Path) -> None:
    fifo_path = tmp_path / "myfifo"
    os.mkfifo(str(fifo_path))
    report, error = build_filesystem_report(str(fifo_path), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.other == 1
    assert report.summary.files == 0


@pytest.mark.skipif(sys.platform == "win32", reason="mkfifo unavailable on Windows")
def test_nested_special_file_counted_as_other(tmp_path: Path) -> None:
    os.mkfifo(str(tmp_path / "myfifo"))
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.other == 1
    assert report.summary.files == 0


def test_missing_root_is_operational_failure(tmp_path: Path) -> None:
    missing = str(tmp_path / "does-not-exist")
    report, error = build_filesystem_report(missing, max_depth=2, max_entries=100, top=5)
    assert report is None
    assert error is not None
    assert "path not found" in error
    assert missing in error


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root bypasses permission checks"
)
def test_unreadable_root_is_operational_failure(tmp_path: Path) -> None:
    sub = tmp_path / "locked"
    sub.mkdir()
    parent_mode = tmp_path.stat().st_mode
    os.chmod(str(tmp_path), 0o000)
    try:
        target = str(sub)
        report, error = build_filesystem_report(target, max_depth=2, max_entries=100, top=5)
    finally:
        os.chmod(str(tmp_path), stat.S_IMODE(parent_mode))
    assert report is None
    assert error is not None
    assert "permission denied" in error
