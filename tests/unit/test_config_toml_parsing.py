"""parse_toml_file() distinguishes missing, malformed, and valid configuration files."""

from pathlib import Path

from maops_pydevops.core.config import parse_toml_file
from maops_pydevops.core.config_models import ConfigFileStatus


def test_missing_file_is_reported_as_missing(tmp_path: Path) -> None:
    result = parse_toml_file(tmp_path / "does-not-exist.toml")
    assert result.status is ConfigFileStatus.MISSING
    assert result.raw is None
    assert result.error is None


def test_malformed_toml_is_reported_as_invalid(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("this is not = = valid toml [[[", encoding="utf-8")
    result = parse_toml_file(config_file)
    assert result.status is ConfigFileStatus.INVALID
    assert result.raw is None
    assert result.error is not None


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('output_format = "text"\noutput_format = "json"\n', encoding="utf-8")
    result = parse_toml_file(config_file)
    assert result.status is ConfigFileStatus.INVALID
    assert result.raw is None


def test_valid_toml_is_parsed(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'output_format = "json"\ncommand_timeout_seconds = 5.0\nmax_output_bytes = 2048\n',
        encoding="utf-8",
    )
    result = parse_toml_file(config_file)
    assert result.status is ConfigFileStatus.VALID
    assert result.raw == {
        "output_format": "json",
        "command_timeout_seconds": 5.0,
        "max_output_bytes": 2048,
    }
    assert result.error is None


def test_empty_file_parses_to_empty_document(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("", encoding="utf-8")
    result = parse_toml_file(config_file)
    assert result.status is ConfigFileStatus.VALID
    assert result.raw == {}


def test_unreadable_file_is_reported_as_invalid(tmp_path: Path) -> None:
    config_dir_as_file = tmp_path / "config.toml"
    config_dir_as_file.mkdir()
    result = parse_toml_file(config_dir_as_file)
    assert result.status is ConfigFileStatus.INVALID
    assert result.raw is None
