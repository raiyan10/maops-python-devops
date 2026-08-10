#!/usr/bin/env python3
"""Loopback-only smoke check for ``maops-py workflow validate``/``workflow run``.

Starts a real ``http.server.ThreadingHTTPServer`` and a real raw TCP
listener, both bound to ``127.0.0.1`` on ephemeral ports (mirroring
``health_smoke_check.py``), writes a workflow TOML file exercising every
supported step kind (using the caller-supplied filesystem/log fixtures
for the filesystem/log steps), then drives the *installed wheel's*
``maops-py`` executable through ``workflow validate`` and ``workflow
run`` against it. Asserts: validation reports valid, the run's ``overall``
is ``pass``/``warn``, its JSON output parses, and its Markdown output is
generated. No public network is ever touched.

Usage: workflow_smoke_check.py <maops-py-executable> <fixture-tree-dir> <log-fixture-path>
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def _start_http_server() -> str:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _host, port = httpd.server_address[:2]
    return f"http://127.0.0.1:{port}/health"


def _start_tcp_listener() -> tuple[socket.socket, str]:
    # See health_smoke_check.py's identical comment: the caller must hold
    # a reference to the returned socket for as long as the listener needs
    # to stay up.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    host, port = sock.getsockname()
    return sock, f"{host}:{port}"


def _workflow_toml(*, fixture_tree: str, log_fixture: str, http_url: str, tcp_target: str) -> str:
    return f"""\
schema_version = 1
name = "smoke workflow"

[[steps]]
id = "doc"
kind = "doctor"

[[steps]]
id = "sysinv"
kind = "inventory_system"

[[steps]]
id = "fsinv"
kind = "inventory_filesystem"
path = {fixture_tree!r}
max_depth = 2
top = 3

[[steps]]
id = "loganalyze"
kind = "logs_analyze"
path = {log_fixture!r}

[[steps]]
id = "http"
kind = "health_http"
urls = [{http_url!r}]

[[steps]]
id = "tcp"
kind = "health_tcp"
targets = [{tcp_target!r}]
"""


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "usage: workflow_smoke_check.py <maops-py-executable> "
            "<fixture-tree-dir> <log-fixture-path>",
            file=sys.stderr,
        )
        return 2

    exe, fixture_tree, log_fixture = argv[1], argv[2], argv[3]
    http_url = _start_http_server()
    tcp_listener, tcp_target = _start_tcp_listener()
    wf_fd, wf_path = tempfile.mkstemp(suffix=".toml")
    try:
        with os.fdopen(wf_fd, "w", encoding="utf-8") as handle:
            handle.write(
                _workflow_toml(
                    fixture_tree=fixture_tree,
                    log_fixture=log_fixture,
                    http_url=http_url,
                    tcp_target=tcp_target,
                )
            )

        validate_result = subprocess.run(
            [exe, "workflow", "validate", wf_path, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if validate_result.returncode != 0:
            raise SystemExit(f"workflow validate failed: {validate_result.stderr}")
        validate_data = json.loads(validate_result.stdout)
        if validate_data["status"] != "valid":
            raise SystemExit(f"workflow validate reported invalid: {validate_result.stdout}")

        run_result = subprocess.run(
            [exe, "workflow", "run", wf_path, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if run_result.returncode not in (0, 1):
            raise SystemExit(f"unexpected exit code {run_result.returncode}: {run_result.stderr}")
        run_data = json.loads(run_result.stdout)
        if run_data["overall"] not in ("pass", "warn"):
            raise SystemExit(f"unexpected overall {run_data['overall']!r}: {run_result.stdout}")

        markdown_result = subprocess.run(
            [exe, "workflow", "run", wf_path, "--format", "markdown"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if markdown_result.returncode not in (0, 1):
            raise SystemExit(f"workflow run (markdown) failed: {markdown_result.stderr}")
        if not markdown_result.stdout.startswith("# MAOps Workflow Run:"):
            raise SystemExit("markdown output missing expected heading")
    finally:
        os.unlink(wf_path)
        tcp_listener.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
