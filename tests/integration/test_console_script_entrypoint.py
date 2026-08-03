"""The installed maops-py console script invokes the same CLI as python -m."""

import shutil
import subprocess

import pytest

from maops_pydevops.version import get_version

_CONSOLE_SCRIPT = shutil.which("maops-py")


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_version() -> None:
    result = subprocess.run(["maops-py", "--version"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.strip() == get_version()


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_doctor_text() -> None:
    result = subprocess.run(["maops-py", "doctor"], capture_output=True, text=True, check=False)
    assert result.returncode in (0, 1)
    assert "Doctor Report" in result.stdout
