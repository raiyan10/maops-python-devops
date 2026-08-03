"""A failing required check drives overall status to fail."""

import pytest

import maops_pydevops.commands.doctor as doctor_module
from maops_pydevops.commands.doctor import build_report
from maops_pydevops.core.models import CheckStatus, DoctorCheck


def _check(report_checks: tuple[DoctorCheck, ...], name: str) -> DoctorCheck:
    return next(check for check in report_checks if check.name == name)


def test_unsupported_python_causes_required_failure() -> None:
    report = build_report(python_version=(3, 9, 0))
    python_check = _check(report.checks, "python_version")
    assert python_check.status is CheckStatus.FAIL
    assert python_check.required is True
    assert report.overall is CheckStatus.FAIL


def test_unsupported_os_causes_required_failure() -> None:
    report = build_report(os_system="Plan9")
    os_check = _check(report.checks, "os_family")
    assert os_check.status is CheckStatus.FAIL
    assert report.overall is CheckStatus.FAIL


def test_unresolvable_python_executable_causes_required_failure() -> None:
    report = build_report(python_executable="/definitely/not/a/real/interpreter")
    exe_check = _check(report.checks, "python_executable")
    assert exe_check.status is CheckStatus.FAIL
    assert report.overall is CheckStatus.FAIL


def test_unavailable_temp_directory_causes_required_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor_module.tempfile, "gettempdir", lambda: "/nonexistent-maops-temp-dir")
    report = build_report()
    temp_check = _check(report.checks, "temp_directory")
    assert temp_check.status is CheckStatus.FAIL
    assert report.overall is CheckStatus.FAIL


def test_unavailable_filesystem_encoding_causes_required_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor_module.sys, "getfilesystemencoding", lambda: "")
    report = build_report()
    encoding_check = _check(report.checks, "filesystem_encoding")
    assert encoding_check.status is CheckStatus.FAIL
    assert report.overall is CheckStatus.FAIL


def test_package_import_failure_causes_required_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(name: str) -> None:
        raise ImportError(f"cannot import {name}")

    monkeypatch.setattr(doctor_module.importlib, "import_module", _raise)
    report = build_report()
    import_check = _check(report.checks, "package_import")
    assert import_check.status is CheckStatus.FAIL
    assert report.overall is CheckStatus.FAIL
