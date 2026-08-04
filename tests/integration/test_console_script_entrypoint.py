"""The installed maops-py console script invokes the same CLI as python -m."""

import json
import shutil
import subprocess
from pathlib import Path

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


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_config_path(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"HOME": str(tmp_path), "PATH": script_dir}
    result = subprocess.run(
        ["maops-py", "config", "path"], capture_output=True, text=True, check=False, env=env
    )
    assert result.returncode == 0
    assert result.stdout.strip() == str(tmp_path / ".config" / "maops-py" / "config.toml")


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_tools_inspect_json(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    result = subprocess.run(
        ["maops-py", "tools", "inspect", "git", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "warn"
