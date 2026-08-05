"""``maops-py inventory filesystem`` CLI wiring: validation, format, exit codes."""

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main


def test_omitted_path_scans_current_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    exit_code = main(["inventory", "filesystem", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["root"] == str(tmp_path)


def test_explicit_path_argument(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["inventory", "filesystem", str(tmp_path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["root"] == str(tmp_path)


def test_default_format_is_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["inventory", "filesystem", str(tmp_path)])
    assert exit_code == EXIT_SUCCESS
    assert "Filesystem Inventory" in capsys.readouterr().out


def test_invalid_format_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--format", "xml"])
    assert exc_info.value.code == 2


def test_extra_positional_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), str(tmp_path)])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_max_depth_invalid_syntax_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-depth", "abc"])
    assert exc_info.value.code == 2


def test_max_depth_out_of_range_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-depth", "65"])
    assert exc_info.value.code == 2


def test_max_depth_negative_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-depth", "-1"])
    assert exc_info.value.code == 2


def test_max_entries_invalid_syntax_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-entries", "abc"])
    assert exc_info.value.code == 2


def test_max_entries_below_minimum_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-entries", "0"])
    assert exc_info.value.code == 2


def test_max_entries_above_maximum_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--max-entries", "1000001"])
    assert exc_info.value.code == 2


def test_top_invalid_syntax_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--top", "abc"])
    assert exc_info.value.code == 2


def test_top_out_of_range_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", str(tmp_path), "--top", "101"])
    assert exc_info.value.code == 2


def test_top_boundary_values_are_valid(tmp_path: Path) -> None:
    assert main(["inventory", "filesystem", str(tmp_path), "--top", "0"]) == EXIT_SUCCESS
    assert main(["inventory", "filesystem", str(tmp_path), "--top", "100"]) == EXIT_SUCCESS


def test_max_depth_boundary_values_are_valid(tmp_path: Path) -> None:
    assert main(["inventory", "filesystem", str(tmp_path), "--max-depth", "0"]) == EXIT_SUCCESS
    assert main(["inventory", "filesystem", str(tmp_path), "--max-depth", "64"]) == EXIT_SUCCESS


def test_max_entries_boundary_values_are_valid(tmp_path: Path) -> None:
    assert main(["inventory", "filesystem", str(tmp_path), "--max-entries", "1"]) == EXIT_SUCCESS
    assert (
        main(["inventory", "filesystem", str(tmp_path), "--max-entries", "1000000"]) == EXIT_SUCCESS
    )


def test_nonexistent_root_exits_one(tmp_path: Path) -> None:
    missing = str(tmp_path / "nope")
    exit_code = main(["inventory", "filesystem", missing])
    assert exit_code == EXIT_FAILURE


def test_error_message_preserves_user_supplied_path_lexically(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["inventory", "filesystem", "./relative/does-not-exist"])
    assert exit_code == EXIT_FAILURE
    err = capsys.readouterr().err
    assert "./relative/does-not-exist" in err


def test_root_is_normalized_absolute_path_lexically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    relative = str(sub) + "/.."
    exit_code = main(["inventory", "filesystem", relative, "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["root"] == str(tmp_path)
