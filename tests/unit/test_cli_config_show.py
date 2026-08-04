"""``maops-py config show`` text/JSON rendering and invalid-config hard failure."""

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import main


def test_missing_file_shows_defaults_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    exit_code = main(["config", "show", "--format", "json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["exists"] is False
    assert data["valid"] is False
    assert data["values"]["output_format"] == "text"
    assert data["sources"]["output_format"] == "default"


def test_valid_file_shows_exists_and_valid_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('output_format = "json"\n', encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "show", "--format", "json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["exists"] is True
    assert data["valid"] is True
    assert data["values"]["output_format"] == "json"
    assert data["sources"]["output_format"] == "file"


def test_invalid_file_exits_one_with_no_report_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("not valid toml [[[", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "show", "--format", "json"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error" in captured.err


def test_invalid_environment_value_also_hard_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("MAOPS_PY_COMMAND_TIMEOUT_SECONDS", "not-a-number")
    exit_code = main(["config", "show"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error" in captured.err


def test_text_output_contains_path_and_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    exit_code = main(["config", "show", "--format", "text"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert str(tmp_path / "missing.toml") in out
    assert "output_format" in out


def test_json_has_no_ansi_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    main(["config", "show", "--format", "json"])
    assert "\x1b" not in capsys.readouterr().out


def test_json_field_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    main(["config", "show", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data["path"], str)
    assert isinstance(data["exists"], bool)
    assert isinstance(data["valid"], bool)
    assert isinstance(data["values"]["command_timeout_seconds"], float)
    assert isinstance(data["values"]["max_output_bytes"], int)
    assert isinstance(data["sources"]["output_format"], str)


def test_default_format_falls_back_to_effective_output_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('output_format = "json"\n', encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "show"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["values"]["output_format"] == "json"


def test_invalid_format_choice_exits_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "show", "--format", "yaml"])
    assert exc_info.value.code == 2
