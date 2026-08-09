#!/usr/bin/env python3
"""Loopback-only smoke check for ``maops-py health http``/``health tcp``.

Starts a real ``http.server.ThreadingHTTPServer`` and a real raw TCP
listener, both bound to ``127.0.0.1`` on ephemeral ports, then drives the
*installed wheel's* ``maops-py`` executable against them and asserts each
report's ``overall`` is ``pass`` or ``warn`` and its JSON output is valid.
Both servers are daemon-threaded, so nothing needs an explicit background
job to track or kill: this single Python process owns the full lifecycle
and exits cleanly. No public network is ever touched.

Usage: health_smoke_check.py <maops-py-executable>
"""

from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
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
    # The caller must hold a reference to the returned socket for as long
    # as the listener needs to stay up -- an unreferenced listening
    # socket is garbage-collected (and its fd closed) shortly after this
    # function returns, which would silently turn every later connection
    # attempt into "connection refused".
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    host, port = sock.getsockname()
    return sock, f"{host}:{port}"


def _run_and_check(exe: str, *args: str) -> None:
    result = subprocess.run([exe, *args], capture_output=True, text=True, check=False, timeout=30)
    if result.returncode not in (0, 1):
        raise SystemExit(f"unexpected exit code {result.returncode} for {args}: {result.stderr}")
    data = json.loads(result.stdout)
    if data["overall"] not in ("pass", "warn"):
        raise SystemExit(f"unexpected overall {data['overall']!r} for {args}: {result.stdout}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: health_smoke_check.py <maops-py-executable>", file=sys.stderr)
        return 2

    exe = argv[1]
    http_url = _start_http_server()
    tcp_listener, tcp_target = _start_tcp_listener()
    try:
        _run_and_check(exe, "health", "http", http_url, "--format", "json")
        _run_and_check(exe, "health", "tcp", tcp_target, "--format", "json")
    finally:
        tcp_listener.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
