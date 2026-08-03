"""Both doctor JSON invocation paths validate via python -m json.tool."""

import subprocess
import sys


def test_python_m_json_validates_with_json_tool() -> None:
    doctor = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "doctor", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    validator = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=doctor.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validator.returncode == 0, validator.stderr
