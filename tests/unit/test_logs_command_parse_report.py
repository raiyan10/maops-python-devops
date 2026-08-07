"""``build_log_parse_report`` orchestration: ordering, retention caps,
overall/exit semantics.
"""

from __future__ import annotations

import json
from pathlib import Path

from maops_pydevops.commands.logs import build_log_parse_report
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.models import CheckStatus


def _write(path: Path, *lines: str) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_events_in_input_order(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(
        path,
        json.dumps({"message": "first"}),
        json.dumps({"message": "second"}),
        json.dumps({"message": "third"}),
    )
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert error is None
    assert report is not None
    assert [e.message for e in report.events] == ["first", "second", "third"]
    assert [e.line_number for e in report.events] == [1, 2, 3]


def test_issue_ordering_matches_input_order(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, "not json {", json.dumps({"message": "ok"}), "still not json {")
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert [i.line_number for i in report.issues] == [1, 3]


def test_max_events_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, *[json.dumps({"message": f"m{i}"}) for i in range(3)])
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=3,
        redact=True,
    )
    assert report is not None
    assert report.summary.events_parsed == 3
    assert report.summary.events_emitted == 3


def test_max_events_zero_gives_summary_only_report(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "m1"}), json.dumps({"message": "m2"}))
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=0,
        redact=True,
    )
    assert report is not None
    assert report.events == ()
    assert report.summary.events_parsed == 2
    assert report.summary.events_emitted == 0


def test_parsed_versus_emitted_counts_diverge_under_cap(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, *[json.dumps({"message": f"m{i}"}) for i in range(10)])
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=4,
        redact=True,
    )
    assert report is not None
    assert report.summary.events_parsed == 10
    assert report.summary.events_emitted == 4


def test_pass_overall_no_issues_no_truncation(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "clean"}))
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert report.overall is CheckStatus.PASS


def test_warn_overall_with_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "ok"}), "not valid json {")
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert report.overall is CheckStatus.WARN


def test_fail_overall_nonempty_zero_events(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, "not json {", "still not json {")
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.FAIL


def test_empty_file_is_pass(tmp_path: Path) -> None:
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert error is None
    assert report is not None
    assert report.overall is CheckStatus.PASS


def test_blank_only_file_truncated_is_warn(tmp_path: Path) -> None:
    # A file with only blank lines is treated as effectively empty (no
    # non-blank content), but if a hard limit still truncated it before
    # reaching the end, overall must be WARN, not PASS.
    path = tmp_path / "a.log"
    path.write_text("\n\n\n\n\n", encoding="utf-8")
    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=3,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert error is None
    assert report is not None
    assert report.summary.blank_lines == 3
    assert report.truncated is True
    assert report.overall is CheckStatus.WARN


def test_missing_file_returns_error(tmp_path: Path) -> None:
    report, error = build_log_parse_report(
        str(tmp_path / "nope.log"),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is None
    assert error is not None


def test_malformed_issue_detail_never_echoes_raw_line(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    secret_line = '{"message": "ok", "password": "should-not-leak-in-issue-detail"}extra-garbage{'
    _write(path, secret_line)
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    for issue in report.issues:
        assert "should-not-leak-in-issue-detail" not in issue.detail


def test_raw_secret_absent_from_parse_json(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "password=hunter2secretvalue login failed"}))
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert "hunter2secretvalue" not in report.to_json()


def test_overlong_line_becomes_issue_and_summary_count(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_bytes(json.dumps({"message": "ok"}).encode() + b"\n" + b"x" * 500 + b"\n")
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=32,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert report.summary.overlong_lines == 1
    assert any(i.code.value == "overlong_line" for i in report.issues)
    assert report.truncated is True


def test_blank_lines_counted_and_excluded_from_events(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "one"}), "", "", json.dumps({"message": "two"}))
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=True,
    )
    assert report is not None
    assert report.summary.blank_lines == 2
    assert report.summary.events_parsed == 2


def test_no_redact_preserves_secret(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    _write(path, json.dumps({"message": "password=hunter2secretvalue login failed"}))
    report, _error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=False,
    )
    assert report is not None
    assert "hunter2secretvalue" in report.to_json()
    assert report.events[0].redacted is False
