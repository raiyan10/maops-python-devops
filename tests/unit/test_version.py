"""Authoritative version source: pyproject.toml, read back via importlib.metadata."""

import re
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import maops_pydevops.version as version_module
from maops_pydevops.version import get_version

CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def test_get_version_is_0_2_0() -> None:
    assert get_version() == "0.2.0"


def test_matches_changelog_latest_entry() -> None:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, flags=re.MULTILINE)
    assert match is not None, "CHANGELOG.md must contain a version heading"
    assert match.group(1) == get_version()


def test_get_version_falls_back_when_distribution_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(version_module, "version", _raise)
    assert version_module.get_version() == "0.0.0+unknown"
