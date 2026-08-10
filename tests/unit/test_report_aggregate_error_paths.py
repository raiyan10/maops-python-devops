"""Malformed-field branches of ``core/report_aggregate.py`` normalization,
one per report kind, plus the ``_status_field`` invalid-value branch and
the ``build_aggregate_report`` normalization-failure passthrough.

Uses minimal, purpose-built fixtures (rather than importing the fuller
schema fixtures from ``test_report_aggregate.py``) so each test only
carries the fields relevant to the branch it exercises.
"""

from __future__ import annotations

import json
from pathlib import Path

from maops_pydevops.core.report_aggregate import (
    _status_field,
    build_aggregate_report,
    normalize_report,
)
from maops_pydevops.core.report_models import ReportKind


def test_status_field_invalid_value_returns_none() -> None:
    assert _status_field({"overall": "not-a-status"}) is None


def test_status_field_missing_key_returns_none() -> None:
    assert _status_field({}) is None


def test_normalize_doctor_invalid_check_entry() -> None:
    raw = {
        "version": "0.6.0",
        "overall": "pass",
        "checks": [{"status": "not-a-status"}],
    }
    normalized, error = normalize_report(ReportKind.DOCTOR, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "invalid checks entry" in error


def test_normalize_tools_inspect_missing_required_field() -> None:
    raw = {"overall": "pass", "tools": []}
    normalized, error = normalize_report(ReportKind.TOOLS_INSPECT, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_tools_inspect_invalid_tools_entry() -> None:
    raw = {"version": "0.6.0", "overall": "pass", "tools": [{"status": "not-a-status"}]}
    normalized, error = normalize_report(ReportKind.TOOLS_INSPECT, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "invalid tools entry" in error


def test_normalize_inventory_system_missing_required_field() -> None:
    raw = {"version": "0.6.0", "overall": "pass", "issues": []}
    normalized, error = normalize_report(ReportKind.INVENTORY_SYSTEM, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_inventory_filesystem_missing_required_field() -> None:
    raw = {"version": "0.6.0", "overall": "pass"}
    normalized, error = normalize_report(ReportKind.INVENTORY_FILESYSTEM, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_inventory_filesystem_invalid_scanned_entries() -> None:
    raw = {
        "version": "0.6.0",
        "overall": "pass",
        "root": "/tmp",
        "summary": {"scanned_entries": "not-an-int"},
        "issues": [],
        "truncated": False,
    }
    normalized, error = normalize_report(ReportKind.INVENTORY_FILESYSTEM, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "scanned_entries" in error


def test_normalize_logs_parse_missing_required_field() -> None:
    raw = {"version": "0.6.0", "overall": "pass"}
    normalized, error = normalize_report(ReportKind.LOGS_PARSE, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_logs_parse_invalid_summary_fields() -> None:
    raw = {
        "version": "0.6.0",
        "overall": "pass",
        "path": "/var/log/app.log",
        "summary": {"events_emitted": "not-an-int", "malformed_lines": 0},
        "truncated": False,
    }
    normalized, error = normalize_report(ReportKind.LOGS_PARSE, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "invalid summary fields" in error


def test_normalize_logs_analyze_missing_required_field() -> None:
    raw = {"version": "0.6.0", "overall": "pass"}
    normalized, error = normalize_report(ReportKind.LOGS_ANALYZE, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_logs_analyze_invalid_events_parsed() -> None:
    raw = {
        "version": "0.6.0",
        "overall": "pass",
        "path": "/var/log/app.log",
        "summary": {"events_parsed": "not-an-int"},
        "findings": [],
        "truncated": False,
    }
    normalized, error = normalize_report(ReportKind.LOGS_ANALYZE, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "events_parsed" in error


def test_normalize_health_http_missing_required_field() -> None:
    raw = {"version": "0.6.0", "overall": "pass"}
    normalized, error = normalize_report(ReportKind.HEALTH_HTTP, raw, source_path="x")
    assert normalized is None
    assert error is not None


def test_normalize_health_tcp_invalid_summary_fields() -> None:
    raw = {
        "version": "0.6.0",
        "overall": "pass",
        "summary": {"targets": 1, "passed": "not-an-int", "warned": 0, "failed": 0},
    }
    normalized, error = normalize_report(ReportKind.HEALTH_TCP, raw, source_path="x")
    assert normalized is None
    assert error is not None
    assert "invalid summary fields" in error


def test_build_aggregate_report_propagates_normalization_error(tmp_path: Path) -> None:
    raw = {
        "version": "0.6.0",
        "platform": {},
        "python": {},
        "overall": "pass",
        "checks": [{"status": "not-a-status"}],
    }
    path = tmp_path / "bad-doctor.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    report, error = build_aggregate_report([str(path)])
    assert report is None
    assert error is not None
    assert str(path) in error
    assert "invalid checks entry" in error
