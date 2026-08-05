"""Default root resolution: omitted path uses the current working directory."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_omitted_path_uses_provided_cwd(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    report, error = build_filesystem_report(
        None, max_depth=2, max_entries=100, top=5, cwd=str(tmp_path)
    )
    assert error is None
    assert report is not None
    assert report.root == str(tmp_path)
    assert report.summary.files == 1


def test_empty_directory_produces_zero_counts(tmp_path: Path) -> None:
    report, error = build_filesystem_report(str(tmp_path), max_depth=2, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 0
    assert report.summary.directories == 0
    assert report.summary.files == 0
    assert report.summary.total_file_bytes == 0
    assert report.largest_files == ()
    assert report.issues == ()
    assert report.overall.value == "pass"
