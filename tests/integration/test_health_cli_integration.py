"""``health`` console-script / ``python -m`` parity and JSON validity."""

from __future__ import annotations

import http.server
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

_CONSOLE_SCRIPT = shutil.which("maops-py")


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(home)}


class _AlwaysOkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def test_python_m_root_help_lists_health() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "health" in result.stdout


def test_python_m_health_http_json(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_AlwaysOkHandler)
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", base_url, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"


def test_health_http_json_validates_via_json_tool(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_AlwaysOkHandler)
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", base_url, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    tool_check = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_script_health_http_json(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    assert _CONSOLE_SCRIPT is not None
    base_url = http_loopback_server(_AlwaysOkHandler)
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    result = subprocess.run(
        ["maops-py", "health", "http", base_url, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"


def _strip_timing_fields(data: dict[str, object]) -> dict[str, object]:
    # duration_ms/total_duration_ms reflect real wall-clock timing from
    # two separate subprocess invocations against a real loopback
    # server -- legitimately non-identical between runs. Every other
    # field must still match exactly for console/module parity.
    stripped = json.loads(json.dumps(data))
    for result in stripped["results"]:
        result.pop("total_duration_ms", None)
        for attempt in result.get("attempts", []):
            attempt.pop("duration_ms", None)
    return dict(stripped)


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_module_parity_health_http(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    assert _CONSOLE_SCRIPT is not None
    base_url = http_loopback_server(_AlwaysOkHandler)
    module_result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", base_url, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    console_result = subprocess.run(
        ["maops-py", "health", "http", base_url, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert module_result.returncode == console_result.returncode
    assert _strip_timing_fields(json.loads(module_result.stdout)) == _strip_timing_fields(
        json.loads(console_result.stdout)
    )


def test_health_http_help_via_python_m() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--expect-status" in result.stdout


def test_health_tcp_help_via_python_m() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "tcp", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--timeout" in result.stdout


def test_invalid_target_exits_two_via_python_m(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", "ftp://example.com/"],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )
    assert result.returncode == 2
