"""resolve_config_path() precedence: MAOPS_PY_CONFIG_FILE > XDG_CONFIG_HOME > HOME."""

from pathlib import Path

import pytest

from maops_pydevops.core.config import resolve_config_path


def test_explicit_override_wins_over_everything() -> None:
    env = {
        "MAOPS_PY_CONFIG_FILE": "/explicit/path/config.toml",
        "XDG_CONFIG_HOME": "/xdg",
        "HOME": "/home/user",
    }
    assert resolve_config_path(env=env) == Path("/explicit/path/config.toml")


def test_xdg_config_home_used_when_no_explicit_override() -> None:
    env = {"XDG_CONFIG_HOME": "/xdg", "HOME": "/home/user"}
    assert resolve_config_path(env=env) == Path("/xdg/maops-py/config.toml")


def test_home_fallback_when_xdg_absent() -> None:
    env = {"HOME": "/home/user"}
    assert resolve_config_path(env=env) == Path("/home/user/.config/maops-py/config.toml")


def test_empty_xdg_config_home_falls_back_to_home() -> None:
    env = {"XDG_CONFIG_HOME": "", "HOME": "/home/user"}
    assert resolve_config_path(env=env) == Path("/home/user/.config/maops-py/config.toml")


def test_empty_explicit_override_falls_back_to_xdg() -> None:
    env = {"MAOPS_PY_CONFIG_FILE": "", "XDG_CONFIG_HOME": "/xdg", "HOME": "/home/user"}
    assert resolve_config_path(env=env) == Path("/xdg/maops-py/config.toml")


def test_path_with_spaces_is_preserved_verbatim() -> None:
    env = {"HOME": "/home/user name with spaces"}
    assert resolve_config_path(env=env) == Path(
        "/home/user name with spaces/.config/maops-py/config.toml"
    )


def test_shell_metacharacters_in_path_remain_inert() -> None:
    env = {"MAOPS_PY_CONFIG_FILE": "/tmp/$(rm -rf /)/config.toml"}
    resolved = resolve_config_path(env=env)
    assert str(resolved) == "/tmp/$(rm -rf /)/config.toml"


def test_default_env_uses_real_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/injected")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)
    assert resolve_config_path() == Path("/home/injected/.config/maops-py/config.toml")
