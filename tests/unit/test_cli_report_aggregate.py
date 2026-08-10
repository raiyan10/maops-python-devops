"""``maops-py report aggregate`` CLI wiring: flags, formats, --output, exit codes."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main

_DOCTOR_JSON: dict[str, object] = {
    "version": "0.6.0",
    "python": {"version": "3.12.0", "executable": "/usr/bin/python3", "supported": True},
    "platform": {
        "system": "Linux",
        "release": "6.8.0",
        "architecture": "x86_64",
        "filesystem_encoding": "utf-8",
    },
    "checks": [{"name": "python_version", "status": "pass", "required": True, "detail": "ok"}],
    "overall": "pass",
}


def _write_report(path: Path, data: dict[str, object] | None = None) -> str:
    path.write_text(json.dumps(data if data is not None else _DOCTOR_JSON), encoding="utf-8")
    return str(path)


def test_report_appears_in_root_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "report" in capsys.readouterr().out


def test_report_aggregate_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["report", "aggregate", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--format" in out
    assert "--output" in out
    assert "--force" in out


def test_default_format_is_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_report(tmp_path / "doctor.json")
    exit_code = main(["report", "aggregate", path])
    assert exit_code == EXIT_SUCCESS
    assert "Aggregated Report" in capsys.readouterr().out


def test_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_report(tmp_path / "doctor.json")
    exit_code = main(["report", "aggregate", path, "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_markdown_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_report(tmp_path / "doctor.json")
    exit_code = main(["report", "aggregate", path, "--format", "markdown"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert out.startswith("# MAOps Aggregated Report")


def test_invalid_format_exits_two(tmp_path: Path) -> None:
    path = _write_report(tmp_path / "doctor.json")
    with pytest.raises(SystemExit) as exc_info:
        main(["report", "aggregate", path, "--format", "xml"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_missing_reports_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["report", "aggregate"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_fail_overall_exits_one(tmp_path: Path) -> None:
    fail_data = dict(_DOCTOR_JSON)
    fail_data["overall"] = "fail"
    fail_data["checks"] = [{"name": "x", "status": "fail", "required": True, "detail": "bad"}]
    path = _write_report(tmp_path / "doctor.json", fail_data)
    exit_code = main(["report", "aggregate", path, "--format", "json"])
    assert exit_code == EXIT_FAILURE


def test_malformed_report_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    exit_code = main(["report", "aggregate", str(path)])
    assert exit_code == EXIT_USAGE_ERROR
    assert "Error" in capsys.readouterr().err


def test_output_writes_file_and_stdout_is_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "out.json"
    exit_code = main(["report", "aggregate", path, "--format", "json", "--output", str(out_path)])
    assert exit_code == EXIT_SUCCESS
    assert capsys.readouterr().out == ""
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["overall"] == "pass"


def test_output_file_mode_is_0600(tmp_path: Path) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "out.json"
    exit_code = main(["report", "aggregate", path, "--output", str(out_path)])
    assert exit_code == EXIT_SUCCESS
    mode = stat.S_IMODE(os.stat(out_path).st_mode)
    assert mode == 0o600


def test_output_refuses_existing_file_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "out.json"
    out_path.write_text("existing content", encoding="utf-8")
    exit_code = main(["report", "aggregate", path, "--output", str(out_path)])
    assert exit_code == EXIT_FAILURE
    assert "already exists" in capsys.readouterr().err
    assert out_path.read_text(encoding="utf-8") == "existing content"


def test_output_force_overwrites_existing_file(tmp_path: Path) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "out.json"
    out_path.write_text("existing content", encoding="utf-8")
    exit_code = main(
        ["report", "aggregate", path, "--format", "json", "--output", str(out_path), "--force"]
    )
    assert exit_code == EXIT_SUCCESS
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["overall"] == "pass"


def test_output_missing_parent_directory_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "nonexistent-dir" / "out.json"
    exit_code = main(["report", "aggregate", path, "--output", str(out_path)])
    assert exit_code == EXIT_FAILURE
    assert "parent directory does not exist" in capsys.readouterr().err
    assert not out_path.exists()


def test_output_leaves_no_temp_file_on_refusal(tmp_path: Path) -> None:
    path = _write_report(tmp_path / "doctor.json")
    out_path = tmp_path / "out.json"
    out_path.write_text("existing", encoding="utf-8")
    main(["report", "aggregate", path, "--output", str(out_path)])
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".maops-py-report.")]
    assert leftovers == []


def test_output_refuses_symlink_target_even_with_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_report(tmp_path / "doctor.json")
    real_target = tmp_path / "real.json"
    real_target.write_text("do not touch", encoding="utf-8")
    link_path = tmp_path / "out.json"
    link_path.symlink_to(real_target)
    exit_code = main(["report", "aggregate", path, "--output", str(link_path), "--force"])
    assert exit_code == EXIT_FAILURE
    assert "symbolic link" in capsys.readouterr().err
    assert real_target.read_text(encoding="utf-8") == "do not touch"


def test_control_character_sanitized_in_text_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = dict(_DOCTOR_JSON)
    data["path"] = "irrelevant"
    fs_data = {
        "version": "0.6.0",
        "root": "/tmp/evil\x1b[31mFAKE",
        "options": {
            "max_depth": 2,
            "max_entries": 100,
            "top": 10,
            "follow_symlinks": False,
            "same_filesystem": True,
        },
        "summary": {
            "scanned_entries": 1,
            "directories": 0,
            "files": 1,
            "symlinks": 0,
            "other": 0,
            "total_file_bytes": 1,
            "skipped_entries": 0,
            "inaccessible_entries": 0,
            "different_filesystem_entries": 0,
        },
        "largest_files": [],
        "issues": [],
        "max_depth_reached": False,
        "truncated": False,
        "overall": "pass",
    }
    path = _write_report(tmp_path / "fs.json", fs_data)
    exit_code = main(["report", "aggregate", path])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\x1b" in out


def test_unicode_formatting_character_sanitized_in_text_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fs_data = {
        "version": "0.6.0",
        "root": "/tmp/‮evil",
        "options": {
            "max_depth": 2,
            "max_entries": 100,
            "top": 10,
            "follow_symlinks": False,
            "same_filesystem": True,
        },
        "summary": {
            "scanned_entries": 1,
            "directories": 0,
            "files": 1,
            "symlinks": 0,
            "other": 0,
            "total_file_bytes": 1,
            "skipped_entries": 0,
            "inaccessible_entries": 0,
            "different_filesystem_entries": 0,
        },
        "largest_files": [],
        "issues": [],
        "max_depth_reached": False,
        "truncated": False,
        "overall": "pass",
    }
    path = _write_report(tmp_path / "fs.json", fs_data)
    exit_code = main(["report", "aggregate", path])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "‮" not in out
    assert "\\u202e" in out
