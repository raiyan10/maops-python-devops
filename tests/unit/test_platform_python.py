"""Supported / unsupported Python version simulation via dependency injection."""

import pytest

from maops_pydevops.core.platform import is_supported_python


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((3, 11, 0), True),
        ((3, 12, 4), True),
        ((3, 13, 0), True),
        ((3, 14, 0), True),
        ((3, 10, 9), False),
        ((2, 7, 18), False),
    ],
)
def test_is_supported_python(version: tuple[int, int, int], expected: bool) -> None:
    assert is_supported_python(version) is expected


def test_is_supported_python_uses_current_interpreter_by_default() -> None:
    assert is_supported_python() is True
