"""Text output for both inventory commands: stable headings, no ANSI."""

from pathlib import Path

import pytest

import maops_pydevops.cli as cli_module
from maops_pydevops.cli import main


def test_system_text_output_contains_stable_headings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["inventory", "system"])
    out = capsys.readouterr().out
    assert "System Inventory" in out
    assert "Hostname:" in out
    assert "OS:" in out
    assert "OS version:" in out
    assert "Machine:" in out
    assert "Distribution:" in out
    assert "Python:" in out
    assert "Python executable:" in out
    assert "CPU logical count:" in out
    assert "Load average (1/5/15):" in out
    assert "Memory used:" in out
    assert "Uptime:" in out
    assert "Issues:" in out
    assert "Overall status:" in out
    assert "\x1b" not in out


def test_system_text_output_shows_unavailable_placeholders_and_issues(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from maops_pydevops.core.system_inventory import build_system_report

    def _raise_loadavg() -> tuple[float, float, float]:
        raise OSError("unsupported")

    def _fake_build_report() -> object:
        return build_system_report(
            getloadavg=_raise_loadavg,
            memory_os_family="Windows",
            uptime_os_family="Windows",
        )

    monkeypatch.setattr(cli_module, "build_system_report", _fake_build_report)
    main(["inventory", "system"])
    out = capsys.readouterr().out
    assert "Load average (1/5/15): (unavailable)" in out
    assert "Memory used:           (unavailable)" in out
    assert "Uptime:                (unavailable)" in out
    assert "[WARN]" in out


def test_filesystem_text_output_contains_stable_headings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    main(["inventory", "filesystem", str(tmp_path)])
    out = capsys.readouterr().out
    assert "Filesystem Inventory" in out
    assert "Root:" in out
    assert "Max depth:" in out
    assert "Max entries:" in out
    assert "Scanned entries:" in out
    assert "Directories:" in out
    assert "Files:" in out
    assert "Total file bytes:" in out
    assert "Max depth reached:" in out
    assert "Truncated:" in out
    assert "Largest files:" in out
    assert "Issues:" in out
    assert "Overall status:" in out
    assert "\x1b" not in out
