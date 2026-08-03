"""python -m maops_pydevops invokes the same CLI as the console script."""

import json
import subprocess
import sys

from maops_pydevops.version import get_version


def test_python_m_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == get_version()


def test_python_m_doctor_json() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "doctor", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1)
    json.loads(result.stdout)


def test_python_m_unknown_command_exits_two() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "bogus"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
