"""Explicit, typed serialization of inventory models. No dict-spreading."""

import json

import pytest

from maops_pydevops.core.inventory_models import (
    CpuInfo,
    DistributionInfo,
    FilesystemInventoryReport,
    FilesystemScanOptions,
    FilesystemScanSummary,
    HostInfo,
    InventoryIssue,
    LargestFileEntry,
    MemoryInfo,
    SystemInventoryReport,
    SystemPythonInfo,
    UptimeInfo,
)
from maops_pydevops.core.models import CheckStatus


def test_inventory_issue_to_dict() -> None:
    issue = InventoryIssue(component="memory", status=CheckStatus.WARN, detail="unavailable")
    assert issue.to_dict() == {"component": "memory", "status": "warn", "detail": "unavailable"}


def _make_system_report() -> SystemInventoryReport:
    return SystemInventoryReport(
        version="0.3.0",
        host=HostInfo(
            hostname="host", os_family="Linux", os_release="6.0", os_version=None, machine="x86_64"
        ),
        distribution=DistributionInfo(
            id="ubuntu", name="Ubuntu", version_id="22.04", available=True
        ),
        python=SystemPythonInfo(
            version="3.12.1", implementation="CPython", executable="/usr/bin/python3"
        ),
        cpu=CpuInfo(
            logical_count=4, load_average_1m=0.1, load_average_5m=0.2, load_average_15m=0.3
        ),
        memory=MemoryInfo(
            available=True, total_bytes=1000, available_bytes=500, used_bytes=500, used_percent=50.0
        ),
        uptime=UptimeInfo(available=True, seconds=123.45),
        issues=(),
        overall=CheckStatus.PASS,
    )


def test_system_inventory_report_to_dict_and_to_json_agree() -> None:
    report = _make_system_report()
    data = report.to_dict()
    assert data["version"] == "0.3.0"
    assert data["overall"] == "pass"
    assert data["host"]["hostname"] == "host"
    assert data["host"]["os_version"] is None
    assert json.loads(report.to_json()) == data


def test_system_inventory_models_are_frozen() -> None:
    host = HostInfo(
        hostname="h", os_family="Linux", os_release="1", os_version=None, machine="x86_64"
    )
    with pytest.raises((AttributeError, TypeError)):
        host.hostname = "other"  # type: ignore[misc]


def _make_filesystem_report() -> FilesystemInventoryReport:
    return FilesystemInventoryReport(
        version="0.3.0",
        root="/tmp/x",
        options=FilesystemScanOptions(max_depth=2, max_entries=100, top=5),
        summary=FilesystemScanSummary(
            scanned_entries=1,
            directories=0,
            files=1,
            symlinks=0,
            other=0,
            total_file_bytes=10,
            skipped_entries=0,
            inaccessible_entries=0,
            different_filesystem_entries=0,
        ),
        largest_files=(
            LargestFileEntry(
                path="/tmp/x/a.txt", relative_path="a.txt", size_bytes=10, modified_ns=1
            ),
        ),
        issues=(InventoryIssue(component="x", status=CheckStatus.WARN, detail="d"),),
        max_depth_reached=False,
        truncated=False,
        overall=CheckStatus.WARN,
    )


def test_filesystem_inventory_report_to_dict_and_to_json_agree() -> None:
    report = _make_filesystem_report()
    data = report.to_dict()
    assert data["root"] == "/tmp/x"
    assert data["overall"] == "warn"
    assert data["options"] == {
        "max_depth": 2,
        "max_entries": 100,
        "top": 5,
        "follow_symlinks": False,
        "same_filesystem": True,
    }
    assert isinstance(data["largest_files"], list)
    assert data["largest_files"][0]["relative_path"] == "a.txt"
    assert json.loads(report.to_json()) == data


def test_filesystem_options_default_flags_are_fixed() -> None:
    options = FilesystemScanOptions(max_depth=1, max_entries=1, top=1)
    assert options.follow_symlinks is False
    assert options.same_filesystem is True


def test_filesystem_inventory_models_are_frozen() -> None:
    summary = FilesystemScanSummary(
        scanned_entries=0,
        directories=0,
        files=0,
        symlinks=0,
        other=0,
        total_file_bytes=0,
        skipped_entries=0,
        inaccessible_entries=0,
        different_filesystem_entries=0,
    )
    with pytest.raises((AttributeError, TypeError)):
        summary.files = 1  # type: ignore[misc]
