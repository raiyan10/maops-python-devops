"""End-to-end ``inventory`` commands via real subprocesses: console script
and ``python -m`` parity, JSON validity through ``json.tool``.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_CONSOLE_SCRIPT = shutil.which("maops-py")


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(home)}


def test_python_m_inventory_system_json(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "inventory", "system", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] in ("pass", "warn", "fail")


def test_python_m_inventory_filesystem_json(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "inventory",
            "filesystem",
            str(tmp_path),
            "--max-depth",
            "1",
            "--top",
            "3",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["root"] == str(tmp_path)


def test_inventory_system_json_validates_via_json_tool(tmp_path: Path) -> None:
    inspect_result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "inventory", "system", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    tool_check = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=inspect_result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0


def test_inventory_filesystem_json_validates_via_json_tool(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")
    inspect_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "inventory",
            "filesystem",
            str(tmp_path),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    tool_check = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=inspect_result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0


def test_python_m_root_help_lists_inventory() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "inventory" in result.stdout


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_inventory_system_json(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    result = subprocess.run(
        ["maops-py", "inventory", "system", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] in ("pass", "warn", "fail")


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_inventory_filesystem_json(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")
    result = subprocess.run(
        ["maops-py", "inventory", "filesystem", str(tmp_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["root"] == str(tmp_path)


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_inventory_filesystem_nonexistent_root_exits_one(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    missing = str(tmp_path / "nope")
    result = subprocess.run(
        ["maops-py", "inventory", "filesystem", missing],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 1
