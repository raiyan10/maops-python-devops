"""Supported / unsupported OS family simulation via dependency injection."""

import pytest

from maops_pydevops.core.platform import is_supported_os


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Linux", True),
        ("Darwin", True),
        ("Windows", True),
        ("Plan9", False),
        ("", False),
    ],
)
def test_is_supported_os(system: str, expected: bool) -> None:
    assert is_supported_os(system) is expected
