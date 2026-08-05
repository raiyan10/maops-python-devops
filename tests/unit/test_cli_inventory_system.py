"""``maops-py inventory system`` CLI wiring: text/JSON output, dispatch, exit code."""

import json
from pathlib import Path

import pytest

from maops_pydevops.cli import EXIT_SUCCESS, main


def test_default_format_is_text(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["inventory", "system"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "System Inventory" in out
    assert "Hostname:" in out
    assert "Overall status:" in out


def test_explicit_text_format(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["inventory", "system", "--format", "text"])
    assert exit_code == EXIT_SUCCESS
    assert "System Inventory" in capsys.readouterr().out


def test_json_format_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["inventory", "system", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, dict)
    assert data["overall"] in ("pass", "warn", "fail")


def test_invalid_format_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "system", "--format", "xml"])
    assert exc_info.value.code == 2


def test_no_ansi_in_output(capsys: pytest.CaptureFixture[str]) -> None:
    main(["inventory", "system"])
    assert "\x1b" not in capsys.readouterr().out


def test_exit_code_is_always_success_regardless_of_config_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """inventory system never resolves the configuration file, so an
    invalid config file must never affect its exit code (unlike tools
    inspect / config show)."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("output_format = 123\n", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(config_file))
    exit_code = main(["inventory", "system"])
    assert exit_code == EXIT_SUCCESS
