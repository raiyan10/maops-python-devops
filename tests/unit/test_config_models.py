"""Config-domain enums and dataclasses serialize with literal, hand-written to_dict()."""

import json

from maops_pydevops.core.config_models import (
    ConfigFileStatus,
    ConfigShowReport,
    ConfigSource,
    EffectiveConfig,
    EffectiveConfigSources,
)
from maops_pydevops.core.models import OutputFormat


def test_config_source_values() -> None:
    assert ConfigSource.CLI.value == "cli"
    assert ConfigSource.ENVIRONMENT.value == "environment"
    assert ConfigSource.FILE.value == "file"
    assert ConfigSource.DEFAULT.value == "default"


def test_config_file_status_values() -> None:
    assert ConfigFileStatus.MISSING.value == "missing"
    assert ConfigFileStatus.INVALID.value == "invalid"
    assert ConfigFileStatus.VALID.value == "valid"


def test_effective_config_to_dict() -> None:
    config = EffectiveConfig(
        output_format=OutputFormat.JSON, command_timeout_seconds=10.0, max_output_bytes=65536
    )
    assert config.to_dict() == {
        "output_format": "json",
        "command_timeout_seconds": 10.0,
        "max_output_bytes": 65536,
    }


def test_effective_config_sources_to_dict() -> None:
    sources = EffectiveConfigSources(
        output_format=ConfigSource.CLI,
        command_timeout_seconds=ConfigSource.ENVIRONMENT,
        max_output_bytes=ConfigSource.DEFAULT,
    )
    assert sources.to_dict() == {
        "output_format": "cli",
        "command_timeout_seconds": "environment",
        "max_output_bytes": "default",
    }


def test_config_show_report_to_dict_and_json() -> None:
    report = ConfigShowReport(
        path="/tmp/config.toml",
        exists=True,
        valid=True,
        values=EffectiveConfig(
            output_format=OutputFormat.TEXT, command_timeout_seconds=10.0, max_output_bytes=65536
        ),
        sources=EffectiveConfigSources(
            output_format=ConfigSource.DEFAULT,
            command_timeout_seconds=ConfigSource.DEFAULT,
            max_output_bytes=ConfigSource.DEFAULT,
        ),
    )
    data = report.to_dict()
    assert data["path"] == "/tmp/config.toml"
    assert data["exists"] is True
    assert data["valid"] is True
    assert data["values"] == {
        "output_format": "text",
        "command_timeout_seconds": 10.0,
        "max_output_bytes": 65536,
    }
    assert data["sources"] == {
        "output_format": "default",
        "command_timeout_seconds": "default",
        "max_output_bytes": "default",
    }
    assert json.loads(report.to_json()) == data


def test_dataclasses_are_frozen() -> None:
    config = EffectiveConfig(
        output_format=OutputFormat.TEXT, command_timeout_seconds=10.0, max_output_bytes=65536
    )
    try:
        config.max_output_bytes = 1  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised
