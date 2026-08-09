"""Shared pytest fixtures for ``tests/unit`` and ``tests/integration``.

``_isolated_config_env`` is autouse: every test in this suite that touches
configuration resolution (directly, or indirectly via any CLI invocation)
wants ``HOME``/``XDG_CONFIG_HOME``/``MAOPS_PY_CONFIG_FILE``/
``MAOPS_PY_OUTPUT_FORMAT`` isolated from the real invoking user's
environment -- no test in the suite exercises "config env NOT isolated" as
its point. Previously duplicated verbatim in ``test_cli_logs_parse.py`` and
``test_cli_logs_analyze.py`` (Day 4 finding J3); centralized here.

``http_loopback_server``/``tcp_loopback_listener`` are opt-in (not
autouse) fixtures for ``tests/integration/`` health-check tests: real,
``127.0.0.1``-bound, ephemeral-port servers -- no public network, no mocks.
"""

from __future__ import annotations

import http.server
import socket
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)
    monkeypatch.delenv("MAOPS_PY_OUTPUT_FORMAT", raising=False)


@pytest.fixture
def http_loopback_server() -> Iterator[Callable[[type[http.server.BaseHTTPRequestHandler]], str]]:
    """Start a real ``ThreadingHTTPServer`` bound to ``127.0.0.1:0``.

    Returns a starter callable: pass a handler class, get back the
    server's base URL. Binding happens synchronously in the constructor,
    so the port is live before this returns -- no poll/sleep needed.
    Every started server is shut down and closed on fixture teardown.
    """
    servers: list[http.server.ThreadingHTTPServer] = []

    def _start(handler_cls: type[http.server.BaseHTTPRequestHandler]) -> str:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        servers.append(httpd)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address[:2]
        return f"http://{host}:{port}"

    yield _start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def tcp_loopback_listener() -> Iterator[Callable[..., tuple[str, int]]]:
    """Reserve a ``127.0.0.1`` ephemeral port and (optionally, after a
    delay) start listening on it -- for simulating both an immediately
    reachable TCP target and a "refused, then recovers" retry scenario.
    """
    sockets: list[socket.socket] = []

    def _reserve_port() -> int:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        return port

    def _start(*, delay_seconds: float = 0.0, never_listen: bool = False) -> tuple[str, int]:
        port = _reserve_port()
        if never_listen:
            return "127.0.0.1", port

        def _listen() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.listen(5)
            sockets.append(sock)

        if delay_seconds > 0:

            def _delayed_listen() -> None:
                time.sleep(delay_seconds)
                _listen()

            threading.Thread(target=_delayed_listen, daemon=True).start()
        else:
            _listen()

        return "127.0.0.1", port

    yield _start
    for sock in sockets:
        sock.close()
