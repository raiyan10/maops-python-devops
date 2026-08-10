"""Exhaustive per-field type/range validation coverage for every workflow step kind.

``core/workflow_parser.py``'s field helpers (``_opt_int``, ``_opt_float``,
``_opt_bool``, ``_opt_str``, ``_opt_str_tuple``, ``_req_str_tuple``) are
each reused across every step kind; this file drives every field of every
kind through its invalid-type and out-of-range branches once, rather than
relying on incidental coverage from the schema-shape tests in
``test_workflow_parser.py``.
"""

from __future__ import annotations

import pytest

from maops_pydevops.core.workflow_parser import validate_workflow_document


def _document(step: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "name": "x", "steps": [step]}


_INVALID_FIELD_CASES: list[tuple[dict[str, object], str]] = [
    # tools_inspect
    ({"id": "a", "kind": "tools_inspect", "tools": "git"}, "tools"),
    ({"id": "a", "kind": "tools_inspect", "tools": [1, 2]}, "tools"),
    ({"id": "a", "kind": "tools_inspect", "timeout_seconds": "fast"}, "timeout_seconds"),
    ({"id": "a", "kind": "tools_inspect", "timeout_seconds": 0}, "timeout_seconds"),
    ({"id": "a", "kind": "tools_inspect", "timeout_seconds": 301.0}, "timeout_seconds"),
    # inventory_filesystem
    ({"id": "a", "kind": "inventory_filesystem", "path": 5}, "path"),
    ({"id": "a", "kind": "inventory_filesystem", "path": ""}, "path"),
    ({"id": "a", "kind": "inventory_filesystem", "max_depth": "two"}, "max_depth"),
    ({"id": "a", "kind": "inventory_filesystem", "max_depth": -1}, "max_depth"),
    ({"id": "a", "kind": "inventory_filesystem", "max_depth": 65}, "max_depth"),
    ({"id": "a", "kind": "inventory_filesystem", "max_entries": "many"}, "max_entries"),
    ({"id": "a", "kind": "inventory_filesystem", "max_entries": 0}, "max_entries"),
    ({"id": "a", "kind": "inventory_filesystem", "max_entries": 1_000_001}, "max_entries"),
    ({"id": "a", "kind": "inventory_filesystem", "top": "ten"}, "top"),
    ({"id": "a", "kind": "inventory_filesystem", "top": -1}, "top"),
    ({"id": "a", "kind": "inventory_filesystem", "top": 101}, "top"),
    # logs_analyze
    ({"id": "a", "kind": "logs_analyze", "path": 5}, "path"),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "input_format": "xml"}, "input_format"),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "max_lines": "many"}, "max_lines"),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "max_lines": 0}, "max_lines"),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "max_bytes": 100}, "max_bytes"),
    (
        {"id": "a", "kind": "logs_analyze", "path": "app.log", "max_line_bytes": 100_000_000},
        "max_line_bytes",
    ),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "top": 101}, "top"),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "bucket_seconds": 0}, "bucket_seconds"),
    (
        {"id": "a", "kind": "logs_analyze", "path": "app.log", "repeat_threshold": 1},
        "repeat_threshold",
    ),
    (
        {"id": "a", "kind": "logs_analyze", "path": "app.log", "error_threshold": 0},
        "error_threshold",
    ),
    ({"id": "a", "kind": "logs_analyze", "path": "app.log", "redact": "yes"}, "redact"),
    # health_http
    ({"id": "a", "kind": "health_http", "urls": "http://x/"}, "urls"),
    ({"id": "a", "kind": "health_http", "urls": []}, "urls"),
    ({"id": "a", "kind": "health_http", "urls": ["http://x/"], "method": "POST"}, "method"),
    (
        {"id": "a", "kind": "health_http", "urls": ["http://x/"], "expect_status_min": 50},
        "expect_status_min",
    ),
    (
        {"id": "a", "kind": "health_http", "urls": ["http://x/"], "expect_status_max": 700},
        "expect_status_max",
    ),
    (
        {"id": "a", "kind": "health_http", "urls": ["http://x/"], "timeout_seconds": 0},
        "timeout_seconds",
    ),
    ({"id": "a", "kind": "health_http", "urls": ["http://x/"], "retries": 6}, "retries"),
    (
        {"id": "a", "kind": "health_http", "urls": ["http://x/"], "retry_delay_seconds": 31},
        "retry_delay_seconds",
    ),
    ({"id": "a", "kind": "health_http", "urls": ["http://x/"], "workers": 0}, "workers"),
    ({"id": "a", "kind": "health_http", "urls": ["http://x/"], "workers": 33}, "workers"),
    # health_tcp
    ({"id": "a", "kind": "health_tcp", "targets": "127.0.0.1:1"}, "targets"),
    ({"id": "a", "kind": "health_tcp", "targets": []}, "targets"),
    (
        {"id": "a", "kind": "health_tcp", "targets": ["127.0.0.1:1"], "timeout_seconds": 61},
        "timeout_seconds",
    ),
    ({"id": "a", "kind": "health_tcp", "targets": ["127.0.0.1:1"], "retries": -1}, "retries"),
    (
        {"id": "a", "kind": "health_tcp", "targets": ["127.0.0.1:1"], "retry_delay_seconds": -1},
        "retry_delay_seconds",
    ),
    ({"id": "a", "kind": "health_tcp", "targets": ["127.0.0.1:1"], "workers": 0}, "workers"),
]


@pytest.mark.parametrize(("step", "expected_field"), _INVALID_FIELD_CASES)
def test_invalid_field_rejected(step: dict[str, object], expected_field: str) -> None:
    workflow, error = validate_workflow_document(_document(step))
    assert workflow is None
    assert error is not None
    assert expected_field in error


def test_top_level_steps_non_list_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": "not-a-list"}
    )
    assert workflow is None
    assert error is not None
    assert "array of tables" in error


def test_read_error_on_workflow_file_maps_to_could_not_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    from maops_pydevops.core.workflow_parser import parse_workflow_file

    def _raise_os_error(self: Path, *args: object, **kwargs: object) -> object:
        raise OSError("simulated read failure")

    monkeypatch.setattr(Path, "open", _raise_os_error)
    workflow, error = parse_workflow_file(Path("/nonexistent/does-not-matter.toml"))
    assert workflow is None
    assert error is not None
    assert "could not be read" in error
