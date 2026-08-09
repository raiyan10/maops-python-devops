"""``health http`` against real loopback HTTP servers -- no public network.

Every server is a real ``http.server.ThreadingHTTPServer`` bound to
``127.0.0.1:0`` (ephemeral port), started via the ``http_loopback_server``
fixture in ``tests/conftest.py``. The CLI is invoked as a real subprocess
(``python -m maops_pydevops``), matching this project's established
integration-test convention.
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


def _run_health_http(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "health", "http", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )


class _AlwaysOkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        pass


class _FlakyThenOkHandler(http.server.BaseHTTPRequestHandler):
    calls = 0

    def do_GET(self) -> None:
        type(self).calls += 1
        if type(self).calls == 1:
            self.send_response(503)
        else:
            self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    calls = 0

    def do_GET(self) -> None:
        type(self).calls += 1
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:1/should-never-be-requested")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def test_first_attempt_200_is_pass(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_AlwaysOkHandler)
    result = _run_health_http(tmp_path, f"{base_url}/health", "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["results"][0]["status"] == "pass"
    assert data["results"][0]["attempts_used"] == 1
    assert data["results"][0]["peer_ip"] == "127.0.0.1"


def test_503_then_200_is_warn_and_exits_zero(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_FlakyThenOkHandler)
    result = _run_health_http(tmp_path, base_url, "--retry-delay", "0.05", "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "warn"
    assert data["results"][0]["status"] == "warn"
    assert data["results"][0]["attempts_used"] == 2
    assert data["results"][0]["attempts"][0]["http_status"] == 503
    assert data["results"][0]["attempts"][1]["http_status"] == 200


def test_redirect_returned_without_being_followed(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_RedirectHandler)
    result = _run_health_http(tmp_path, base_url, "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["results"][0]["final_http_status"] == 302
    # The server only ever received exactly one request per attempt (1,
    # since a 302 is inside the default 200-399 expected range and is
    # therefore a first-attempt success) -- proving no follow-up request
    # was ever issued to the Location target.
    assert _RedirectHandler.calls == 1
    assert data["results"][0]["attempts_used"] == 1
    assert "should-never-be-requested" not in result.stdout


def test_mixed_target_ordering_survives_reversed_completion(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    fast_url = http_loopback_server(_AlwaysOkHandler)

    class _SlowHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            import time as _time

            _time.sleep(0.15)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    slow_url = http_loopback_server(_SlowHandler)
    # Target 1 (slow) is submitted first but completes last; target 2
    # (fast) completes first -- output order must still match CLI order.
    result = _run_health_http(
        tmp_path, f"{slow_url}/a", f"{fast_url}/b", "--workers", "2", "--format", "json"
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    targets = [entry["target"] for entry in data["results"]]
    assert targets == [f"{slow_url}/a", f"{fast_url}/b"]
    indexes = [entry["index"] for entry in data["results"]]
    assert indexes == [1, 2]


def test_query_values_absent_from_output(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    base_url = http_loopback_server(_AlwaysOkHandler)
    result = _run_health_http(
        tmp_path, f"{base_url}/health?token=super-secret-value&region=ap", "--format", "json"
    )
    assert result.returncode == 0
    assert "super-secret-value" not in result.stdout
    data = json.loads(result.stdout)
    assert data["results"][0]["target"] == f"{base_url}/health?token=[REDACTED]&region=[REDACTED]"


def test_no_response_body_in_output(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    class _BodyHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"UNIQUE_BODY_MARKER_SHOULD_NEVER_APPEAR"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    base_url = http_loopback_server(_BodyHandler)
    result = _run_health_http(tmp_path, base_url, "--format", "json")
    assert result.returncode == 0
    assert "UNIQUE_BODY_MARKER_SHOULD_NEVER_APPEAR" not in result.stdout


def test_no_response_header_in_output(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    class _HeaderHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("X-Unique-Marker-Header", "UNIQUE_HEADER_VALUE_MARKER")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    base_url = http_loopback_server(_HeaderHandler)
    result = _run_health_http(tmp_path, base_url, "--format", "json")
    assert result.returncode == 0
    assert "UNIQUE_HEADER_VALUE_MARKER" not in result.stdout


def test_head_method(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    class _HeadCapableHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    base_url = http_loopback_server(_HeadCapableHandler)
    result = _run_health_http(tmp_path, base_url, "--method", "HEAD", "--format", "json")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["options"]["method"] == "HEAD"


def test_malformed_target_does_not_discard_other_targets_results(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    # Regression test for day-05-network-review.md's Critical C1: an
    # empty-DNS-label hostname (a stray double dot) used to raise an
    # uncaught UnicodeError from conn.connect(), crashing the whole
    # multi-target run and discarding every other target's already-
    # obtained result, not just the malformed one's.
    base_url = http_loopback_server(_AlwaysOkHandler)
    result = _run_health_http(
        tmp_path, base_url, "http://example..com/", "--retries", "0", "--format", "json"
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "fail"
    assert data["results"][0]["status"] == "pass"
    assert data["results"][1]["status"] == "fail"
    assert data["results"][1]["attempts"][0]["failure_reason"] == "invalid_target_encoding"


def test_retry_exhaustion_is_fail_and_exits_one(
    tmp_path: Path, http_loopback_server: Callable[[type[http.server.BaseHTTPRequestHandler]], str]
) -> None:
    class _AlwaysServiceUnavailableHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    base_url = http_loopback_server(_AlwaysServiceUnavailableHandler)
    result = _run_health_http(
        tmp_path, base_url, "--retries", "1", "--retry-delay", "0.02", "--format", "json"
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "fail"
    assert data["results"][0]["attempts_used"] == 2
