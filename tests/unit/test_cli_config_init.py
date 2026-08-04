"""``maops-py config init`` success and refusal exit codes via the CLI."""

from pathlib import Path

import pytest

from maops_pydevops.cli import main


def test_init_creates_file_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "config.toml"
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(target))
    exit_code = main(["config", "init"])
    assert exit_code == 0
    assert target.exists()


def test_init_refuses_existing_file_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "config.toml"
    target.write_text("stale\n", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(target))
    exit_code = main(["config", "init"])
    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_init_force_flag_replaces_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "config.toml"
    target.write_text("stale\n", encoding="utf-8")
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(target))
    exit_code = main(["config", "init", "--force"])
    assert exit_code == 0
