"""gather_distribution_info() degrades gracefully when unavailable."""

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.system_inventory import gather_distribution_info


def test_gather_distribution_info_success() -> None:
    fake_data = {"ID": "ubuntu", "NAME": "Ubuntu", "VERSION_ID": "22.04"}
    info, issue = gather_distribution_info(freedesktop_os_release=lambda: fake_data)
    assert info.id == "ubuntu"
    assert info.name == "Ubuntu"
    assert info.version_id == "22.04"
    assert info.available is True
    assert issue is None


def test_gather_distribution_info_unavailable_produces_warning() -> None:
    def _raise() -> dict[str, str]:
        raise OSError("no /etc/os-release")

    info, issue = gather_distribution_info(freedesktop_os_release=_raise)
    assert info.id is None
    assert info.name is None
    assert info.version_id is None
    assert info.available is False
    assert issue is not None
    assert issue.component == "distribution"
    assert issue.status is CheckStatus.WARN


def test_gather_distribution_info_missing_keys_stay_none() -> None:
    info, issue = gather_distribution_info(freedesktop_os_release=lambda: {})
    assert info.id is None
    assert info.name is None
    assert info.version_id is None
    assert info.available is True
    assert issue is None
