"""CLI-facing configuration orchestration used by ``maops-py config ...``."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from maops_pydevops.core.config import (
    check_config_file,
    init_config_file,
    resolve_config_path,
    resolve_effective_config,
)
from maops_pydevops.core.config_models import ConfigFileStatus, ConfigInitResult, ConfigShowReport


def get_config_path(*, env: Mapping[str, str] | None = None) -> Path:
    """Resolve the configuration file path without creating or reading it."""
    return resolve_config_path(env=env)


def validate_config(
    path: Path | None = None, *, env: Mapping[str, str] | None = None
) -> tuple[ConfigFileStatus, str | None, Path]:
    """Validate a configuration file, resolving the default path if none is given."""
    resolved_path = path if path is not None else resolve_config_path(env=env)
    status, error = check_config_file(resolved_path)
    return status, error, resolved_path


def init_config(path: Path, *, force: bool) -> ConfigInitResult:
    """Create a documented configuration template at ``path``."""
    return init_config_file(path, force=force)


def build_show_report(
    *,
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[ConfigShowReport | None, str | None]:
    """Build the effective-configuration report, or return an error message.

    Returns ``(None, error)`` whenever resolution fails -- an invalid file
    *or* an invalid ``MAOPS_PY_*`` environment variable -- so the caller can
    fail operationally rather than print a misleading report. ``config show``
    has no flag that sets ``output_format`` itself (its own ``--format`` is a
    pure rendering directive), so this never takes a CLI override.
    """
    path = config_path if config_path is not None else resolve_config_path(env=env)
    resolution = resolve_effective_config(config_path=path, env=env)
    if resolution.config is None or resolution.sources is None:
        return None, resolution.error

    report = ConfigShowReport(
        path=str(path),
        exists=resolution.file_status is not ConfigFileStatus.MISSING,
        valid=resolution.file_status is ConfigFileStatus.VALID,
        values=resolution.config,
        sources=resolution.sources,
    )
    return report, None
