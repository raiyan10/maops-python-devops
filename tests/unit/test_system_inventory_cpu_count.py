"""gather_cpu_info() distinguishes "not overridden" from an overridden None."""

from maops_pydevops.core.system_inventory import gather_cpu_info


def _fake_loadavg() -> tuple[float, float, float]:
    return (0.1, 0.2, 0.3)


def test_gather_cpu_info_with_injected_count() -> None:
    info, issue = gather_cpu_info(cpu_count=8, getloadavg=_fake_loadavg)
    assert info.logical_count == 8
    assert issue is None


def test_gather_cpu_info_with_none_override_stays_none() -> None:
    """An explicit ``cpu_count=None`` override must be honored as None, not
    treated as "no override" (os.cpu_count() itself can legitimately return
    None on an indeterminate platform)."""
    info, issue = gather_cpu_info(cpu_count=None, getloadavg=_fake_loadavg)
    assert info.logical_count is None
    assert issue is None


def test_gather_cpu_info_no_override_uses_real_cpu_count() -> None:
    info, issue = gather_cpu_info(getloadavg=_fake_loadavg)
    assert isinstance(info.logical_count, int) or info.logical_count is None
