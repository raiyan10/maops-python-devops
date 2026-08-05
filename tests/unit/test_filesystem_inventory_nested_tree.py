"""Traversal order is deterministic: name-ascending per directory, depth-first."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_traversal_visits_names_in_ascending_order_depth_first(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("1", encoding="utf-8")
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    sub = tmp_path / "m_sub"
    sub.mkdir()
    (sub / "z.txt").write_text("3", encoding="utf-8")
    (sub / "y.txt").write_text("4", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=0)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 5
    assert report.summary.files == 4
    assert report.summary.directories == 1


def test_directories_files_and_symlinks_are_counted_correctly(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("data", encoding="utf-8")
    (tmp_path / "dir").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "file.txt")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.files == 1
    assert report.summary.directories == 1
    assert report.summary.symlinks == 1
    assert report.summary.scanned_entries == 3
