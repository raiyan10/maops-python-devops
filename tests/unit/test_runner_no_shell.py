"""run_command() never invokes a shell, and the runtime source never contains
shell=True, os.system, eval(, exec(, pickle, sudo, or logging configuration.
"""

from pathlib import Path

import pytest

from maops_pydevops.core.runner import CommandSpec, run_command

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"

_FORBIDDEN_PATTERNS = (
    "shell=True",
    "os.system",
    "os.popen",
    "eval(",
    "exec(",
    "pickle",
    "sudo",
    "logging.basicConfig",
    "logging.config",
)


def test_shell_is_always_false(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class _FakeCompleted:
        returncode = 0
        stdout = b""
        stderr = b""

    def _fake_run(*args: object, **kwargs: object) -> _FakeCompleted:
        captured_kwargs.update(kwargs)
        return _FakeCompleted()

    import maops_pydevops.core.runner as runner_module

    monkeypatch.setattr(runner_module.subprocess, "run", _fake_run)

    spec = CommandSpec(argv=("echo", "hi"), timeout_seconds=5.0, max_output_bytes=65536)
    run_command(spec)

    assert captured_kwargs["shell"] is False
    assert captured_kwargs["stdin"] is runner_module.subprocess.DEVNULL


def test_no_forbidden_patterns_anywhere_in_source() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            assert pattern not in text, f"forbidden pattern {pattern!r} found in {path}"


def test_only_runner_module_imports_subprocess() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        if path.name == "runner.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "import subprocess" not in text, f"unexpected subprocess import in {path}"


def test_no_module_imports_logging() -> None:
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import logging" not in text, f"unexpected logging import in {path}"


def test_only_health_modules_import_socket() -> None:
    # Day 5 introduces the package's first intentional network access,
    # isolated to core/health_http.py and core/health_tcp.py -- every
    # other module retains the prior "no socket" invariant unchanged. See
    # tests/unit/test_health_no_forbidden_tokens.py and
    # tests/unit/test_no_network_health_boundary.py for the full
    # network-boundary regression coverage.
    permitted = {"health_http.py", "health_tcp.py"}
    for path in SRC_ROOT.rglob("*.py"):
        if path.name in permitted:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import socket" not in text, f"unexpected socket import in {path}"
