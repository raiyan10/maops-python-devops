"""Unicode filenames, spaces, and shell metacharacters remain inert.

There is no subprocess/shell anywhere in the scanner, so this is
structurally guaranteed; these tests prove it empirically.
"""

import json
from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_unicode_filename_is_scanned_correctly(tmp_path: Path) -> None:
    name = "éè中文\U0001f600.txt"
    (tmp_path / name).write_text("data", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.files == 1
    assert report.largest_files[0].relative_path == name
    # Must also round-trip cleanly through JSON serialization.
    json.loads(report.to_json())


def test_filename_with_spaces_is_scanned_correctly(tmp_path: Path) -> None:
    name = "a file with spaces.txt"
    (tmp_path / name).write_text("data", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.largest_files[0].relative_path == name


def test_shell_metacharacters_in_filename_remain_inert(tmp_path: Path) -> None:
    name = "weird;name$(echo hi)[1]`bad`.txt"
    (tmp_path / name).write_text("data", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.files == 1
    assert report.largest_files[0].relative_path == name
    # Round-trips through JSON without any shell interpretation artifacts.
    data = json.loads(report.to_json())
    assert data["largest_files"][0]["relative_path"] == name


def test_directory_name_with_metacharacters_is_traversed(tmp_path: Path) -> None:
    sub = tmp_path / "dir;with$dollar"
    sub.mkdir()
    (sub / "inside.txt").write_text("x", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.directories == 1
    assert report.summary.files == 1
