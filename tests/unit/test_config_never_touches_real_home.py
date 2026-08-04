"""Config commands never write outside an isolated HOME, even when actually invoked."""

from pathlib import Path

import pytest

import maops_pydevops.core.config as config_module
from maops_pydevops.cli import main


def test_config_init_never_writes_outside_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)

    original_replace = config_module.os.replace

    def _guarded_replace(src: object, dst: object) -> object:
        assert str(dst).startswith(str(tmp_path)), f"write outside isolated HOME: {dst}"
        return original_replace(src, dst)

    monkeypatch.setattr(config_module.os, "replace", _guarded_replace)

    exit_code = main(["config", "init"])
    assert exit_code == 0
    assert (isolated_home / ".config" / "maops-py" / "config.toml").exists()


def test_all_config_subcommands_respect_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)

    for argv in (
        ["config", "path"],
        ["config", "init"],
        ["config", "validate"],
        ["config", "show"],
    ):
        main(argv)
        out = capsys.readouterr().out
        assert str(isolated_home) in out or "config.toml" in out


def test_config_init_force_write_also_confined_to_isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)

    main(["config", "init"])
    exit_code = main(["config", "init", "--force"])
    assert exit_code == 0
    assert (isolated_home / ".config" / "maops-py" / "config.toml").exists()
