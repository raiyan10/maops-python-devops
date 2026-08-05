"""Exhaustive JSON field-type coverage for ``inventory filesystem``."""

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import main


def test_json_field_types_complete(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.txt").write_text("x" * 10, encoding="utf-8")
    main(["inventory", "filesystem", str(tmp_path), "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert isinstance(data["version"], str)
    assert isinstance(data["root"], str)

    options = data["options"]
    assert isinstance(options["max_depth"], int)
    assert isinstance(options["max_entries"], int)
    assert isinstance(options["top"], int)
    assert options["follow_symlinks"] is False
    assert options["same_filesystem"] is True

    summary = data["summary"]
    for key in (
        "scanned_entries",
        "directories",
        "files",
        "symlinks",
        "other",
        "total_file_bytes",
        "skipped_entries",
        "inaccessible_entries",
        "different_filesystem_entries",
    ):
        assert isinstance(summary[key], int)

    assert isinstance(data["largest_files"], list)
    for entry in data["largest_files"]:
        assert isinstance(entry["path"], str)
        assert isinstance(entry["relative_path"], str)
        assert isinstance(entry["size_bytes"], int)
        assert isinstance(entry["modified_ns"], int)

    assert isinstance(data["issues"], list)
    for issue in data["issues"]:
        assert isinstance(issue["component"], str)
        assert issue["status"] in ("pass", "warn", "fail")
        assert isinstance(issue["detail"], str)

    assert isinstance(data["max_depth_reached"], bool)
    assert isinstance(data["truncated"], bool)
    assert data["overall"] in ("pass", "warn", "fail")


def test_json_explicit_null_fields_for_empty_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Empty issues/largest_files are explicit JSON [] arrays, never omitted."""
    main(["inventory", "filesystem", str(tmp_path), "--top", "0", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["largest_files"] == []
    assert data["issues"] == []
    assert "largest_files" in data
    assert "issues" in data
