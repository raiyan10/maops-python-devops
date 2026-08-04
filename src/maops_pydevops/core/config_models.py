"""Typed data models for configuration values, sources, and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from maops_pydevops.core.models import OutputFormat

DEFAULT_OUTPUT_FORMAT = OutputFormat.TEXT
DEFAULT_COMMAND_TIMEOUT_SECONDS: float = 10.0
MIN_COMMAND_TIMEOUT_SECONDS: float = 0.0
MAX_COMMAND_TIMEOUT_SECONDS: float = 300.0
DEFAULT_MAX_OUTPUT_BYTES: int = 65536
MIN_MAX_OUTPUT_BYTES: int = 1024
MAX_MAX_OUTPUT_BYTES: int = 1048576

KNOWN_CONFIG_KEYS: frozenset[str] = frozenset(
    {"output_format", "command_timeout_seconds", "max_output_bytes"}
)


def is_valid_command_timeout_seconds(value: float) -> bool:
    """The single range check for ``command_timeout_seconds``, shared by every caller."""
    return MIN_COMMAND_TIMEOUT_SECONDS < value <= MAX_COMMAND_TIMEOUT_SECONDS


class ConfigSource(StrEnum):
    """Where an effective configuration value came from."""

    CLI = "cli"
    ENVIRONMENT = "environment"
    FILE = "file"
    DEFAULT = "default"


class ConfigFileStatus(StrEnum):
    """Result of attempting to locate and parse the configuration file."""

    MISSING = "missing"
    INVALID = "invalid"
    VALID = "valid"


@dataclass(frozen=True)
class EffectiveConfig:
    """The fully resolved configuration values in effect for this invocation."""

    output_format: OutputFormat
    command_timeout_seconds: float
    max_output_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "output_format": self.output_format.value,
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
        }


@dataclass(frozen=True)
class EffectiveConfigSources:
    """The source that produced each effective configuration value."""

    output_format: ConfigSource
    command_timeout_seconds: ConfigSource
    max_output_bytes: ConfigSource

    def to_dict(self) -> dict[str, object]:
        return {
            "output_format": self.output_format.value,
            "command_timeout_seconds": self.command_timeout_seconds.value,
            "max_output_bytes": self.max_output_bytes.value,
        }


@dataclass(frozen=True)
class TomlParseResult:
    """The outcome of locating and parsing the configuration file as TOML."""

    status: ConfigFileStatus
    raw: dict[str, object] | None
    error: str | None


@dataclass(frozen=True)
class ValidatedConfigValues:
    """The subset of configuration keys present in a file, already type/range checked.

    Each field is ``None`` when the corresponding key was absent from the
    file -- never used to mean "invalid," since an invalid file never
    produces a :class:`ValidatedConfigValues` at all.
    """

    output_format: str | None
    command_timeout_seconds: float | None
    max_output_bytes: int | None


@dataclass(frozen=True)
class SchemaValidationResult:
    """The outcome of validating a parsed TOML document against the schema."""

    valid: bool
    values: ValidatedConfigValues | None
    error: str | None


@dataclass(frozen=True)
class ConfigResolution:
    """The outcome of resolving effective configuration from all sources.

    ``file_status`` describes only the configuration *file* itself
    (missing/invalid/valid). ``config``/``sources`` are ``None`` whenever
    resolution failed for any reason -- an invalid file *or* an invalid
    ``MAOPS_PY_*`` environment variable -- with ``error`` set to a
    human-readable explanation in that case.
    """

    file_status: ConfigFileStatus
    path: str
    config: EffectiveConfig | None
    sources: EffectiveConfigSources | None
    error: str | None


class ConfigInitStatus(StrEnum):
    """Result of attempting to create a new configuration file."""

    CREATED = "created"
    REFUSED_EXISTS = "refused_exists"
    REFUSED_SYMLINK = "refused_symlink"
    REFUSED_NOT_REGULAR = "refused_not_regular"
    FAILED = "failed"


@dataclass(frozen=True)
class ConfigInitResult:
    """The outcome of ``maops-py config init``."""

    status: ConfigInitStatus
    path: str
    detail: str


@dataclass(frozen=True)
class ConfigShowReport:
    """The full report rendered by ``maops-py config show``."""

    path: str
    exists: bool
    valid: bool
    values: EffectiveConfig
    sources: EffectiveConfigSources

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "valid": self.valid,
            "values": self.values.to_dict(),
            "sources": self.sources.to_dict(),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
