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

import os
import socket
import subprocess
from pathlib import Path

import pytest

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.workflow_parser import parse_workflow_file
from maops_pydevops.core.workflow_runner import MAX_WORKFLOW_STEPS, run_workflow

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


def test_run_workflow_makes_no_subprocess_calls_with_real_doctor_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dynamic proof, not just the static forbidden-token scan below, that
    ``run_workflow()`` -- the module that actually *executes* steps, where
    CLAUDE.md's "never a recursive maops-py subprocess" language
    specifically applies -- makes zero subprocess calls. Uses the real
    ``build_doctor_report()`` rather than a mock, so a hypothetical
    ``subprocess.run(["maops-py", ...])`` call added directly inside
    ``_run_step()`` would be caught here even though every other
    ``workflow_runner`` test monkeypatches ``build_doctor_report`` away
    (day-06-test-review.md M-2)."""

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess execution attempted during workflow run")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "call", _fail)
    monkeypatch.setattr(os, "system", _fail)

    path = tmp_path / "wf.toml"
    path.write_text(
        'schema_version = 1\nname = "real-doctor"\n\n[[steps]]\nid = "d"\nkind = "doctor"\n',
        encoding="utf-8",
    )
    workflow, error = parse_workflow_file(path)
    assert error is None
    assert workflow is not None

    report = run_workflow(workflow, workflow_path=str(path), workflow_dir=tmp_path)
    assert len(report.steps) == 1
    assert report.steps[0].status in (CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL)


_WORKFLOW_MODULES = (
    "core/workflow_models.py",
    "core/workflow_parser.py",
    "core/workflow_runner.py",
    "commands/workflow.py",
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
