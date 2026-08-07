"""End-to-end ``logs`` commands via real subprocesses: console script and
``python -m`` parity, JSON validity through ``json.tool``, secret absence.
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


def _write_fixture_log(tmp_path: Path) -> Path:
    path = tmp_path / "sample.log"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-08-06T04:00:00Z",
                        "severity": "error",
                        "hostname": "app01",
                        "source": "api",
                        "message": "database connection failed to 10.0.0.5",
                    }
                ),
                "<11>2026-08-06T04:00:05Z app01 myapp[123]: "
                "password=hunter2secretvalue login failed",
                "not any recognized log format at all",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_python_m_logs_parse_json(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "parse",
            str(log_path),
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
    assert data["overall"] in ("pass", "warn", "fail")
    assert "hunter2secretvalue" not in result.stdout


def test_python_m_logs_analyze_json(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "analyze",
            str(log_path),
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
    assert data["overall"] in ("pass", "warn", "fail")
    assert "hunter2secretvalue" not in result.stdout


def test_logs_parse_json_validates_via_json_tool(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    parse_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "parse",
            str(log_path),
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
        input=parse_result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0


def test_logs_analyze_json_validates_via_json_tool(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    analyze_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "analyze",
            str(log_path),
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
        input=analyze_result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0


def test_python_m_root_help_lists_logs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "logs" in result.stdout


def test_no_redact_only_against_synthetic_fixture(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "parse",
            str(log_path),
            "--no-redact",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    assert result.returncode == 0
    assert "hunter2secretvalue" in result.stdout


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_logs_parse_json(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    log_path = _write_fixture_log(tmp_path)
    result = subprocess.run(
        ["maops-py", "logs", "parse", str(log_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] in ("pass", "warn", "fail")


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_logs_analyze_json(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    log_path = _write_fixture_log(tmp_path)
    result = subprocess.run(
        ["maops-py", "logs", "analyze", str(log_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] in ("pass", "warn", "fail")


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_logs_parse_nonexistent_path_exits_one(tmp_path: Path) -> None:
    assert _CONSOLE_SCRIPT is not None
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    missing = str(tmp_path / "nope.log")
    result = subprocess.run(
        ["maops-py", "logs", "parse", missing],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 1


def test_console_module_parity_parse(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    module_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "parse",
            str(log_path),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    if _CONSOLE_SCRIPT is None:
        pytest.skip("maops-py console script not installed")
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    console_result = subprocess.run(
        ["maops-py", "logs", "parse", str(log_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert module_result.stdout == console_result.stdout
    assert module_result.returncode == console_result.returncode


def test_console_module_parity_analyze(tmp_path: Path) -> None:
    log_path = _write_fixture_log(tmp_path)
    module_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "logs",
            "analyze",
            str(log_path),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    if _CONSOLE_SCRIPT is None:
        pytest.skip("maops-py console script not installed")
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    console_result = subprocess.run(
        ["maops-py", "logs", "analyze", str(log_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert module_result.stdout == console_result.stdout
    assert module_result.returncode == console_result.returncode
