"""gather_cpu_info() load-average collection and its failure mode."""

import pytest

import maops_pydevops.core.system_inventory as system_inventory_module
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import gather_cpu_info


def test_load_average_success() -> None:
    info, issue = gather_cpu_info(cpu_count=4, getloadavg=lambda: (1.5, 2.5, 3.5))
    assert info.load_average_1m == 1.5
    assert info.load_average_5m == 2.5
    assert info.load_average_15m == 3.5
    assert issue is None


def test_load_average_unavailable_produces_warning() -> None:
    def _raise() -> tuple[float, float, float]:
        raise OSError("getloadavg not supported")

    info, issue = gather_cpu_info(cpu_count=4, getloadavg=_raise)
    assert info.load_average_1m is None
    assert info.load_average_5m is None
    assert info.load_average_15m is None
    assert info.logical_count == 4
    assert issue is not None
    assert issue.component == "load_average"
    assert issue.status is CheckStatus.WARN


def test_load_average_missing_attribute_is_a_warning_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """os.getloadavg does not exist at all on Windows -- the attribute
    lookup itself, not just the call, must degrade gracefully rather
    than raising an uncaught AttributeError."""
    monkeypatch.delattr(system_inventory_module.os, "getloadavg", raising=False)
    info, issue = gather_cpu_info(cpu_count=4)
    assert info.load_average_1m is None
    assert info.load_average_5m is None
    assert info.load_average_15m is None
    assert info.logical_count == 4
    assert issue is not None
    assert issue.component == "load_average"
    assert issue.status is CheckStatus.WARN


def test_load_average_injected_override_bypasses_hasattr_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit getloadavg= override must still be used even when the
    real os.getloadavg attribute is absent (e.g. simulating Windows while
    still exercising the success/failure branches deterministically)."""
    monkeypatch.delattr(system_inventory_module.os, "getloadavg", raising=False)
    info, issue = gather_cpu_info(cpu_count=4, getloadavg=lambda: (0.1, 0.2, 0.3))
    assert info.load_average_1m == 0.1
    assert issue is None
