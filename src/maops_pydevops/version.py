"""Authoritative version lookup.

The version is declared exactly once, in ``pyproject.toml``. This module
reads it back via ``importlib.metadata`` at call time only — never at
import time — so importing this module has no side effects.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_DISTRIBUTION_NAME = "maops-pydevops"


def get_version() -> str:
    """Return the installed package version."""
    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0.0.0+unknown"
