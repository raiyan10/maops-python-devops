"""``maops-py logs analyze`` CLI wiring: validation, format, exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main


def _write_log(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "test.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_logs_analyze_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--bucket-seconds" in out
    assert "--repeat-threshold" in out
    assert "--error-threshold" in out


def test_default_format_is_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    exit_code = main(["logs", "analyze", str(path)])
    assert exit_code == EXIT_SUCCESS
    assert "Log Analysis Report" in capsys.readouterr().out


def test_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # An event with no severity field is UNKNOWN, which itself triggers
    # the "unknown_severity" finding -- use an explicit severity here so
    # this test isolates JSON-format validity, not finding generation.
    path = _write_log(tmp_path, json.dumps({"message": "hi", "severity": "info"}))
    exit_code = main(["logs", "analyze", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_cli_format_overrides_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    home = tmp_path / "isolated-home"
    config_dir = home / ".config" / "maops-py"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('output_format = "json"\n', encoding="utf-8")
    exit_code = main(["logs", "analyze", str(path), "--format", "text"])
    assert exit_code == EXIT_SUCCESS
    assert "Log Analysis Report" in capsys.readouterr().out


def test_invalid_input_format_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze", str(path), "--input-format", "bogus"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_invalid_format_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze", str(path), "--format", "xml"])
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
        ("--top", "abc"),
        ("--top", "-1"),
        ("--top", "101"),
        ("--bucket-seconds", "abc"),
        ("--bucket-seconds", "0"),
        ("--bucket-seconds", "86401"),
        ("--repeat-threshold", "abc"),
        ("--repeat-threshold", "1"),
        ("--repeat-threshold", "1000001"),
        ("--error-threshold", "abc"),
        ("--error-threshold", "0"),
        ("--error-threshold", "1000001"),
    ],
)
def test_bounded_int_flags_invalid_syntax_and_range(
    tmp_path: Path, flag: str, bad_value: str
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze", str(path), flag, bad_value])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_bounded_int_flags_boundary_values_valid(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    assert main(["logs", "analyze", str(path), "--top", "0"]) == EXIT_SUCCESS
    assert main(["logs", "analyze", str(path), "--top", "100"]) == EXIT_SUCCESS
    assert main(["logs", "analyze", str(path), "--bucket-seconds", "1"]) == EXIT_SUCCESS
    assert main(["logs", "analyze", str(path), "--bucket-seconds", "86400"]) == EXIT_SUCCESS
    assert main(["logs", "analyze", str(path), "--repeat-threshold", "2"]) == EXIT_SUCCESS
    assert main(["logs", "analyze", str(path), "--error-threshold", "1"]) == EXIT_SUCCESS


def test_missing_path_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_additional_positional_path_exits_two(tmp_path: Path) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    with pytest.raises(SystemExit) as exc_info:
        main(["logs", "analyze", str(path), str(path)])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_nonexistent_path_exits_one(tmp_path: Path) -> None:
    exit_code = main(["logs", "analyze", str(tmp_path / "nope.log")])
    assert exit_code == EXIT_FAILURE


def test_no_redact_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "password=hunter2secretvalue"}))
    exit_code = main(["logs", "analyze", str(path), "--no-redact", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "hunter2secretvalue" in out


def test_default_redacts_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "password=hunter2secretvalue"}))
    exit_code = main(["logs", "analyze", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "hunter2secretvalue" not in out


def test_nonempty_zero_events_exits_one(tmp_path: Path) -> None:
    path = _write_log(tmp_path, "not json {", "still not json {")
    exit_code = main(["logs", "analyze", str(path), "--input-format", "jsonl"])
    assert exit_code == EXIT_FAILURE


def test_warning_report_with_findings_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "ok", "severity": "error"}), "not json {")
    exit_code = main(
        ["logs", "analyze", str(path), "--input-format", "jsonl", "--error-threshold", "1"]
    )
    assert exit_code == EXIT_SUCCESS
    assert "WARN" in capsys.readouterr().out


def test_invalid_environment_config_value_exits_one_before_opening_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi"}))
    monkeypatch.setenv("MAOPS_PY_OUTPUT_FORMAT", "not-a-real-format")
    exit_code = main(["logs", "analyze", str(path)])
    assert exit_code == EXIT_FAILURE
    assert "Error" in capsys.readouterr().err


def test_config_derived_format_used_when_no_cli_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_log(tmp_path, json.dumps({"message": "hi", "severity": "info"}))
    home = tmp_path / "isolated-home"
    config_dir = home / ".config" / "maops-py"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('output_format = "json"\n', encoding="utf-8")
    exit_code = main(["logs", "analyze", str(path)])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_root_version_precedence_still_works_with_logs_present() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version", "logs"])
    assert exc_info.value.code == EXIT_USAGE_ERROR
