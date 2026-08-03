"""The doctor command never shells out or executes subprocesses."""

import os
import subprocess

import pytest

from maops_pydevops.commands.doctor import build_report


def test_build_report_never_calls_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess invoked")

    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(os, "system", _fail)
    monkeypatch.setattr(os, "popen", _fail)

    build_report()


def test_doctor_module_does_not_import_subprocess() -> None:
    import maops_pydevops.commands.doctor as doctor_module

    assert "subprocess" not in vars(doctor_module)
