"""``workflow run`` steps of kind ``health_http``/``health_tcp`` against real loopback.

Every server/listener is real and bound to ``127.0.0.1`` only (the shared
``http_loopback_server``/``tcp_loopback_listener`` fixtures from
``tests/conftest.py``) -- no public network is ever touched. The workflow
file itself is written to a temp directory and run as a real
``python -m maops_pydevops`` subprocess, matching this project's
established integration-test convention.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(home)}


def _run_workflow(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "workflow", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def test_workflow_run_health_http_step_loopback(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_OkHandler)
    workflow_path = tmp_path / "wf.toml"
    workflow_path.write_text(
        f"""
schema_version = 1
name = "http workflow"

[[steps]]
id = "check"
kind = "health_http"
urls = ["{base_url}/health"]
""",
        encoding="utf-8",
    )
    result = _run_workflow(tmp_path, "run", str(workflow_path), "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["steps"][0]["kind"] == "health_http"
    assert data["steps"][0]["status"] == "pass"
    values = {m["label"]: m["value"] for m in data["steps"][0]["metrics"]}
    assert values["targets"] == "1"
    assert values["passed"] == "1"


def test_workflow_run_health_tcp_step_loopback(
    tmp_path: Path, tcp_loopback_listener: Callable[..., tuple[str, int]]
) -> None:
    host, port = tcp_loopback_listener()
    workflow_path = tmp_path / "wf.toml"
    workflow_path.write_text(
        f"""
schema_version = 1
name = "tcp workflow"

[[steps]]
id = "check"
kind = "health_tcp"
targets = ["{host}:{port}"]
""",
        encoding="utf-8",
    )
    result = _run_workflow(tmp_path, "run", str(workflow_path), "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["steps"][0]["kind"] == "health_tcp"
    assert data["steps"][0]["status"] == "pass"


def test_workflow_run_health_steps_never_reach_public_network(
    tmp_path: Path,
    http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str],
    tcp_loopback_listener: Callable[..., tuple[str, int]],
) -> None:
    base_url = http_loopback_server(_OkHandler)
    host, port = tcp_loopback_listener()
    workflow_path = tmp_path / "wf.toml"
    workflow_path.write_text(
        f"""
schema_version = 1
name = "combined"

[[steps]]
id = "doc"
kind = "doctor"

[[steps]]
id = "http"
kind = "health_http"
urls = ["{base_url}/health"]

[[steps]]
id = "tcp"
kind = "health_tcp"
targets = ["{host}:{port}"]
""",
        encoding="utf-8",
    )
    result = _run_workflow(tmp_path, "run", str(workflow_path), "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert [step["id"] for step in data["steps"]] == ["doc", "http", "tcp"]
    assert all(step["status"] == "pass" for step in data["steps"])
    # All targets used are 127.0.0.1 -- confirm no other hostname appears
    # anywhere in the report (proving no public-network target leaked in).
    assert "example.com" not in result.stdout
