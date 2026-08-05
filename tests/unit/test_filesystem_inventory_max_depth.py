"""--max-depth boundary semantics (worked examples from docs/inventory.md)."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_max_depth_zero_never_scans_root_children(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=0, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 0
    assert report.max_depth_reached is True


def test_max_depth_one_scans_direct_children_but_not_grandchildren(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "b.txt").write_text("y", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=1, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 2
    assert report.summary.files == 1
    assert report.summary.directories == 1
    assert report.max_depth_reached is True


def test_max_depth_boundary_directory_still_counted_but_not_descended(tmp_path: Path) -> None:
    level1 = tmp_path / "level1"
    level1.mkdir()
    level2 = level1 / "level2"
    level2.mkdir()
    (level2 / "deep.txt").write_text("z", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    # level1 (depth1) and level2 (depth2) are both counted as directories;
    # level2's own contents (depth3) are never enumerated.
    assert report.summary.directories == 2
    assert report.summary.files == 0
    assert report.max_depth_reached is True


def test_deeper_than_needed_max_depth_never_sets_reached(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=10, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.max_depth_reached is False
