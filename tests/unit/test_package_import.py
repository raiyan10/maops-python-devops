"""Package import succeeds and exposes the expected public API."""

import maops_pydevops


def test_import_succeeds() -> None:
    assert maops_pydevops is not None


def test_get_version_is_exposed() -> None:
    assert hasattr(maops_pydevops, "get_version")
    assert callable(maops_pydevops.get_version)
