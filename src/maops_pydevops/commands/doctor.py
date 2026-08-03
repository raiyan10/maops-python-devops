"""Read-only environment diagnostics: required and optional checks."""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

from maops_pydevops.core.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
    PlatformInfo,
    PythonInfo,
)
from maops_pydevops.core.platform import (
    MIN_SUPPORTED_PYTHON,
    gather_platform_info,
    gather_python_info,
    is_supported_os,
)
from maops_pydevops.version import get_version

OPTIONAL_TOOLS: tuple[tuple[str, str], ...] = (
    ("git", "git"),
    ("docker", "docker"),
    ("kubectl", "kubectl"),
    ("terraform", "terraform"),
    ("ansible", "ansible"),
)

_MIN_SUPPORTED_PYTHON_STR = ".".join(str(part) for part in MIN_SUPPORTED_PYTHON)


def check_python_version(python_info: PythonInfo) -> DoctorCheck:
    status = CheckStatus.PASS if python_info.supported else CheckStatus.FAIL
    detail = (
        f"Python {python_info.version} detected; minimum supported is {_MIN_SUPPORTED_PYTHON_STR}."
    )
    return DoctorCheck(name="python_version", status=status, required=True, detail=detail)


def check_package_import() -> DoctorCheck:
    try:
        importlib.import_module("maops_pydevops")
    except ImportError as exc:
        detail = f"Package failed to import: {exc}"
        return DoctorCheck(
            name="package_import", status=CheckStatus.FAIL, required=True, detail=detail
        )
    return DoctorCheck(
        name="package_import",
        status=CheckStatus.PASS,
        required=True,
        detail="maops_pydevops imported successfully.",
    )


def check_os_family(platform_info: PlatformInfo) -> DoctorCheck:
    status = CheckStatus.PASS if is_supported_os(platform_info.system) else CheckStatus.FAIL
    detail = f"Operating system family '{platform_info.system}' detected."
    return DoctorCheck(name="os_family", status=status, required=True, detail=detail)


def check_temp_directory() -> DoctorCheck:
    temp_dir = Path(tempfile.gettempdir())
    if temp_dir.is_dir():
        detail = f"Temporary directory available at {temp_dir}."
        return DoctorCheck(
            name="temp_directory", status=CheckStatus.PASS, required=True, detail=detail
        )
    detail = f"Temporary directory {temp_dir} is not available."
    return DoctorCheck(name="temp_directory", status=CheckStatus.FAIL, required=True, detail=detail)


def check_filesystem_encoding() -> DoctorCheck:
    encoding = sys.getfilesystemencoding()
    if encoding:
        detail = f"Filesystem encoding is {encoding}."
        return DoctorCheck(
            name="filesystem_encoding", status=CheckStatus.PASS, required=True, detail=detail
        )
    return DoctorCheck(
        name="filesystem_encoding",
        status=CheckStatus.FAIL,
        required=True,
        detail="Filesystem encoding could not be determined.",
    )


def check_python_executable(python_info: PythonInfo) -> DoctorCheck:
    executable = python_info.executable
    if executable and Path(executable).exists():
        detail = f"Python executable resolved at {executable}."
        return DoctorCheck(
            name="python_executable", status=CheckStatus.PASS, required=True, detail=detail
        )
    detail = f"Python executable path '{executable}' could not be resolved."
    return DoctorCheck(
        name="python_executable", status=CheckStatus.FAIL, required=True, detail=detail
    )


def check_optional_tool(label: str, binary: str) -> DoctorCheck:
    found = shutil.which(binary)
    if found is not None:
        detail = f"{label} found at {found}."
        return DoctorCheck(name=label, status=CheckStatus.PASS, required=False, detail=detail)
    detail = f"{label} not found on PATH."
    return DoctorCheck(name=label, status=CheckStatus.WARN, required=False, detail=detail)


def _compute_overall(checks: tuple[DoctorCheck, ...]) -> CheckStatus:
    if any(check.required and check.status is CheckStatus.FAIL for check in checks):
        return CheckStatus.FAIL
    return CheckStatus.PASS


def build_report(
    *,
    python_version: tuple[int, int, int] | None = None,
    python_executable: str | None = None,
    os_system: str | None = None,
) -> DoctorReport:
    """Assemble a full doctor report in deterministic check order."""
    python_info = gather_python_info(version=python_version, executable=python_executable)
    platform_info = gather_platform_info(system=os_system)

    required_checks: tuple[DoctorCheck, ...] = (
        check_python_version(python_info),
        check_package_import(),
        check_os_family(platform_info),
        check_temp_directory(),
        check_filesystem_encoding(),
        check_python_executable(python_info),
    )
    optional_checks: tuple[DoctorCheck, ...] = tuple(
        check_optional_tool(label, binary) for label, binary in OPTIONAL_TOOLS
    )
    checks = required_checks + optional_checks

    return DoctorReport(
        version=get_version(),
        python=python_info,
        platform=platform_info,
        checks=checks,
        overall=_compute_overall(checks),
    )
