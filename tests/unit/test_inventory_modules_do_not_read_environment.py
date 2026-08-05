"""Inventory collection modules never read named environment variables.

``core/config.py`` is the sole module permitted to do so. This is a
textual scan (consistent with the repo's other forbidden-pattern checks)
plus a runtime proof that a fully-cleared environment does not affect
inventory collection.
"""

from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "maops_pydevops"

_INVENTORY_MODULES = (
    "commands/inventory.py",
    "core/system_inventory.py",
    "core/filesystem_inventory.py",
    "core/inventory_models.py",
)


@pytest.mark.parametrize("relative_path", _INVENTORY_MODULES)
def test_module_never_references_os_environ_or_getenv(relative_path: str) -> None:
    text = (SRC_ROOT / relative_path).read_text(encoding="utf-8")
    assert "os.environ" not in text
    assert "os.getenv" not in text


def test_build_system_report_ignores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("PATH", raising=False)
    from maops_pydevops.core.system_inventory import build_system_report

    report = build_system_report(
        freedesktop_os_release=lambda: {"ID": "ubuntu"},
        getloadavg=lambda: (0.0, 0.0, 0.0),
        meminfo_lines=["MemTotal: 100 kB", "MemAvailable: 50 kB"],
        memory_os_family="Linux",
        uptime_line="10.0 0.0",
        uptime_os_family="Linux",
    )
    assert report.overall.value == "pass"


def test_build_filesystem_report_ignores_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("PATH", raising=False)
    from maops_pydevops.core.filesystem_inventory import build_filesystem_report

    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
