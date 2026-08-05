"""Memory and uptime collection short-circuit to unavailable+warning on
non-Linux platforms, without ever touching real /proc content."""

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import gather_memory_info, gather_uptime_info


def test_memory_unavailable_on_windows() -> None:
    info, issue = gather_memory_info(os_family="Windows")
    assert info.available is False
    assert info.total_bytes is None
    assert info.available_bytes is None
    assert info.used_bytes is None
    assert info.used_percent is None
    assert issue is not None
    assert issue.component == "memory"
    assert issue.status is CheckStatus.WARN


def test_memory_unavailable_on_darwin() -> None:
    info, issue = gather_memory_info(os_family="Darwin")
    assert info.available is False
    assert issue is not None


def test_uptime_unavailable_on_windows() -> None:
    info, issue = gather_uptime_info(os_family="Windows")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None
    assert issue.component == "uptime"
    assert issue.status is CheckStatus.WARN


def test_non_linux_gather_never_reads_meminfo_lines_argument_is_ignored() -> None:
    """Even if meminfo_lines were somehow supplied, a non-Linux os_family
    always short-circuits before parsing -- proving the OS gate runs first."""
    info, issue = gather_memory_info(meminfo_lines=["MemTotal: 100 kB"], os_family="Windows")
    assert info.available is False
    assert issue is not None
