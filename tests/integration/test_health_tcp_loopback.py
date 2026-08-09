"""``health tcp`` against real loopback TCP listeners -- no public network.

Every listener is a real ``socket.socket`` bound to ``127.0.0.1:0``
(ephemeral port), via the ``tcp_loopback_listener`` fixture in
``tests/conftest.py``. The CLI is invoked as a real subprocess.

Retry recovery (refused-then-succeeds -> WARN) is deliberately *not*
exercised here: coordinating a real subprocess's attempt timing against an
in-process delayed listener is inherently racy against interpreter-startup
jitter, and the behavior is already covered deterministically at the unit
level (``tests/unit/test_health_retry_state_machine.py``) with injected
fakes and no timing dependency at all.
"""

from __future__ import annotations

import json
import shutil
import socket
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


def _run_health_tcp(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "tcp", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )


def test_successful_connection(
    tmp_path: Path, tcp_loopback_listener: Callable[..., tuple[str, int]]
) -> None:
    host, port = tcp_loopback_listener()
    result = _run_health_tcp(tmp_path, f"{host}:{port}", "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["results"][0]["status"] == "pass"
    assert data["results"][0]["peer_ip"] == "127.0.0.1"
    assert data["results"][0]["host"] == host
    assert data["results"][0]["port"] == port


def test_connection_refused_is_fail(
    tmp_path: Path, tcp_loopback_listener: Callable[..., tuple[str, int]]
) -> None:
    # Reserve a port but never start listening on it -- nothing accepts,
    # so the connection is refused immediately.
    host, port = tcp_loopback_listener(never_listen=True)
    result = _run_health_tcp(tmp_path, f"{host}:{port}", "--retries", "0", "--format", "json")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "fail"
    assert data["results"][0]["status"] == "fail"
    assert data["results"][0]["attempts"][0]["failure_reason"] == "connection_refused"
    assert data["results"][0]["peer_ip"] is None


def test_malformed_target_does_not_discard_other_targets_results(
    tmp_path: Path, tcp_loopback_listener: Callable[..., tuple[str, int]]
) -> None:
    # Regression test for day-05-network-review.md's Critical C1: an
    # empty-DNS-label hostname (a stray double dot) used to raise an
    # uncaught UnicodeError from socket.create_connection(), crashing the
    # whole multi-target run and discarding every other target's already-
    # obtained result, not just the malformed one's.
    host, port = tcp_loopback_listener()
    result = _run_health_tcp(
        tmp_path, f"{host}:{port}", "example..com:80", "--retries", "0", "--format", "json"
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "fail"
    assert data["results"][0]["status"] == "pass"
    assert data["results"][1]["status"] == "fail"
    assert data["results"][1]["attempts"][0]["failure_reason"] == "invalid_target_encoding"


def test_ipv6_loopback_target(tmp_path: Path) -> None:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.bind(("::1", 0))
    except OSError:
        sock.close()
        pytest.skip("IPv6 loopback not available on this platform")
        return
    try:
        sock.listen(1)
        port = sock.getsockname()[1]
        result = _run_health_tcp(tmp_path, f"[::1]:{port}", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["overall"] == "pass"
        assert data["results"][0]["host"] == "::1"
    finally:
        sock.close()


@pytest.mark.skipif(_CONSOLE_SCRIPT is None, reason="maops-py console script not installed")
def test_console_module_parity(
    tmp_path: Path, tcp_loopback_listener: Callable[..., tuple[str, int]]
) -> None:
    assert _CONSOLE_SCRIPT is not None
    host, port = tcp_loopback_listener()
    module_result = _run_health_tcp(tmp_path, f"{host}:{port}", "--format", "json")

    script_dir = str(Path(_CONSOLE_SCRIPT).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    console_result = subprocess.run(
        ["maops-py", "health", "tcp", f"{host}:{port}", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # duration_ms/total_duration_ms are real wall-clock timings from two
    # separate subprocess invocations -- legitimately non-identical.
    module_data = json.loads(module_result.stdout)
    console_data = json.loads(console_result.stdout)
    for data in (module_data, console_data):
        for result in data["results"]:
            result.pop("total_duration_ms", None)
            for attempt in result["attempts"]:
                attempt.pop("duration_ms", None)
    assert module_data == console_data
    assert module_result.returncode == console_result.returncode
