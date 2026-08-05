"""gather_host_info() collects host/OS facts via injectable overrides."""

from types import SimpleNamespace

from maops_pydevops.core.system_inventory import gather_host_info


def test_gather_host_info_uses_injected_uname_and_hostname() -> None:
    fake_uname = SimpleNamespace(
        system="Linux", release="6.1.0", version="#1 SMP", machine="x86_64"
    )
    info = gather_host_info(uname=fake_uname, hostname="myhost")
    assert info.hostname == "myhost"
    assert info.os_family == "Linux"
    assert info.os_release == "6.1.0"
    assert info.os_version == "#1 SMP"
    assert info.machine == "x86_64"


def test_empty_hostname_normalizes_to_none() -> None:
    fake_uname = SimpleNamespace(system="Linux", release="6.1.0", version="", machine="x86_64")
    info = gather_host_info(uname=fake_uname, hostname="")
    assert info.hostname is None


def test_empty_uname_version_normalizes_to_none() -> None:
    fake_uname = SimpleNamespace(system="Linux", release="6.1.0", version="", machine="x86_64")
    info = gather_host_info(uname=fake_uname, hostname="host")
    assert info.os_version is None


def test_gather_host_info_defaults_to_real_platform_calls() -> None:
    info = gather_host_info()
    assert isinstance(info.os_family, str)
    assert isinstance(info.os_release, str)
    assert isinstance(info.machine, str)
