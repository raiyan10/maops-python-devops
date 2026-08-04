"""init_config_file() refuses directory and other non-regular targets unconditionally."""

import os
from pathlib import Path

import pytest

from maops_pydevops.core.config import init_config_file
from maops_pydevops.core.config_models import ConfigInitStatus


def test_directory_target_refused_without_force(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.mkdir()
    result = init_config_file(target, force=False)
    assert result.status is ConfigInitStatus.REFUSED_NOT_REGULAR
    assert target.is_dir()


def test_directory_target_refused_with_force(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.mkdir()
    result = init_config_file(target, force=True)
    assert result.status is ConfigInitStatus.REFUSED_NOT_REGULAR
    assert target.is_dir()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo unavailable on this platform")
def test_fifo_target_refused_unconditionally(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    os.mkfifo(target)
    result = init_config_file(target, force=True)
    assert result.status is ConfigInitStatus.REFUSED_NOT_REGULAR
