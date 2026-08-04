"""``maops-py config validate`` exit codes: 0 valid, 1 missing/invalid, 2 usage error."""

from pathlib import Path

import pytest

from maops_pydevops.cli import main


def test_valid_file_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('output_format = "json"\n', encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "validate"])
    assert exit_code == 0
    assert "valid" in capsys.readouterr().out


def test_missing_file_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "missing.toml"))
    exit_code = main(["config", "validate"])
    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_malformed_toml_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("not valid toml [[[", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "validate"])
    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_schema_invalid_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("unknown_key = 1\n", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["config", "validate"])
    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_explicit_path_argument_is_used(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_file = tmp_path / "other.toml"
    config_file.write_text('output_format = "text"\n', encoding="utf-8")
    exit_code = main(["config", "validate", str(config_file)])
    assert exit_code == 0
    assert str(config_file) in capsys.readouterr().out


def test_unexpected_extra_positional_argument_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "validate", str(tmp_path / "a.toml"), str(tmp_path / "b.toml")])
    assert exc_info.value.code == 2


def test_unknown_flag_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "validate", "--bogus"])
    assert exc_info.value.code == 2
