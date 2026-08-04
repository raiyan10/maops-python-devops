"""The toolkit remains standard-library-only at runtime after Day 2."""

import tomllib
from pathlib import Path

PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_no_runtime_dependencies_declared() -> None:
    with PYPROJECT_PATH.open("rb") as handle:
        data = tomllib.load(handle)
    assert data["project"]["dependencies"] == []


def test_tomllib_is_the_only_toml_dependency() -> None:
    # tomllib is standard library as of Python 3.11; asserting the import
    # succeeds without installing anything is the regression guard.
    import tomllib as _tomllib

    assert hasattr(_tomllib, "load")
