"""init_config_file() never writes through a symlink at the target path."""

from pathlib import Path

from maops_pydevops.core.config import init_config_file
from maops_pydevops.core.config_models import ConfigInitStatus


def test_symlink_target_refused_without_force(tmp_path: Path) -> None:
    real_file = tmp_path / "real.toml"
    real_file.write_text("original contents\n", encoding="utf-8")
    link = tmp_path / "config.toml"
    link.symlink_to(real_file)

    result = init_config_file(link, force=False)

    assert result.status is ConfigInitStatus.REFUSED_SYMLINK
    assert link.is_symlink()
    assert real_file.read_text(encoding="utf-8") == "original contents\n"


def test_symlink_target_refused_with_force(tmp_path: Path) -> None:
    real_file = tmp_path / "real.toml"
    real_file.write_text("original contents\n", encoding="utf-8")
    link = tmp_path / "config.toml"
    link.symlink_to(real_file)

    result = init_config_file(link, force=True)

    assert result.status is ConfigInitStatus.REFUSED_SYMLINK
    assert link.is_symlink()
    assert real_file.read_text(encoding="utf-8") == "original contents\n"


def test_dangling_symlink_is_also_refused(tmp_path: Path) -> None:
    link = tmp_path / "config.toml"
    link.symlink_to(tmp_path / "does-not-exist.toml")

    result = init_config_file(link, force=True)

    assert result.status is ConfigInitStatus.REFUSED_SYMLINK
    assert link.is_symlink()
