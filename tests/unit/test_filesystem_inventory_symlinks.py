"""Nested symlinks -- to files, directories, and loops -- are counted, never followed."""

from pathlib import Path

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_nested_symlink_to_file_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("x" * 1000, encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.symlinks == 1
    assert report.summary.files == 1
    # The symlink itself never contributes to total_file_bytes.
    assert report.summary.total_file_bytes == 1000


def test_nested_symlink_to_directory_not_entered(tmp_path: Path) -> None:
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inside.txt").write_text("data", encoding="utf-8")
    (tmp_path / "link_dir").symlink_to(real_dir)

    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    # real_dir is entered normally (1 dir + 1 file inside), link_dir is
    # counted as a symlink and never entered a second time.
    assert report.summary.directories == 1
    assert report.summary.files == 1
    assert report.summary.symlinks == 1


def test_self_referential_symlink_loop_cannot_recurse(tmp_path: Path) -> None:
    (tmp_path / "self_loop").symlink_to(tmp_path)

    report, error = build_filesystem_report(str(tmp_path), max_depth=20, max_entries=1000, top=5)
    assert error is None
    assert report is not None
    assert report.summary.symlinks == 1
    assert report.summary.scanned_entries == 1


def test_indirect_symlink_cycle_cannot_recurse(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.mkdir()
    (a / "back_to_root").symlink_to(tmp_path)

    report, error = build_filesystem_report(str(tmp_path), max_depth=20, max_entries=1000, top=5)
    assert error is None
    assert report is not None
    assert report.summary.directories == 1
    assert report.summary.symlinks == 1
    assert report.summary.scanned_entries == 2
