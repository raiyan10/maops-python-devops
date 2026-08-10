"""``workflow validate`` (parsing/validation only) never touches the network or subprocess.

Mirrors ``test_no_network_health_boundary.py``'s "network-forbidden" style:
a monkeypatched ``socket.socket``/``socket.create_connection`` and
``subprocess.Popen`` both raise if ever called during validation of even a
workflow that *declares* network-capable (``health_http``/``health_tcp``)
or subprocess-capable (``tools_inspect``) steps -- because validation
parses and range-checks declared parameters only, it never actually
resolves a tool executable or opens a connection.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from maops_pydevops.core.workflow_parser import parse_workflow_file
from maops_pydevops.core.workflow_runner import MAX_WORKFLOW_STEPS

_FULL_WORKFLOW_TOML = """
schema_version = 1
name = "full"

[[steps]]
id = "doc"
kind = "doctor"

[[steps]]
id = "tools"
kind = "tools_inspect"
tools = ["git", "docker"]

[[steps]]
id = "sysinv"
kind = "inventory_system"

[[steps]]
id = "fsinv"
kind = "inventory_filesystem"
path = "."

[[steps]]
id = "logs"
kind = "logs_analyze"
path = "app.log"

[[steps]]
id = "http"
kind = "health_http"
urls = ["http://127.0.0.1:1/should-never-be-contacted"]

[[steps]]
id = "tcp"
kind = "health_tcp"
targets = ["127.0.0.1:1"]
"""


def test_validate_full_workflow_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted during validation")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)

    path = tmp_path / "wf.toml"
    path.write_text(_FULL_WORKFLOW_TOML, encoding="utf-8")
    workflow, error = parse_workflow_file(path)
    assert error is None
    assert workflow is not None
    assert len(workflow.steps) == 7


def test_validate_full_workflow_makes_no_subprocess_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess execution attempted during validation")

    monkeypatch.setattr(subprocess, "Popen", _fail)

    path = tmp_path / "wf.toml"
    path.write_text(_FULL_WORKFLOW_TOML, encoding="utf-8")
    workflow, error = parse_workflow_file(path)
    assert error is None
    assert workflow is not None


def test_max_workflow_steps_is_32() -> None:
    assert MAX_WORKFLOW_STEPS == 32


_WORKFLOW_MODULES = (
    "core/workflow_models.py",
    "core/workflow_parser.py",
)

_FORBIDDEN_TOKENS = (
    "subprocess",
    "socket",
    "ssl",
    "http.client",
    "urllib.request",
    "os.system(",
    "os.popen(",
    "shell=True",
    "eval(",
    "exec(",
    "pickle",
    "importlib",
    "__import__",
)


def _code_only(text: str) -> str:
    return text.split('"""', 2)[-1] if text.count('"""') >= 2 else text


@pytest.mark.parametrize("relative_path", _WORKFLOW_MODULES)
def test_workflow_parsing_modules_contain_no_forbidden_tokens(relative_path: str) -> None:
    src_root = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"
    text = (src_root / relative_path).read_text(encoding="utf-8")
    code_only = _code_only(text)
    for token in _FORBIDDEN_TOKENS:
        assert token not in code_only, f"{relative_path} references forbidden token {token!r}"
