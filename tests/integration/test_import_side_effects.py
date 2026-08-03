"""Importing the package produces no stdout/stderr output."""

import subprocess
import sys


def test_import_produces_no_output() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import maops_pydevops"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
