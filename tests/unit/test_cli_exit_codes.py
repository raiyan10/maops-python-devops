"""Exit code convention: 0 success, 1 operational failure, 2 usage error."""

from __future__ import annotations

import pytest

import maops_pydevops.cli as cli_module
from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from maops_pydevops.core.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
    PlatformInfo,
    PythonInfo,
)


def _make_report(overall: CheckStatus) -> DoctorReport:
    python_info = PythonInfo(version="3.11.9", executable="/usr/bin/python3", supported=True)
    platform_info = PlatformInfo(
        system="Linux", release="6.0", architecture="x86_64", filesystem_encoding="utf-8"
    )
    checks = (
        DoctorCheck(name="python_version", status=CheckStatus.PASS, required=True, detail="ok"),
    )
    return DoctorReport(
        version="0.1.0",
        python=python_info,
        platform=platform_info,
        checks=checks,
        overall=overall,
    )


def test_doctor_exit_zero_when_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "build_report", lambda: _make_report(CheckStatus.PASS))
    assert main(["doctor"]) == EXIT_SUCCESS


def test_doctor_exit_one_when_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "build_report", lambda: _make_report(CheckStatus.FAIL))
    assert main(["doctor"]) == EXIT_FAILURE


def test_version_exit_zero() -> None:
    assert main(["version"]) == EXIT_SUCCESS


def test_unknown_command_exit_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["nope"])
    assert exc_info.value.code == EXIT_USAGE_ERROR
