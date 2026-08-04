"""End-to-end ``config`` subcommands via a real subprocess, isolated from the real HOME."""

import json
import subprocess
import sys
from pathlib import Path


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "maops_pydevops", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
    }


def test_config_path_creates_nothing(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    result = _run(["config", "path"], env)
    assert result.returncode == 0
    expected = Path(env["HOME"]) / ".config" / "maops-py" / "config.toml"
    assert result.stdout.strip() == str(expected)
    assert not expected.exists()


def test_config_init_then_validate_then_show(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)

    init_result = _run(["config", "init"], env)
    assert init_result.returncode == 0

    validate_result = _run(["config", "validate"], env)
    assert validate_result.returncode == 0
    assert "valid" in validate_result.stdout

    show_result = _run(["config", "show", "--format", "json"], env)
    assert show_result.returncode == 0
    data = json.loads(show_result.stdout)
    assert data["exists"] is True
    assert data["valid"] is True


def test_config_init_refuses_without_force_then_succeeds_with_force(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    _run(["config", "init"], env)

    refused = _run(["config", "init"], env)
    assert refused.returncode == 1

    forced = _run(["config", "init", "--force"], env)
    assert forced.returncode == 0


def test_config_show_json_is_valid_json_via_json_tool(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    show = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "config", "show", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    tool_check = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=show.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0
