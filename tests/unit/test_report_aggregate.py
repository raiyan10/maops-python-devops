"""Report-kind detection, normalization, and aggregate assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from maops_pydevops.core.report_aggregate import (
    build_aggregate_report,
    detect_report_kind,
    normalize_report,
)
from maops_pydevops.core.report_models import ReportKind
from maops_pydevops.core.report_reader import MAX_REPORT_COUNT

DOCTOR_JSON: dict[str, object] = {
    "version": "0.6.0",
    "python": {"version": "3.12.0", "executable": "/usr/bin/python3", "supported": True},
    "platform": {
        "system": "Linux",
        "release": "6.8.0",
        "architecture": "x86_64",
        "filesystem_encoding": "utf-8",
    },
    "checks": [
        {"name": "python_version", "status": "pass", "required": True, "detail": "ok"},
        {"name": "git", "status": "warn", "required": False, "detail": "not found"},
    ],
    "overall": "pass",
}

TOOLS_INSPECT_JSON: dict[str, object] = {
    "version": "0.6.0",
    "configuration": {
        "path": "/dev/null",
        "command_timeout_seconds": 10.0,
        "max_output_bytes": 65536,
    },
    "tools": [
        {
            "name": "git",
            "executable": "/usr/bin/git",
            "status": "pass",
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": 5,
            "stdout": "git version 2.0\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "detail": "ok",
        }
    ],
    "overall": "pass",
}

INVENTORY_SYSTEM_JSON: dict[str, object] = {
    "version": "0.6.0",
    "host": {
        "hostname": "myhost",
        "os_family": "Linux",
        "os_release": "6.8.0",
        "os_version": None,
        "machine": "x86_64",
    },
    "distribution": {"id": None, "name": None, "version_id": None, "available": False},
    "python": {"version": "3.12.0", "implementation": "CPython", "executable": "/usr/bin/python3"},
    "cpu": {
        "logical_count": 8,
        "load_average_1m": None,
        "load_average_5m": None,
        "load_average_15m": None,
    },
    "memory": {
        "available": False,
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
        "used_percent": None,
    },
    "uptime": {"available": False, "seconds": None},
    "issues": [{"component": "memory", "status": "warn", "detail": "unavailable"}],
    "overall": "warn",
}

INVENTORY_FILESYSTEM_JSON: dict[str, object] = {
    "version": "0.6.0",
    "root": "/home/user/project",
    "options": {
        "max_depth": 2,
        "max_entries": 10000,
        "top": 10,
        "follow_symlinks": False,
        "same_filesystem": True,
    },
    "summary": {
        "scanned_entries": 3,
        "directories": 1,
        "files": 2,
        "symlinks": 0,
        "other": 0,
        "total_file_bytes": 100,
        "skipped_entries": 0,
        "inaccessible_entries": 0,
        "different_filesystem_entries": 0,
    },
    "largest_files": [],
    "issues": [],
    "max_depth_reached": False,
    "truncated": False,
    "overall": "pass",
}

LOGS_PARSE_JSON: dict[str, object] = {
    "version": "0.6.0",
    "path": "/var/log/app.log",
    "options": {
        "input_format": "auto",
        "max_lines": 10000,
        "max_bytes": 10485760,
        "max_line_bytes": 65536,
        "max_events": 1000,
        "redact": True,
    },
    "summary": {
        "bytes_read": 10,
        "lines_read": 1,
        "blank_lines": 0,
        "events_parsed": 1,
        "events_emitted": 1,
        "malformed_lines": 0,
        "overlong_lines": 0,
    },
    "events": [],
    "issues": [],
    "line_limit_reached": False,
    "byte_limit_reached": False,
    "truncated": False,
    "overall": "pass",
}

LOGS_ANALYZE_JSON: dict[str, object] = {
    "version": "0.6.0",
    "path": "/var/log/app.log",
    "options": {
        "input_format": "auto",
        "max_lines": 10000,
        "max_bytes": 10485760,
        "max_line_bytes": 65536,
        "top": 10,
        "bucket_seconds": 300,
        "repeat_threshold": 5,
        "error_threshold": 1,
        "redact": True,
    },
    "summary": {
        "bytes_read": 10,
        "lines_read": 1,
        "events_parsed": 1,
        "malformed_lines": 0,
        "overlong_lines": 0,
    },
    "severity_counts": {},
    "source_counts": [],
    "top_signatures": [],
    "time": {
        "timestamped_events": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "out_of_order_events": 0,
        "bucket_seconds": 300,
        "peak_bucket_start": None,
        "peak_bucket_count": 0,
    },
    "findings": [{"code": "error_volume", "status": "fail", "detail": "too many errors"}],
    "issues": [],
    "line_limit_reached": False,
    "byte_limit_reached": False,
    "truncated": False,
    "overall": "fail",
}

HEALTH_HTTP_JSON: dict[str, object] = {
    "version": "0.6.0",
    "protocol": "http",
    "options": {
        "method": "GET",
        "expected_status_min": 200,
        "expected_status_max": 399,
        "timeout_seconds": 3.0,
        "retries": 1,
        "retry_delay_seconds": 0.25,
        "workers": 4,
        "follow_redirects": False,
        "tls_verify": True,
    },
    "summary": {"targets": 1, "passed": 1, "warned": 0, "failed": 0, "attempts": 1},
    "results": [],
    "overall": "pass",
}

HEALTH_TCP_JSON: dict[str, object] = {
    "version": "0.6.0",
    "protocol": "tcp",
    "options": {"timeout_seconds": 3.0, "retries": 1, "retry_delay_seconds": 0.25, "workers": 4},
    "summary": {"targets": 1, "passed": 0, "warned": 0, "failed": 1, "attempts": 2},
    "results": [],
    "overall": "fail",
}


@pytest.mark.parametrize(
    "raw,expected_kind",
    [
        (DOCTOR_JSON, ReportKind.DOCTOR),
        (TOOLS_INSPECT_JSON, ReportKind.TOOLS_INSPECT),
        (INVENTORY_SYSTEM_JSON, ReportKind.INVENTORY_SYSTEM),
        (INVENTORY_FILESYSTEM_JSON, ReportKind.INVENTORY_FILESYSTEM),
        (LOGS_PARSE_JSON, ReportKind.LOGS_PARSE),
        (LOGS_ANALYZE_JSON, ReportKind.LOGS_ANALYZE),
        (HEALTH_HTTP_JSON, ReportKind.HEALTH_HTTP),
        (HEALTH_TCP_JSON, ReportKind.HEALTH_TCP),
    ],
)
def test_detect_report_kind(raw: dict[str, object], expected_kind: ReportKind) -> None:
    assert detect_report_kind(raw) is expected_kind


def test_detect_unrecognized_object_returns_none() -> None:
    assert detect_report_kind({"foo": "bar"}) is None


def test_detect_health_with_unknown_protocol_returns_none() -> None:
    raw = dict(HEALTH_HTTP_JSON)
    raw["protocol"] = "quic"
    assert detect_report_kind(raw) is None


@pytest.mark.parametrize(
    "raw,expected_kind",
    [
        (DOCTOR_JSON, ReportKind.DOCTOR),
        (TOOLS_INSPECT_JSON, ReportKind.TOOLS_INSPECT),
        (INVENTORY_SYSTEM_JSON, ReportKind.INVENTORY_SYSTEM),
        (INVENTORY_FILESYSTEM_JSON, ReportKind.INVENTORY_FILESYSTEM),
        (LOGS_PARSE_JSON, ReportKind.LOGS_PARSE),
        (LOGS_ANALYZE_JSON, ReportKind.LOGS_ANALYZE),
        (HEALTH_HTTP_JSON, ReportKind.HEALTH_HTTP),
        (HEALTH_TCP_JSON, ReportKind.HEALTH_TCP),
    ],
)
def test_normalize_report_never_embeds_full_input(
    raw: dict[str, object], expected_kind: ReportKind
) -> None:
    normalized, error = normalize_report(expected_kind, raw, source_path="x.json")
    assert error is None
    assert normalized is not None
    assert normalized.kind is expected_kind
    assert normalized.source_version == "0.6.0"
    # The normalized form must be small and typed -- never a copy of the
    # entire input document's nested detail (a specific check name, a
    # tool's captured stdout, a finding's freeform detail text, etc.),
    # even though a few small identifying fields (hostname, root, path)
    # are deliberately kept as summary metrics.
    rendered = str(normalized.to_dict())
    for forbidden in (
        "python_version",  # doctor: a specific check name
        "git version 2.0",  # tools_inspect: a tool's captured stdout
        "too many errors",  # logs_analyze: a finding's freeform detail
    ):
        assert forbidden not in rendered, (
            f"{forbidden!r} leaked into normalized {expected_kind.value}"
        )


def test_normalize_doctor_status_and_metrics() -> None:
    normalized, error = normalize_report(ReportKind.DOCTOR, DOCTOR_JSON, source_path="d.json")
    assert error is None
    assert normalized is not None
    assert normalized.status.value == "pass"
    values = {m.label: m.value for m in normalized.metrics}
    assert values["checks_total"] == "2"
    assert values["checks_pass"] == "1"
    assert values["checks_warn"] == "1"


def test_normalize_logs_analyze_fail_status() -> None:
    normalized, error = normalize_report(
        ReportKind.LOGS_ANALYZE, LOGS_ANALYZE_JSON, source_path="a.json"
    )
    assert error is None
    assert normalized is not None
    assert normalized.status.value == "fail"


def test_normalize_malformed_report_missing_required_field() -> None:
    raw = dict(DOCTOR_JSON)
    del raw["overall"]
    normalized, error = normalize_report(ReportKind.DOCTOR, raw, source_path="d.json")
    assert normalized is None
    assert error is not None


def test_normalize_malformed_report_wrong_field_type() -> None:
    raw = dict(DOCTOR_JSON)
    raw["checks"] = "not-a-list"
    normalized, error = normalize_report(ReportKind.DOCTOR, raw, source_path="d.json")
    assert normalized is None
    assert error is not None


def _write_json(path: Path, data: dict[str, object]) -> str:
    import json

    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_build_aggregate_single_report(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "doctor.json", DOCTOR_JSON)
    report, error = build_aggregate_report([path])
    assert error is None
    assert report is not None
    assert report.summary.reports == 1
    assert report.overall.value == "pass"


def test_build_aggregate_multiple_reports_deterministic_order(tmp_path: Path) -> None:
    doctor_path = _write_json(tmp_path / "doctor.json", DOCTOR_JSON)
    tools_path = _write_json(tmp_path / "tools.json", TOOLS_INSPECT_JSON)
    sysinv_path = _write_json(tmp_path / "sysinv.json", INVENTORY_SYSTEM_JSON)

    report, error = build_aggregate_report([sysinv_path, doctor_path, tools_path])
    assert error is None
    assert report is not None
    assert [normalized.source_path for normalized in report.reports] == [
        sysinv_path,
        doctor_path,
        tools_path,
    ]


def test_build_aggregate_mixed_pass_warn_fail_overall(tmp_path: Path) -> None:
    pass_path = _write_json(tmp_path / "doctor.json", DOCTOR_JSON)
    warn_path = _write_json(tmp_path / "sysinv.json", INVENTORY_SYSTEM_JSON)
    fail_path = _write_json(tmp_path / "logsan.json", LOGS_ANALYZE_JSON)

    report, error = build_aggregate_report([pass_path, warn_path, fail_path])
    assert error is None
    assert report is not None
    assert report.overall.value == "fail"
    assert report.summary.pass_count == 1
    assert report.summary.warn_count == 1
    assert report.summary.fail_count == 1


def test_build_aggregate_all_pass_is_overall_pass(tmp_path: Path) -> None:
    path1 = _write_json(tmp_path / "a.json", DOCTOR_JSON)
    path2 = _write_json(tmp_path / "b.json", TOOLS_INSPECT_JSON)
    report, error = build_aggregate_report([path1, path2])
    assert error is None
    assert report is not None
    assert report.overall.value == "pass"


def test_build_aggregate_warn_no_fail_is_overall_warn(tmp_path: Path) -> None:
    path1 = _write_json(tmp_path / "a.json", DOCTOR_JSON)
    path2 = _write_json(tmp_path / "b.json", INVENTORY_SYSTEM_JSON)
    report, error = build_aggregate_report([path1, path2])
    assert error is None
    assert report is not None
    assert report.overall.value == "warn"


def test_build_aggregate_malformed_json_is_validation_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    report, error = build_aggregate_report([str(path)])
    assert report is None
    assert error is not None
    assert str(path) in error


def test_build_aggregate_unsupported_type_is_validation_failure(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "unsupported.json", {"foo": "bar"})
    report, error = build_aggregate_report([path])
    assert report is None
    assert error is not None
    assert "unsupported" in error.lower()


def test_build_aggregate_empty_file_is_validation_failure(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    report, error = build_aggregate_report([str(path)])
    assert report is None
    assert error is not None


def test_build_aggregate_nonexistent_file_is_validation_failure(tmp_path: Path) -> None:
    report, error = build_aggregate_report([str(tmp_path / "nope.json")])
    assert report is None
    assert error is not None


def test_build_aggregate_symlink_input_is_validation_failure(tmp_path: Path) -> None:
    target = _write_json(tmp_path / "target.json", DOCTOR_JSON)
    link = tmp_path / "link.json"
    link.symlink_to(Path(target))
    report, error = build_aggregate_report([str(link)])
    assert report is None
    assert error is not None


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX FIFOs not available on Windows")
def test_build_aggregate_non_regular_input_is_validation_failure(tmp_path: Path) -> None:
    import os

    fifo_path = tmp_path / "fifo"
    os.mkfifo(fifo_path)
    report, error = build_aggregate_report([str(fifo_path)])
    assert report is None
    assert error is not None


def test_build_aggregate_zero_reports_is_boundary_error() -> None:
    report, error = build_aggregate_report([])
    assert report is None
    assert error is not None
    assert "got 0" in error


def test_build_aggregate_report_count_boundary_accepts_max(tmp_path: Path) -> None:
    paths = [_write_json(tmp_path / f"r{i}.json", DOCTOR_JSON) for i in range(3)]
    report, error = build_aggregate_report(paths, max_reports=3)
    assert error is None
    assert report is not None
    assert report.summary.reports == 3


def test_build_aggregate_report_count_boundary_rejects_over_max(tmp_path: Path) -> None:
    paths = [_write_json(tmp_path / f"r{i}.json", DOCTOR_JSON) for i in range(4)]
    report, error = build_aggregate_report(paths, max_reports=3)
    assert report is None
    assert error is not None
    assert "got 4" in error


def test_build_aggregate_report_count_boundary_accepts_real_default_max(
    tmp_path: Path,
) -> None:
    # The real production MAX_REPORT_COUNT boundary (no injected
    # max_reports override) -- proves the actual compiled-in default, not
    # just the generic bound-check logic (Day 6 test-review L-3).
    paths = [_write_json(tmp_path / f"r{i}.json", DOCTOR_JSON) for i in range(MAX_REPORT_COUNT)]
    report, error = build_aggregate_report(paths)
    assert error is None
    assert report is not None
    assert report.summary.reports == MAX_REPORT_COUNT


def test_build_aggregate_report_count_boundary_rejects_real_default_max_plus_one(
    tmp_path: Path,
) -> None:
    paths = [_write_json(tmp_path / f"r{i}.json", DOCTOR_JSON) for i in range(MAX_REPORT_COUNT + 1)]
    report, error = build_aggregate_report(paths)
    assert report is None
    assert error is not None
    assert f"got {MAX_REPORT_COUNT + 1}" in error


def test_build_aggregate_file_size_boundary(tmp_path: Path) -> None:
    import json

    path = tmp_path / "big.json"
    path.write_text(json.dumps(DOCTOR_JSON), encoding="utf-8")
    too_small = len(json.dumps(DOCTOR_JSON).encode("utf-8")) - 1
    report, error = build_aggregate_report([str(path)], max_file_bytes=too_small)
    assert report is None
    assert error is not None


def test_build_aggregate_never_raises_traceback_on_malformed_input(tmp_path: Path) -> None:
    # A malformed report must always be a controlled (report, error) tuple
    # -- never an uncaught exception.
    path = tmp_path / "garbage.json"
    path.write_bytes(b"\x00\x01\x02not-json")
    report, error = build_aggregate_report([str(path)])
    assert report is None
    assert isinstance(error, str)
