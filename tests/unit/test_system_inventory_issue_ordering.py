"""build_system_report() collects issues in a fixed canonical order:
distribution -> cpu/load_average -> memory -> uptime.
"""

from maops_pydevops.core.system_inventory import build_system_report


def _failing_freedesktop() -> dict[str, str]:
    raise OSError("no os-release")


def _failing_loadavg() -> tuple[float, float, float]:
    raise OSError("no loadavg")


def test_issue_order_is_distribution_cpu_memory_uptime() -> None:
    report = build_system_report(
        freedesktop_os_release=_failing_freedesktop,
        getloadavg=_failing_loadavg,
        memory_os_family="Windows",
        uptime_os_family="Windows",
    )
    components = [issue.component for issue in report.issues]
    assert components == ["distribution", "load_average", "memory", "uptime"]


def test_partial_issue_subset_preserves_relative_order() -> None:
    report = build_system_report(
        getloadavg=_failing_loadavg,
        uptime_os_family="Windows",
    )
    components = [issue.component for issue in report.issues]
    assert components == ["load_average", "uptime"]


def test_no_issues_when_everything_succeeds() -> None:
    report = build_system_report(
        freedesktop_os_release=lambda: {"ID": "ubuntu"},
        getloadavg=lambda: (0.1, 0.1, 0.1),
        meminfo_lines=["MemTotal: 100 kB", "MemAvailable: 50 kB"],
        memory_os_family="Linux",
        uptime_line="100.0 0.0",
        uptime_os_family="Linux",
    )
    assert report.issues == ()
