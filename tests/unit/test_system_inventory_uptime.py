"""gather_uptime_info() parses the first numeric token of /proc/uptime."""

import pytest

import maops_pydevops.core.system_inventory as system_inventory_module
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import gather_uptime_info


def test_valid_uptime() -> None:
    info, issue = gather_uptime_info(uptime_line="12345.67 98765.43", os_family="Linux")
    assert info.available is True
    assert info.seconds == 12345.67
    assert issue is None


def test_malformed_uptime_is_rejected() -> None:
    info, issue = gather_uptime_info(uptime_line="not-a-number", os_family="Linux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None
    assert issue.status is CheckStatus.WARN


def test_negative_uptime_is_rejected() -> None:
    info, issue = gather_uptime_info(uptime_line="-1.0 0.0", os_family="Linux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None


def test_nan_uptime_is_rejected() -> None:
    info, issue = gather_uptime_info(uptime_line="nan 0.0", os_family="Linux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None


def test_infinite_uptime_is_rejected() -> None:
    info, issue = gather_uptime_info(uptime_line="inf 0.0", os_family="Linux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None


def test_empty_uptime_content_is_rejected() -> None:
    info, issue = gather_uptime_info(uptime_line="", os_family="Linux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None


def test_missing_procfs_is_a_warning() -> None:
    # A real Path("/proc/uptime").read_text() failure would depend on host
    # state; the non-Linux short-circuit exercises the identical
    # unavailable+warning shape deterministically.
    info, issue = gather_uptime_info(os_family="NotLinux")
    assert info.available is False
    assert info.seconds is None
    assert issue is not None


def test_missing_uptime_file_on_linux_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_read_text(self: object, encoding: str = "utf-8") -> str:
        raise FileNotFoundError("/proc/uptime")

    monkeypatch.setattr(system_inventory_module.Path, "read_text", _raise_read_text)
    info, issue = gather_uptime_info(os_family="Linux")
    assert info.available is False
    assert issue is not None
