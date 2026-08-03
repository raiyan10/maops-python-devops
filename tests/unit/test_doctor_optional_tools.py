"""Optional tool checks use shutil.which and never fail overall when absent."""

import shutil

import pytest

from maops_pydevops.commands.doctor import build_report
from maops_pydevops.core.models import CheckStatus


def test_optional_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda binary: f"/usr/bin/{binary}")
    report = build_report()
    optional = [check for check in report.checks if not check.required]
    assert optional
    assert all(check.status is CheckStatus.PASS for check in optional)


def test_optional_tools_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda binary: None)
    report = build_report()
    optional = [check for check in report.checks if not check.required]
    assert optional
    assert all(check.status is CheckStatus.WARN for check in optional)


def test_optional_tools_absent_do_not_fail_overall(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda binary: None)
    report = build_report()
    assert report.overall is CheckStatus.PASS
