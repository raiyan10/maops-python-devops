"""--max-entries boundary and deterministic mid-directory truncation."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_max_entries_exact_boundary_not_truncated(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=5, top=0)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 5
    assert report.truncated is False


def test_max_entries_below_total_truncates_deterministically(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=3, top=0)
    assert error is None
    assert report is not None
    assert report.summary.scanned_entries == 3
    assert report.truncated is True


def test_truncation_mid_directory_is_deterministic_across_runs(tmp_path: Path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    for i in range(3):
        (sub / f"g{i}.txt").write_text("y", encoding="utf-8")

    first, _ = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=4, top=0)
    second, _ = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=4, top=0)
    assert first is not None
    assert second is not None
    assert first.summary.scanned_entries == second.summary.scanned_entries == 4
    assert first.summary.directories == second.summary.directories
    assert first.summary.files == second.summary.files
    assert first.truncated is second.truncated is True
