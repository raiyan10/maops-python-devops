"""``maops-py logs parse`` CLI wiring: validation, format, exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main


@pytest.fixture(autouse=True)
def _isolated_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)
    monkeypatch.delenv("MAOPS_PY_OUTPUT_FORMAT", raising=False)


def _write_log(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "test.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_logs_appears_in_root_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "logs" in capsys.readouterr().out


def test_logs_parse_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--input-format" in out
    assert "--max-events" in out


def test_default_format_is_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    exit_code = main(["logs", "parse", str(path)])
    assert exit_code == EXIT_SUCCESS
    assert "Log Parse Report" in capsys.readouterr().out


def test_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    exit_code = main(["logs", "parse", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_cli_format_overrides_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    home = tmp_path / "isolated-home"
    config_dir = home / ".config" / "maops-py"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('output_format = "json"\n', encoding="utf-8")
    exit_code = main(["logs", "parse", str(path), "--format", "text"])
    assert exit_code == EXIT_SUCCESS
    assert "Log Parse Report" in capsys.readouterr().out


def test_config_derived_format_used_when_no_cli_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    home = tmp_path / "isolated-home"
    config_dir = home / ".config" / "maops-py"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('output_format = "json"\n', encoding="utf-8")
    exit_code = main(["logs", "parse", str(path)])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_invalid_input_format_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse", str(path), "--input-format", "bogus"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_invalid_format_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse", str(path), "--format", "xml"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


@pytest.mark.parametrize(
    ("flag", "bad_value"),
    [
        ("--max-lines", "abc"),
        ("--max-lines", "0"),
        ("--max-lines", "1000001"),
        ("--max-bytes", "abc"),
        ("--max-bytes", "1023"),
        ("--max-bytes", "104857601"),
        ("--max-line-bytes", "abc"),
        ("--max-line-bytes", "255"),
        ("--max-line-bytes", "1048577"),
        ("--max-events", "abc"),
        ("--max-events", "-1"),
        ("--max-events", "10001"),
    ],
)
def test_bounded_int_flags_invalid_syntax_and_range(
    tmp_path: Path, flag: str, bad_value: str
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse", str(path), flag, bad_value])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_bounded_int_flags_boundary_values_valid(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    assert main(["logs", "parse", str(path), "--max-lines", "1"]) == EXIT_SUCCESS
    assert main(["logs", "parse", str(path), "--max-bytes", "1024"]) == EXIT_SUCCESS
    assert main(["logs", "parse", str(path), "--max-line-bytes", "256"]) == EXIT_SUCCESS
    assert main(["logs", "parse", str(path), "--max-events", "0"]) == EXIT_SUCCESS


def test_missing_path_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_additional_positional_path_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "parse", str(path), str(path)])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_nonexistent_path_exits_one(tmp_path: Path) -> None:
    exit_code = main(["logs", "parse", str(tmp_path / "nope.log")])
    assert exit_code == EXIT_FAILURE


def test_no_redact_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "password=hunter2secretvalue"}))
    exit_code = main(["logs", "parse", str(path), "--no-redact", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "hunter2secretvalue" in out


def test_default_redacts_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "password=hunter2secretvalue"}))
    exit_code = main(["logs", "parse", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "hunter2secretvalue" not in out


def test_nonempty_zero_events_exits_one(tmp_path: Path) -> None:
    path = _write_log(tmp_path, "not json {", "still not json {")
    exit_code = main(["logs", "parse", str(path), "--input-format", "jsonl"])
    assert exit_code == EXIT_FAILURE


def test_warning_report_exits_zero(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "ok"}), "not json {")
    exit_code = main(["logs", "parse", str(path), "--input-format", "jsonl"])
    assert exit_code == EXIT_SUCCESS


def test_invalid_environment_config_value_exits_one_before_opening_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    monkeypatch.setenv("MAOPS_PY_OUTPUT_FORMAT", "not-a-real-format")
    exit_code = main(["logs", "parse", str(path)])
    assert exit_code == EXIT_FAILURE
    assert "Error" in capsys.readouterr().err


def test_root_version_precedence_still_works_with_logs_present() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version", "logs"])
    assert exc_info.value.code == EXIT_USAGE_ERROR
