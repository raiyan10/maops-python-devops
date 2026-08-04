"""Configuration file location, parsing, validation, precedence, and init.

The only module in ``src/maops_pydevops`` permitted to read named
environment variables or write outside a build/test temporary directory.
Never imports ``subprocess``.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import TypeGuard

from maops_pydevops.core.config_models import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_OUTPUT_FORMAT,
    KNOWN_CONFIG_KEYS,
    MAX_COMMAND_TIMEOUT_SECONDS,
    MAX_MAX_OUTPUT_BYTES,
    MIN_COMMAND_TIMEOUT_SECONDS,
    MIN_MAX_OUTPUT_BYTES,
    ConfigFileStatus,
    ConfigInitResult,
    ConfigInitStatus,
    ConfigResolution,
    ConfigSource,
    EffectiveConfig,
    EffectiveConfigSources,
    SchemaValidationResult,
    TomlParseResult,
    ValidatedConfigValues,
    is_valid_command_timeout_seconds,
)
from maops_pydevops.core.models import OutputFormat

TEMPLATE = """\
# maops-py configuration file
#
# Uncomment and edit any of the following keys to override the built-in
# defaults. Every value shown below already matches maops-py's default, so
# this file changes nothing until you edit it.
#
# output_format = "text"          # "text" or "json"
# command_timeout_seconds = 10.0  # > 0, <= 300
# max_output_bytes = 65536        # >= 1024, <= 1048576
#
# No secret, token, or credential values are ever supported here.
"""


def resolve_config_path(*, env: Mapping[str, str] | None = None) -> Path:
    """Resolve the configuration file path: explicit override, then XDG, then HOME."""
    active_env = env if env is not None else os.environ
    explicit = active_env.get("MAOPS_PY_CONFIG_FILE")
    if explicit:
        return Path(explicit)
    xdg_config_home = active_env.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "maops-py" / "config.toml"
    home = active_env.get("HOME", "")
    return Path(home) / ".config" / "maops-py" / "config.toml"


def parse_toml_file(path: Path) -> TomlParseResult:
    """Parse ``path`` as TOML, distinguishing missing from malformed files."""
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        return TomlParseResult(status=ConfigFileStatus.MISSING, raw=None, error=None)
    except tomllib.TOMLDecodeError as exc:
        return TomlParseResult(status=ConfigFileStatus.INVALID, raw=None, error=str(exc))
    except OSError as exc:
        return TomlParseResult(status=ConfigFileStatus.INVALID, raw=None, error=str(exc))
    return TomlParseResult(status=ConfigFileStatus.VALID, raw=raw, error=None)


def _is_numeric_non_bool(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int_non_bool(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_config_schema(raw: dict[str, object]) -> SchemaValidationResult:
    """Validate a parsed TOML document against the supported configuration schema."""
    unknown_keys = set(raw.keys()) - KNOWN_CONFIG_KEYS
    if unknown_keys:
        return SchemaValidationResult(
            valid=False,
            values=None,
            error=f"unknown configuration key(s): {', '.join(sorted(unknown_keys))}",
        )

    output_format: str | None = None
    command_timeout_seconds: float | None = None
    max_output_bytes: int | None = None

    if "output_format" in raw:
        candidate = raw["output_format"]
        if not isinstance(candidate, str) or candidate not in {fmt.value for fmt in OutputFormat}:
            return SchemaValidationResult(
                valid=False, values=None, error="output_format must be 'text' or 'json'"
            )
        output_format = candidate

    if "command_timeout_seconds" in raw:
        timeout_candidate = raw["command_timeout_seconds"]
        if not _is_numeric_non_bool(timeout_candidate):
            return SchemaValidationResult(
                valid=False,
                values=None,
                error="command_timeout_seconds must be numeric, not boolean",
            )
        if not is_valid_command_timeout_seconds(timeout_candidate):
            return SchemaValidationResult(
                valid=False,
                values=None,
                error=(
                    "command_timeout_seconds must be greater than "
                    f"{MIN_COMMAND_TIMEOUT_SECONDS} and at most {MAX_COMMAND_TIMEOUT_SECONDS}"
                ),
            )
        command_timeout_seconds = float(timeout_candidate)

    if "max_output_bytes" in raw:
        bytes_candidate = raw["max_output_bytes"]
        if not _is_int_non_bool(bytes_candidate):
            return SchemaValidationResult(
                valid=False, values=None, error="max_output_bytes must be an integer, not boolean"
            )
        if not (MIN_MAX_OUTPUT_BYTES <= bytes_candidate <= MAX_MAX_OUTPUT_BYTES):
            return SchemaValidationResult(
                valid=False,
                values=None,
                error=(
                    f"max_output_bytes must be between {MIN_MAX_OUTPUT_BYTES} "
                    f"and {MAX_MAX_OUTPUT_BYTES}"
                ),
            )
        max_output_bytes = bytes_candidate

    return SchemaValidationResult(
        valid=True,
        values=ValidatedConfigValues(
            output_format=output_format,
            command_timeout_seconds=command_timeout_seconds,
            max_output_bytes=max_output_bytes,
        ),
        error=None,
    )


def check_config_file(path: Path) -> tuple[ConfigFileStatus, str | None]:
    """Return the file-only status (missing/invalid/valid) used by ``config validate``."""
    parse_result = parse_toml_file(path)
    if parse_result.status is not ConfigFileStatus.VALID:
        return parse_result.status, parse_result.error
    assert parse_result.raw is not None
    schema_result = validate_config_schema(parse_result.raw)
    if not schema_result.valid:
        return ConfigFileStatus.INVALID, schema_result.error
    return ConfigFileStatus.VALID, None


def _parse_env_output_format(raw_value: str) -> str | None:
    if raw_value in {fmt.value for fmt in OutputFormat}:
        return raw_value
    return None


def _parse_env_command_timeout_seconds(raw_value: str) -> float | None:
    try:
        parsed = float(raw_value)
    except ValueError:
        return None
    if not is_valid_command_timeout_seconds(parsed):
        return None
    return parsed


def _parse_env_max_output_bytes(raw_value: str) -> int | None:
    try:
        parsed = int(raw_value)
    except ValueError:
        return None
    if not (MIN_MAX_OUTPUT_BYTES <= parsed <= MAX_MAX_OUTPUT_BYTES):
        return None
    return parsed


def resolve_effective_config(
    *,
    cli_output_format: str | None = None,
    cli_command_timeout_seconds: float | None = None,
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ConfigResolution:
    """Resolve effective configuration: CLI > environment > file > default."""
    active_env = env if env is not None else os.environ
    path = config_path if config_path is not None else resolve_config_path(env=active_env)

    parse_result = parse_toml_file(path)
    file_status = parse_result.status
    file_values = ValidatedConfigValues(
        output_format=None, command_timeout_seconds=None, max_output_bytes=None
    )

    if parse_result.status is ConfigFileStatus.INVALID:
        return ConfigResolution(
            file_status=ConfigFileStatus.INVALID,
            path=str(path),
            config=None,
            sources=None,
            error=parse_result.error,
        )
    if parse_result.status is ConfigFileStatus.VALID:
        assert parse_result.raw is not None
        schema_result = validate_config_schema(parse_result.raw)
        if not schema_result.valid:
            return ConfigResolution(
                file_status=ConfigFileStatus.INVALID,
                path=str(path),
                config=None,
                sources=None,
                error=schema_result.error,
            )
        assert schema_result.values is not None
        file_values = schema_result.values

    if cli_output_format is not None:
        output_format = OutputFormat(cli_output_format)
        output_format_source = ConfigSource.CLI
    elif "MAOPS_PY_OUTPUT_FORMAT" in active_env:
        raw_env_value = active_env["MAOPS_PY_OUTPUT_FORMAT"]
        parsed_format = _parse_env_output_format(raw_env_value)
        if parsed_format is None:
            return ConfigResolution(
                file_status=file_status,
                path=str(path),
                config=None,
                sources=None,
                error=f"invalid MAOPS_PY_OUTPUT_FORMAT value: {raw_env_value!r}",
            )
        output_format = OutputFormat(parsed_format)
        output_format_source = ConfigSource.ENVIRONMENT
    elif file_values.output_format is not None:
        output_format = OutputFormat(file_values.output_format)
        output_format_source = ConfigSource.FILE
    else:
        output_format = DEFAULT_OUTPUT_FORMAT
        output_format_source = ConfigSource.DEFAULT

    if cli_command_timeout_seconds is not None:
        command_timeout_seconds = cli_command_timeout_seconds
        command_timeout_source = ConfigSource.CLI
    elif "MAOPS_PY_COMMAND_TIMEOUT_SECONDS" in active_env:
        raw_env_value = active_env["MAOPS_PY_COMMAND_TIMEOUT_SECONDS"]
        parsed_timeout = _parse_env_command_timeout_seconds(raw_env_value)
        if parsed_timeout is None:
            return ConfigResolution(
                file_status=file_status,
                path=str(path),
                config=None,
                sources=None,
                error=f"invalid MAOPS_PY_COMMAND_TIMEOUT_SECONDS value: {raw_env_value!r}",
            )
        command_timeout_seconds = parsed_timeout
        command_timeout_source = ConfigSource.ENVIRONMENT
    elif file_values.command_timeout_seconds is not None:
        command_timeout_seconds = file_values.command_timeout_seconds
        command_timeout_source = ConfigSource.FILE
    else:
        command_timeout_seconds = DEFAULT_COMMAND_TIMEOUT_SECONDS
        command_timeout_source = ConfigSource.DEFAULT

    if "MAOPS_PY_MAX_OUTPUT_BYTES" in active_env:
        raw_env_value = active_env["MAOPS_PY_MAX_OUTPUT_BYTES"]
        parsed_bytes = _parse_env_max_output_bytes(raw_env_value)
        if parsed_bytes is None:
            return ConfigResolution(
                file_status=file_status,
                path=str(path),
                config=None,
                sources=None,
                error=f"invalid MAOPS_PY_MAX_OUTPUT_BYTES value: {raw_env_value!r}",
            )
        max_output_bytes = parsed_bytes
        max_output_bytes_source = ConfigSource.ENVIRONMENT
    elif file_values.max_output_bytes is not None:
        max_output_bytes = file_values.max_output_bytes
        max_output_bytes_source = ConfigSource.FILE
    else:
        max_output_bytes = DEFAULT_MAX_OUTPUT_BYTES
        max_output_bytes_source = ConfigSource.DEFAULT

    return ConfigResolution(
        file_status=file_status,
        path=str(path),
        config=EffectiveConfig(
            output_format=output_format,
            command_timeout_seconds=command_timeout_seconds,
            max_output_bytes=max_output_bytes,
        ),
        sources=EffectiveConfigSources(
            output_format=output_format_source,
            command_timeout_seconds=command_timeout_source,
            max_output_bytes=max_output_bytes_source,
        ),
        error=None,
    )


def init_config_file(path: Path, *, force: bool) -> ConfigInitResult:
    """Atomically create a documented configuration template at ``path``."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    try:
        target_stat = os.lstat(path)
    except FileNotFoundError:
        target_stat = None

    if target_stat is not None:
        if stat.S_ISLNK(target_stat.st_mode):
            return ConfigInitResult(
                status=ConfigInitStatus.REFUSED_SYMLINK,
                path=str(path),
                detail="refusing to replace a symbolic link target, even with --force",
            )
        if not stat.S_ISREG(target_stat.st_mode):
            return ConfigInitResult(
                status=ConfigInitStatus.REFUSED_NOT_REGULAR,
                path=str(path),
                detail="target exists and is not a regular file",
            )
        if not force:
            return ConfigInitResult(
                status=ConfigInitStatus.REFUSED_EXISTS,
                path=str(path),
                detail="configuration file already exists; use --force to replace it",
            )

    fd: int | None = None
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), prefix=".maops-py-config.", suffix=".tmp")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(TEMPLATE)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    except OSError as exc:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
        return ConfigInitResult(
            status=ConfigInitStatus.FAILED,
            path=str(path),
            detail=f"failed to write configuration file: {exc}",
        )

    return ConfigInitResult(
        status=ConfigInitStatus.CREATED,
        path=str(path),
        detail=f"created configuration file at {path}",
    )
