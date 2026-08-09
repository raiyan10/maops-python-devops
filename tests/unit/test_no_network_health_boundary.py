"""Day 5 introduces network-capable health modules -- every other command
must retain its existing network prohibition unchanged. This is the
"network-forbidden" half of the boundary; see
``test_health_no_forbidden_tokens.py`` for the "network-capable" half.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"

#: Every module in the package except the ones explicitly permitted to
#: make network connections (core/health_http.py, core/health_tcp.py) or
#: to coordinate them (commands/health.py, core/health_runner.py -- the
#: latter never imports socket/ssl/http.client itself, only
#: concurrent.futures, but is excluded here for clarity since it exists
#: solely to serve the health feature).
_NETWORK_FORBIDDEN_MODULES = (
    "cli.py",
    "commands/config.py",
    "commands/doctor.py",
    "commands/tools.py",
    "commands/inventory.py",
    "commands/logs.py",
    "core/config.py",
    "core/config_models.py",
    "core/models.py",
    "core/runner.py",
    "core/system_inventory.py",
    "core/filesystem_inventory.py",
    "core/log_reader.py",
    "core/log_parsers.py",
    "core/log_redaction.py",
    "core/log_analysis.py",
    "core/log_models.py",
    "core/health_models.py",
    "core/output.py",
)

_NETWORK_TOKENS = ("socket", "ssl", "http.client", "urllib.request")


@pytest.mark.parametrize("relative_path", _NETWORK_FORBIDDEN_MODULES)
def test_module_never_references_networking_primitives(relative_path: str) -> None:
    text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
    # Docstrings legitimately *name* these concepts as things a module
    # deliberately does not do; only fail on a token in actual code.
    code_only = text.split('"""', 2)[-1] if text.count('"""') >= 2 else text
    for token in _NETWORK_TOKENS:
        assert token not in code_only, f"{relative_path} references forbidden token {token!r}"


def test_doctor_still_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from maops_pydevops.commands.doctor import build_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    build_report()


def test_config_show_still_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.commands.config import build_show_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)
    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    build_show_report()


def test_tools_inspect_still_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from maops_pydevops.commands.tools import build_inspect_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    build_inspect_report(
        tool_names=("git",),
        version="0.5.0",
        timeout_seconds=1.0,
        max_output_bytes=4096,
        config_path="/dev/null",
        which=lambda name: None,
    )


def test_inventory_system_still_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from maops_pydevops.commands.inventory import build_system_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    build_system_report()


def test_inventory_filesystem_still_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.commands.inventory import build_filesystem_report

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    build_filesystem_report(str(tmp_path), max_depth=2, max_entries=100, top=5)


def test_logs_parse_still_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.commands.logs import build_log_parse_report
    from maops_pydevops.core.log_models import LogInputFormat

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    path = tmp_path / "a.log"
    path.write_text('{"message": "hi"}\n', encoding="utf-8")
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=4096,
        max_line_bytes=256,
        max_events=10,
        redact=True,
    )
    assert error is None
    assert report is not None


def test_logs_analyze_still_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maops_pydevops.commands.logs import build_log_analysis_report
    from maops_pydevops.core.log_models import LogInputFormat

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    path = tmp_path / "a.log"
    path.write_text('{"message": "hi"}\n', encoding="utf-8")
    report, error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=100,
        max_bytes=4096,
        max_line_bytes=256,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=True,
    )
    assert error is None
    assert report is not None
