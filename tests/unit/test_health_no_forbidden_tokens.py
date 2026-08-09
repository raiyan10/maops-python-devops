"""The "network-capable" half of the Day 5 network boundary.

``core/health_http.py`` and ``core/health_tcp.py`` are the only modules
permitted to import ``socket``/``ssl``/``http.client``; ``core/health_runner.py``
is the only module permitted to import ``concurrent.futures``. None of the
health modules may import ``subprocess``, ``urllib.request``, a third-party
HTTP library, or use any of the other forbidden primitives listed in the
project's security restrictions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"

_HEALTH_MODULES = (
    "commands/health.py",
    "core/health_models.py",
    "core/health_http.py",
    "core/health_tcp.py",
    "core/health_runner.py",
)

_FORBIDDEN_TOKENS = (
    "subprocess",
    "urllib.request",
    "requests",
    "httpx",
    "aiohttp",
    "os.system(",
    "os.popen(",
    "shell=True",
    "eval(",
    "exec(",
    "pickle",
    "mmap",
)


def _code_only(text: str) -> str:
    return text.split('"""', 2)[-1] if text.count('"""') >= 2 else text


@pytest.mark.parametrize("relative_path", _HEALTH_MODULES)
def test_health_module_contains_no_forbidden_tokens(relative_path: str) -> None:
    text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
    code_only = _code_only(text)
    for token in _FORBIDDEN_TOKENS:
        assert token not in code_only, f"{relative_path} contains forbidden token {token!r}"


def test_health_http_uses_http_client_ssl_socket() -> None:
    text = (SRC_ROOT / "core/health_http.py").read_text(encoding="utf-8")
    assert "import http.client" in text
    assert "import ssl" in text
    assert "import socket" in text


def test_health_tcp_uses_socket() -> None:
    text = (SRC_ROOT / "core/health_tcp.py").read_text(encoding="utf-8")
    assert "import socket" in text


def test_health_runner_uses_concurrent_futures() -> None:
    text = (SRC_ROOT / "core/health_runner.py").read_text(encoding="utf-8")
    assert "import concurrent.futures" in text


def test_only_health_http_and_health_tcp_import_socket_primitives() -> None:
    all_source_files = sorted(SRC_ROOT.rglob("*.py"))
    permitted = {"core/health_http.py", "core/health_tcp.py"}
    for path in all_source_files:
        relative = str(path.relative_to(SRC_ROOT))
        if relative in permitted:
            continue
        code_only = _code_only(path.read_text(encoding="utf-8"))
        assert "import socket" not in code_only, relative
        assert "import ssl" not in code_only, relative


def test_only_health_runner_imports_concurrent_futures() -> None:
    all_source_files = sorted(SRC_ROOT.rglob("*.py"))
    for path in all_source_files:
        relative = str(path.relative_to(SRC_ROOT))
        if relative == "core/health_runner.py":
            continue
        code_only = _code_only(path.read_text(encoding="utf-8"))
        assert "concurrent.futures" not in code_only, relative


def test_no_bare_except_clauses_in_attempt_functions() -> None:
    for relative_path in ("core/health_http.py", "core/health_tcp.py"):
        text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
        assert "except Exception" not in text
        assert "except BaseException" not in text
        assert "except:" not in text
