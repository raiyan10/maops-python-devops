"""Platform and interpreter inspection, with injectable parameters for testing."""

from __future__ import annotations

import platform
import sys

from maops_pydevops.core.models import PlatformInfo, PythonInfo

MIN_SUPPORTED_PYTHON: tuple[int, int] = (3, 11)
SUPPORTED_OS_FAMILIES: frozenset[str] = frozenset({"Linux", "Darwin", "Windows"})


def is_supported_python(version: tuple[int, int, int] | None = None) -> bool:
    """Return whether the given (or current) Python version is supported."""
    actual = version if version is not None else sys.version_info[:3]
    return actual[:2] >= MIN_SUPPORTED_PYTHON


def is_supported_os(system: str | None = None) -> bool:
    """Return whether the given (or current) OS family is supported."""
    actual = system if system is not None else platform.system()
    return actual in SUPPORTED_OS_FAMILIES


def gather_python_info(
    *,
    version: tuple[int, int, int] | None = None,
    executable: str | None = None,
) -> PythonInfo:
    """Collect interpreter facts, optionally overriding for deterministic testing."""
    actual_version = version if version is not None else sys.version_info[:3]
    version_str = ".".join(str(part) for part in actual_version)
    actual_executable = executable if executable is not None else sys.executable
    return PythonInfo(
        version=version_str,
        executable=actual_executable,
        supported=is_supported_python(actual_version),
    )


def gather_platform_info(*, system: str | None = None) -> PlatformInfo:
    """Collect operating-system facts, optionally overriding the system name for testing."""
    actual_system = system if system is not None else platform.system()
    return PlatformInfo(
        system=actual_system,
        release=platform.release(),
        architecture=platform.machine(),
        filesystem_encoding=sys.getfilesystemencoding(),
    )
