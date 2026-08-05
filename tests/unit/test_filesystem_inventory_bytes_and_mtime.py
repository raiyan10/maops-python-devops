"""Total apparent byte count and nanosecond-precision modification time."""

import os
from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_total_file_bytes_sums_all_regular_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x" * 100, encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y" * 250, encoding="utf-8")

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=0)
    assert error is None
    assert report is not None
    assert report.summary.total_file_bytes == 350


def test_modified_ns_matches_real_mtime_ns(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("hello", encoding="utf-8")
    expected_ns = os.stat(target).st_mtime_ns

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.largest_files[0].modified_ns == expected_ns
    assert isinstance(report.largest_files[0].modified_ns, int)
