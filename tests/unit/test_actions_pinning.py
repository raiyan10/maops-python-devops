"""CI workflow actions must be pinned to a full commit SHA with a version comment."""

import re
from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "python-validation.yml"
)
_USES_PATTERN = re.compile(r"^\s*-?\s*uses:\s*(.+?)\s*$")
_PINNED_PATTERN = re.compile(r"^[^@]+@[0-9a-f]{40}\s+#\s*v\d+\.\d+\.\d+\s*$")


def _iter_uses_values(text: str) -> list[str]:
    values = []
    for line in text.splitlines():
        match = _USES_PATTERN.match(line)
        if match:
            values.append(match.group(1))
    return values


def test_workflow_file_exists() -> None:
    assert WORKFLOW_PATH.is_file()


def test_all_actions_are_pinned_to_a_commit_sha() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    uses_values = _iter_uses_values(text)
    assert uses_values, "workflow must reference at least one action"
    for value in uses_values:
        assert _PINNED_PATTERN.match(value), f"unpinned or malformed action reference: {value}"


def test_pinned_pattern_rejects_tags_and_branches() -> None:
    assert _PINNED_PATTERN.match("actions/checkout@v4") is None
    assert _PINNED_PATTERN.match("actions/checkout@main") is None


def test_pinned_pattern_accepts_full_sha_with_version_comment() -> None:
    assert _PINNED_PATTERN.match(
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
    )
