"""Malformed, negative, or internally inconsistent /proc/meminfo content is
rejected and reported as a warning, never fabricated or silently substituted.
"""

import pytest

import maops_pydevops.core.system_inventory as system_inventory_module
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import gather_memory_info


def test_mem_available_absent_leaves_total_populated_but_used_fields_null() -> None:
    """Partial population: MemFree is never read as a substitute for a
    missing MemAvailable -- total_bytes can stay populated while
    used_bytes/used_percent are simultaneously null."""
    lines = ["MemTotal: 10485760 kB", "MemFree: 2097152 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.available is True
    assert info.total_bytes == 10485760 * 1024
    assert info.available_bytes is None
    assert info.used_bytes is None
    assert info.used_percent is None
    assert issue is not None
    assert issue.status is CheckStatus.WARN
    assert "MemAvailable" in issue.detail


def test_malformed_meminfo_line_is_rejected() -> None:
    lines = ["MemTotal: not-a-number kB", "MemAvailable: 1000 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes is None
    assert issue is not None
    assert "unparseable" in issue.detail


def test_missing_mem_total_is_rejected() -> None:
    """MemTotal missing nulls total_bytes/used_bytes/used_percent, but a
    validly-parsed MemAvailable is still reported (the "exceeds total"
    consistency check only applies when total_bytes itself is known)."""
    lines = ["MemAvailable: 1000 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes is None
    assert info.available_bytes == 1000 * 1024
    assert info.used_bytes is None
    assert info.used_percent is None
    assert issue is not None
    assert "MemTotal" in issue.detail


def test_negative_mem_total_is_rejected() -> None:
    lines = ["MemTotal: -5 kB", "MemAvailable: 1000 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes is None
    assert issue is not None
    assert "negative" in issue.detail


def test_negative_mem_available_is_rejected() -> None:
    lines = ["MemTotal: 10000 kB", "MemAvailable: -1 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes == 10000 * 1024
    assert info.available_bytes is None
    assert issue is not None
    assert "negative" in issue.detail


def test_available_exceeding_total_is_rejected() -> None:
    lines = ["MemTotal: 1000 kB", "MemAvailable: 2000 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes == 1000 * 1024
    assert info.available_bytes is None
    assert info.used_bytes is None
    assert issue is not None
    assert "exceeds" in issue.detail


def test_zero_total_guards_against_division_by_zero() -> None:
    lines = ["MemTotal: 0 kB", "MemAvailable: 0 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes == 0
    assert info.used_bytes is None
    assert info.used_percent is None
    assert issue is not None


def test_bad_unit_line_is_rejected() -> None:
    lines = ["MemTotal: 1000 MB", "MemAvailable: 500 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes is None
    assert issue is not None


def test_used_percent_is_clamped_to_bounds() -> None:
    lines = ["MemTotal: 1000 kB", "MemAvailable: 0 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.used_percent is not None
    assert 0.0 <= info.used_percent <= 100.0
    assert issue is None


def test_line_without_colon_is_skipped_silently() -> None:
    lines = ["not a key-value line at all", "MemTotal: 1000 kB", "MemAvailable: 500 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes == 1000 * 1024
    assert issue is None


def test_duplicate_mem_total_keeps_first_occurrence() -> None:
    lines = ["MemTotal: 1000 kB", "MemTotal: 2000 kB", "MemAvailable: 500 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.total_bytes == 1000 * 1024


def test_duplicate_mem_available_keeps_first_occurrence() -> None:
    lines = ["MemTotal: 2000 kB", "MemAvailable: 500 kB", "MemAvailable: 1500 kB"]
    info, issue = gather_memory_info(meminfo_lines=lines, os_family="Linux")
    assert info.available_bytes == 500 * 1024


def test_missing_meminfo_file_on_linux_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_read_text(self: object, encoding: str = "utf-8") -> str:
        raise FileNotFoundError("/proc/meminfo")

    monkeypatch.setattr(system_inventory_module.Path, "read_text", _raise_read_text)
    info, issue = gather_memory_info(os_family="Linux")
    assert info.available is False
    assert issue is not None
