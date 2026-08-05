"""build_system_report()'s overall reflects issue severity: pass/warn/fail."""

from maops_pydevops.core.inventory_models import InventoryIssue
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import _compute_overall, build_system_report


def test_overall_is_pass_when_no_issues() -> None:
    report = build_system_report(
        freedesktop_os_release=lambda: {"ID": "ubuntu"},
        getloadavg=lambda: (0.1, 0.1, 0.1),
        meminfo_lines=["MemTotal: 100 kB", "MemAvailable: 50 kB"],
        memory_os_family="Linux",
        uptime_line="100.0 0.0",
        uptime_os_family="Linux",
    )
    assert report.overall is CheckStatus.PASS


def test_overall_is_warn_when_any_issue_present() -> None:
    report = build_system_report(memory_os_family="Windows")
    assert report.overall is CheckStatus.WARN


def test_compute_overall_pass_warn_fail_directly() -> None:
    assert _compute_overall(()) is CheckStatus.PASS
    assert (
        _compute_overall((InventoryIssue(component="x", status=CheckStatus.WARN, detail="d"),))
        is CheckStatus.WARN
    )
    assert (
        _compute_overall((InventoryIssue(component="x", status=CheckStatus.FAIL, detail="d"),))
        is CheckStatus.FAIL
    )
