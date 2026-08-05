"""--top 0 disables the largest-files list; ties break by path ascending."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_top_zero_disables_largest_files_but_still_sums_bytes(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x" * 10, encoding="utf-8")
    (tmp_path / "b.txt").write_text("y" * 20, encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=0)
    assert error is None
    assert report is not None
    assert report.largest_files == ()
    assert report.summary.total_file_bytes == 30


def test_top_n_returns_largest_files_size_descending(tmp_path: Path) -> None:
    (tmp_path / "small.txt").write_text("x" * 5, encoding="utf-8")
    (tmp_path / "big.txt").write_text("y" * 50, encoding="utf-8")
    (tmp_path / "medium.txt").write_text("z" * 25, encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=2)
    assert error is None
    assert report is not None
    assert len(report.largest_files) == 2
    assert report.largest_files[0].relative_path == "big.txt"
    assert report.largest_files[1].relative_path == "medium.txt"


def test_size_ties_break_by_path_ascending(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("x" * 10, encoding="utf-8")
    (tmp_path / "a.txt").write_text("y" * 10, encoding="utf-8")
    (tmp_path / "c.txt").write_text("z" * 5, encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=3)
    assert error is None
    assert report is not None
    assert [f.relative_path for f in report.largest_files] == ["a.txt", "b.txt", "c.txt"]
