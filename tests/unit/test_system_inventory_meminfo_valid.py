"""gather_memory_info() computes used_bytes/used_percent from valid /proc/meminfo content."""

from maops_pydevops.core.system_inventory import gather_memory_info


def test_valid_meminfo_computes_used_bytes_and_percent() -> None:
    lines = [
        "MemTotal:       10485760 kB",
        "MemFree:         2097152 kB",
        "MemAvailable:    5242880 kB",
    ]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.available is True
    assert info.total_bytes == 10485760 * 1024
    assert info.available_bytes == 5242880 * 1024
    assert info.used_bytes == (10485760 - 5242880) * 1024
    assert info.used_percent == 50.0
    assert issue is None


def test_meminfo_used_percent_is_bounded() -> None:
    lines = ["MemTotal: 1000 kB", "MemAvailable: 1000 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.used_percent == 0.0
    assert issue is None
