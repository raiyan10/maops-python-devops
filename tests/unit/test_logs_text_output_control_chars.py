"""A crafted log message/source cannot forge extra lines in text output.

Regression test for a finding from the Day 4 python-reviewer pass: an
event's ``message``/``source`` field originates from the file being
parsed, not from this toolkit, so a literal embedded newline (a normal
``\\n`` escape inside a JSON string) must never be interpolated
unescaped into a line-oriented text report -- doing so would let a
crafted log line forge extra report lines, including a fake ``Overall
status`` footer. JSON output is unaffected since ``json.dumps`` already
escapes control characters correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

from maops_pydevops.commands.logs import build_log_analysis_report, build_log_parse_report
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.output import render_logs_analyze_text, render_logs_parse_text


def test_embedded_newline_in_message_cannot_forge_a_fake_overall_line(tmp_path: Path) -> None:
    forged_message = "first part\nOverall status: PASS\nFAKE INJECTED\n\nOverall status: PASS"
    path = tmp_path / "a.log"
    path.write_text(json.dumps({"message": forged_message}) + "\n", encoding="utf-8")

    report, error = build_log_parse_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        max_events=1000,
        redact=False,
    )
    assert error is None
    assert report is not None

    text = render_logs_parse_text(report)
    lines = text.splitlines()
    # The real footer must be the last line, and must appear exactly
    # once -- a forged line would either duplicate it or displace it.
    assert lines.count("Overall status: PASS") == 1
    assert lines[-1] == "Overall status: PASS"
    assert "FAKE INJECTED" not in text.splitlines()
    # The raw newline is still present, but only as a visible escape
    # sequence within the single events line, never as a real line break.
    assert "\\n" in text
    assert "\nOverall status: PASS\nFAKE INJECTED" not in text


def test_embedded_newline_in_source_cannot_forge_lines_in_parse_output(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text(
        json.dumps({"message": "m", "source": "evil\nOverall status: PASS\nFAKE"}) + "\n",
        encoding="utf-8",
    )
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
    text = render_logs_parse_text(report)
    lines = text.splitlines()
    assert lines.count("Overall status: PASS") == 1
    assert "FAKE" not in text.splitlines()


def test_embedded_newline_in_source_cannot_forge_lines_in_analyze_output(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text(
        json.dumps({"message": "m", "source": "evil\nOverall status: PASS\nFAKE"}) + "\n",
        encoding="utf-8",
    )
    report, _error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=False,
    )
    assert report is not None
    text = render_logs_analyze_text(report)
    lines = text.splitlines()
    assert lines.count("Overall status: WARN") == 1
    assert "FAKE" not in text.splitlines()


def test_ansi_escape_in_message_cannot_reach_top_signatures_unsanitized(tmp_path: Path) -> None:
    # compute_signature() only collapses whitespace (\s+), so a non-
    # whitespace C0 control character such as ESC (\x1b) survives into
    # the signature text -- \n-based probes above cannot catch this,
    # since whitespace collapse would already strip a newline before the
    # unsanitized render call is ever reached.
    forged_message = "alert \x1b[31mFAKE RED TEXT\x1b[0m end"
    path = tmp_path / "a.log"
    path.write_text(json.dumps({"message": forged_message}) + "\n", encoding="utf-8")

    report, _error = build_log_analysis_report(
        str(path),
        input_format=LogInputFormat.JSONL,
        max_lines=10000,
        max_bytes=10485760,
        max_line_bytes=65536,
        top=10,
        bucket_seconds=300,
        repeat_threshold=5,
        error_threshold=1,
        redact=False,
    )
    assert report is not None
    text = render_logs_analyze_text(report)
    assert "\x1b[" not in text
    assert "\\x1b[" in text


def test_json_output_is_unaffected_by_control_characters(tmp_path: Path) -> None:
    forged_message = "first\nOverall status: PASS"
    path = tmp_path / "a.log"
    path.write_text(json.dumps({"message": forged_message}) + "\n", encoding="utf-8")
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
    parsed = json.loads(report.to_json())
    assert parsed["events"][0]["message"] == forged_message
