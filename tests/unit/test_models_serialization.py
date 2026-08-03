"""Explicit, typed serialization of core models. No dict-spreading."""

import json

import pytest

from maops_pydevops.core.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
    OutputFormat,
    PlatformInfo,
    PythonInfo,
)


def test_doctor_check_to_dict() -> None:
    check = DoctorCheck(name="git", status=CheckStatus.WARN, required=False, detail="not found")
    assert check.to_dict() == {
        "name": "git",
        "status": "warn",
        "required": False,
        "detail": "not found",
    }


def test_doctor_report_to_dict_and_to_json_agree() -> None:
    python_info = PythonInfo(version="3.11.9", executable="/usr/bin/python3", supported=True)
    platform_info = PlatformInfo(
        system="Linux", release="6.0", architecture="x86_64", filesystem_encoding="utf-8"
    )
    checks = (
        DoctorCheck(name="python_version", status=CheckStatus.PASS, required=True, detail="ok"),
    )
    report = DoctorReport(
        version="0.1.0",
        python=python_info,
        platform=platform_info,
        checks=checks,
        overall=CheckStatus.PASS,
    )

    data = report.to_dict()
    assert data["version"] == "0.1.0"
    assert data["overall"] == "pass"
    assert isinstance(data["checks"], list)
    assert data["checks"][0]["name"] == "python_version"
    assert json.loads(report.to_json()) == data


def test_models_are_frozen() -> None:
    check = DoctorCheck(name="git", status=CheckStatus.PASS, required=False, detail="ok")
    with pytest.raises((AttributeError, TypeError)):
        check.name = "docker"  # type: ignore[misc]


def test_output_format_values() -> None:
    assert OutputFormat.TEXT.value == "text"
    assert OutputFormat.JSON.value == "json"
