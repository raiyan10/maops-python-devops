"""The doctor command never shells out or executes subprocesses."""

import os
import subprocess
from pathlib import Path

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


def test_config_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.config as config_module

    assert "subprocess" not in vars(config_module)


def test_commands_config_module_does_not_import_subprocess() -> None:
    import maops_pydevops.commands.config as commands_config_module

    assert "subprocess" not in vars(commands_config_module)


def test_cli_module_does_not_import_subprocess() -> None:
    import maops_pydevops.cli as cli_module

    assert "subprocess" not in vars(cli_module)


def test_core_models_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.models as models_module

    assert "subprocess" not in vars(models_module)


def test_config_models_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.config_models as config_models_module

    assert "subprocess" not in vars(config_models_module)


def test_commands_inventory_module_does_not_import_subprocess() -> None:
    import maops_pydevops.commands.inventory as inventory_module

    assert "subprocess" not in vars(inventory_module)


def test_core_system_inventory_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.system_inventory as system_inventory_module

    assert "subprocess" not in vars(system_inventory_module)


def test_core_filesystem_inventory_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.filesystem_inventory as filesystem_inventory_module

    assert "subprocess" not in vars(filesystem_inventory_module)


def test_core_inventory_models_module_does_not_import_subprocess() -> None:
    import maops_pydevops.core.inventory_models as inventory_models_module

    assert "subprocess" not in vars(inventory_models_module)


def test_build_system_report_never_calls_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    from maops_pydevops.core.system_inventory import build_system_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess invoked")

    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(os, "system", _fail)
    monkeypatch.setattr(os, "popen", _fail)

    build_system_report()


def test_build_filesystem_report_never_calls_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.core.filesystem_inventory import build_filesystem_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess invoked")

    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(os, "system", _fail)
    monkeypatch.setattr(os, "popen", _fail)

    build_filesystem_report(str(tmp_path), max_depth=2, max_entries=100, top=5)
