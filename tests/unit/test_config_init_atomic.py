"""init_config_file() creates a secure, atomic configuration template."""

import os
import stat
from pathlib import Path

import pytest

from maops_pydevops.core.config import TEMPLATE, init_config_file
from maops_pydevops.core.config_models import ConfigInitStatus


def test_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "maops-py" / "config.toml"
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.CREATED
    assert target.parent.is_dir()


def test_template_content_written(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    init_config_file(target, force=False)
    assert target.read_text(encoding="utf-8") == TEMPLATE


def test_template_keys_are_documented_but_commented_out() -> None:
    for key in ("output_format", "command_timeout_seconds", "max_output_bytes"):
        assert f"# {key}" in TEMPLATE
    assert "\noutput_format =" not in TEMPLATE


def test_file_mode_is_0600_independent_of_umask(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    old_umask = os.umask(0o022)
    try:
        init_config_file(target, force=False)
    finally:
        os.umask(old_umask)
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600


def test_refuses_existing_file_without_force(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text('output_format = "text"\n', encoding="utf-8")
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.REFUSED_EXISTS
    assert target.read_text(encoding="utf-8") == 'output_format = "text"\n'


def test_force_replaces_existing_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("stale content\n", encoding="utf-8")
    result = init_config_file(target, force=True)
    assert result.status is ConfigInitStatus.CREATED
    assert target.read_text(encoding="utf-8") == TEMPLATE


def test_no_leftover_temp_file_after_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import maops_pydevops.core.config as config_module

    def _raise(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk full")

    monkeypatch.setattr(config_module.os, "fsync", _raise)
    target = tmp_path / "config.toml"
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.FAILED
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_no_leftover_fd_after_fchmod_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import maops_pydevops.core.config as config_module

    def _raise(*args: object, **kwargs: object) -> None:
        raise OSError("simulated fchmod failure")

    monkeypatch.setattr(config_module.os, "fchmod", _raise)
    target = tmp_path / "config.toml"
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.FAILED
    assert list(tmp_path.iterdir()) == []


def test_no_leftover_state_after_mkstemp_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import maops_pydevops.core.config as config_module

    def _raise(*args: object, **kwargs: object) -> OSError:
        raise OSError("simulated mkstemp failure")

    monkeypatch.setattr(config_module.tempfile, "mkstemp", _raise)
    target = tmp_path / "config.toml"
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.FAILED
    assert list(tmp_path.iterdir()) == []


def test_sentinel_files_in_same_directory_survive_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import maops_pydevops.core.config as config_module

    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    def _raise(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk full")

    monkeypatch.setattr(config_module.os, "fsync", _raise)
    target = tmp_path / "config.toml"
    init_config_file(target, force=False)
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_does_not_modify_existing_parent_directory_permissions(tmp_path: Path) -> None:
    parent = tmp_path / "existing"
    parent.mkdir(mode=0o750)
    before = stat.S_IMODE(parent.stat().st_mode)
    init_config_file(parent / "config.toml", force=False)
    after = stat.S_IMODE(parent.stat().st_mode)
    assert before == after


def test_success_detail_mentions_path(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    result = init_config_file(target, force=False)
    assert str(target) in result.detail
