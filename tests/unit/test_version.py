"""Authoritative version source: pyproject.toml, read back via importlib.metadata."""

import json
import re
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import maops_pydevops.version as version_module
from maops_pydevops.version import get_version

CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def test_get_version_is_0_7_0() -> None:
    assert get_version() == "0.7.0"


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


_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Docs whose embedded ``maops-py`` CLI output examples are explicitly
#: intended to represent the CURRENT release's output -- not every
#: version string in the repository. CHANGELOG.md's per-release headings
#: and docs/roadmap.md's historical version references are deliberately
#: excluded: those are supposed to name past releases, and rejecting
#: every older version string anywhere would make the test meaningless
#: (Day 6 release-readiness follow-up, deferred finding L-2: "no
#: regression test pins the fixed doc version examples against drift").
_CURRENT_VERSION_EXAMPLE_DOCS = (
    "README.md",
    "docs/inventory.md",
    "docs/health-checks.md",
    "docs/log-analysis.md",
    "docs/log-parsing.md",
    "docs/workflows.md",
)

#: A text-renderer ``Version:`` line -- always at the start of a line, so
#: this never matches a nested field like "Python version:".
_TEXT_VERSION_LINE_PATTERN = re.compile(r"^Version:\s+(\d+\.\d+\.\d+)", flags=re.MULTILINE)

#: A fenced ```json code block, parsed as JSON below rather than matched
#: with a flat regex -- a flat ``"version":\s*"..."`` regex would also
#: match the *nested* ``python.version`` runtime-version field (e.g.
#: ``"3.12.3"``), which is not the package version and must not be
#: compared against it.
_JSON_BLOCK_PATTERN = re.compile(r"```json\n(.*?)```", flags=re.DOTALL)


@pytest.mark.parametrize("doc", _CURRENT_VERSION_EXAMPLE_DOCS)
def test_doc_current_version_examples_match_package_version(doc: str) -> None:
    text = (_REPO_ROOT / doc).read_text(encoding="utf-8")
    text_matches = _TEXT_VERSION_LINE_PATTERN.findall(text)

    json_matches: list[str] = []
    for block in _JSON_BLOCK_PATTERN.findall(text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            json_matches.append(data["version"])

    all_matches = text_matches + json_matches
    assert all_matches, f"{doc} no longer contains a recognizable current-version example"
    for found in all_matches:
        assert found == get_version(), f"{doc} contains a stale version example: {found!r}"
