"""resolve_effective_config() precedence: CLI > environment > file > default."""

from pathlib import Path

from maops_pydevops.core.config import resolve_effective_config
from maops_pydevops.core.config_models import ConfigFileStatus, ConfigSource
from maops_pydevops.core.models import OutputFormat


def _write_config(tmp_path: Path, content: str) -> Path:
    config_file = tmp_path / "config.toml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


def test_missing_file_resolves_to_all_defaults(tmp_path: Path) -> None:
    resolution = resolve_effective_config(config_path=tmp_path / "missing.toml", env={})
    assert resolution.file_status is ConfigFileStatus.MISSING
    assert resolution.config is not None
    assert resolution.config.output_format is OutputFormat.TEXT
    assert resolution.config.command_timeout_seconds == 10.0
    assert resolution.config.max_output_bytes == 65536
    assert resolution.sources is not None
    assert resolution.sources.output_format is ConfigSource.DEFAULT
    assert resolution.sources.command_timeout_seconds is ConfigSource.DEFAULT
    assert resolution.sources.max_output_bytes is ConfigSource.DEFAULT


def test_file_value_wins_over_default(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'output_format = "json"\n')
    resolution = resolve_effective_config(config_path=path, env={})
    assert resolution.config is not None
    assert resolution.config.output_format is OutputFormat.JSON
    assert resolution.sources is not None
    assert resolution.sources.output_format is ConfigSource.FILE


def test_environment_wins_over_file(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'output_format = "json"\n')
    resolution = resolve_effective_config(config_path=path, env={"MAOPS_PY_OUTPUT_FORMAT": "text"})
    assert resolution.config is not None
    assert resolution.config.output_format is OutputFormat.TEXT
    assert resolution.sources is not None
    assert resolution.sources.output_format is ConfigSource.ENVIRONMENT


def test_cli_wins_over_environment_and_file(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'output_format = "json"\n')
    resolution = resolve_effective_config(
        cli_output_format="text",
        config_path=path,
        env={"MAOPS_PY_OUTPUT_FORMAT": "json"},
    )
    assert resolution.config is not None
    assert resolution.config.output_format is OutputFormat.TEXT
    assert resolution.sources is not None
    assert resolution.sources.output_format is ConfigSource.CLI


def test_cli_command_timeout_wins_over_all() -> None:
    resolution = resolve_effective_config(
        cli_command_timeout_seconds=42.0,
        config_path=Path("/nonexistent/config.toml"),
        env={"MAOPS_PY_COMMAND_TIMEOUT_SECONDS": "5"},
    )
    assert resolution.config is not None
    assert resolution.config.command_timeout_seconds == 42.0
    assert resolution.sources is not None
    assert resolution.sources.command_timeout_seconds is ConfigSource.CLI


def test_environment_max_output_bytes_wins_over_file(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "max_output_bytes = 4096\n")
    resolution = resolve_effective_config(
        config_path=path, env={"MAOPS_PY_MAX_OUTPUT_BYTES": "2048"}
    )
    assert resolution.config is not None
    assert resolution.config.max_output_bytes == 2048
    assert resolution.sources is not None
    assert resolution.sources.max_output_bytes is ConfigSource.ENVIRONMENT


def test_file_value_wins_for_command_timeout_seconds(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "command_timeout_seconds = 25.0\n")
    resolution = resolve_effective_config(config_path=path, env={})
    assert resolution.config is not None
    assert resolution.config.command_timeout_seconds == 25.0
    assert resolution.sources is not None
    assert resolution.sources.command_timeout_seconds is ConfigSource.FILE


def test_file_value_wins_for_max_output_bytes(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "max_output_bytes = 8192\n")
    resolution = resolve_effective_config(config_path=path, env={})
    assert resolution.config is not None
    assert resolution.config.max_output_bytes == 8192
    assert resolution.sources is not None
    assert resolution.sources.max_output_bytes is ConfigSource.FILE


def test_invalid_environment_timeout_syntax_fails(tmp_path: Path) -> None:
    resolution = resolve_effective_config(
        config_path=tmp_path / "missing.toml",
        env={"MAOPS_PY_COMMAND_TIMEOUT_SECONDS": "not-numeric"},
    )
    assert resolution.config is None
    assert resolution.error is not None


def test_invalid_environment_timeout_out_of_range_fails(tmp_path: Path) -> None:
    resolution = resolve_effective_config(
        config_path=tmp_path / "missing.toml",
        env={"MAOPS_PY_COMMAND_TIMEOUT_SECONDS": "500"},
    )
    assert resolution.config is None
    assert resolution.error is not None


def test_invalid_environment_max_output_bytes_syntax_fails(tmp_path: Path) -> None:
    resolution = resolve_effective_config(
        config_path=tmp_path / "missing.toml",
        env={"MAOPS_PY_MAX_OUTPUT_BYTES": "not-an-integer"},
    )
    assert resolution.config is None
    assert resolution.error is not None


def test_invalid_environment_output_format_fails_operationally(tmp_path: Path) -> None:
    resolution = resolve_effective_config(
        config_path=tmp_path / "missing.toml", env={"MAOPS_PY_OUTPUT_FORMAT": "xml"}
    )
    assert resolution.config is None
    assert resolution.sources is None
    assert resolution.error is not None
    assert "MAOPS_PY_OUTPUT_FORMAT" in resolution.error


def test_invalid_environment_timeout_does_not_silently_fall_back(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "command_timeout_seconds = 20.0\n")
    resolution = resolve_effective_config(
        config_path=path, env={"MAOPS_PY_COMMAND_TIMEOUT_SECONDS": "not-a-number"}
    )
    assert resolution.config is None
    assert resolution.error is not None


def test_invalid_environment_max_output_bytes_fails() -> None:
    resolution = resolve_effective_config(
        config_path=Path("/nonexistent/config.toml"),
        env={"MAOPS_PY_MAX_OUTPUT_BYTES": "99999999"},
    )
    assert resolution.config is None
    assert resolution.error is not None


def test_invalid_file_fails_resolution(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "not valid toml [[[")
    resolution = resolve_effective_config(config_path=path, env={})
    assert resolution.file_status is ConfigFileStatus.INVALID
    assert resolution.config is None
    assert resolution.error is not None


def test_schema_invalid_file_fails_resolution(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "unknown_key = 1\n")
    resolution = resolve_effective_config(config_path=path, env={})
    assert resolution.file_status is ConfigFileStatus.INVALID
    assert resolution.config is None


def test_all_three_fields_resolved_independently(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'output_format = "json"\n')
    resolution = resolve_effective_config(
        cli_command_timeout_seconds=5.0,
        config_path=path,
        env={"MAOPS_PY_MAX_OUTPUT_BYTES": "2048"},
    )
    assert resolution.config is not None
    assert resolution.config.output_format is OutputFormat.JSON
    assert resolution.config.command_timeout_seconds == 5.0
    assert resolution.config.max_output_bytes == 2048
    assert resolution.sources is not None
    assert resolution.sources.output_format is ConfigSource.FILE
    assert resolution.sources.command_timeout_seconds is ConfigSource.CLI
    assert resolution.sources.max_output_bytes is ConfigSource.ENVIRONMENT


def test_default_config_path_used_when_not_specified(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    resolution = resolve_effective_config(env=env)
    assert resolution.path == str(tmp_path / "maops-py" / "config.toml")
