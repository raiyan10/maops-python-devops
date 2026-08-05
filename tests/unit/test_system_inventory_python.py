"""gather_python_info() reports interpreter facts, injectable for tests."""

from maops_pydevops.core.system_inventory import gather_python_info


def test_gather_python_info_uses_injected_values() -> None:
    info = gather_python_info(
        version="3.12.1", implementation="CPython", executable="/usr/bin/python3.12"
    )
    assert info.version == "3.12.1"
    assert info.implementation == "CPython"
    assert info.executable == "/usr/bin/python3.12"


def test_gather_python_info_defaults_to_real_values() -> None:
    info = gather_python_info()
    assert isinstance(info.version, str)
    assert isinstance(info.implementation, str)
    assert isinstance(info.executable, str)
