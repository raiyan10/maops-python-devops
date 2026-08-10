"""Bounded, fd-safe reading of ``maops-py`` JSON report input files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from maops_pydevops.core.report_reader import ReportReadFailureReason, read_report_file


def test_valid_report_file_parses(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text('{"version": "0.6.0", "overall": "pass"}', encoding="utf-8")
    document, reason, detail = read_report_file(str(path))
    assert reason is None
    assert detail is None
    assert document == {"version": "0.6.0", "overall": "pass"}


def test_missing_file_is_not_found(tmp_path: Path) -> None:
    document, reason, detail = read_report_file(str(tmp_path / "nope.json"))
    assert document is None
    assert reason is ReportReadFailureReason.NOT_FOUND
    assert detail is not None


def test_directory_is_rejected(tmp_path: Path) -> None:
    document, reason, detail = read_report_file(str(tmp_path))
    assert document is None
    assert reason is ReportReadFailureReason.IS_DIRECTORY


def test_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"overall": "pass"}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    document, reason, detail = read_report_file(str(link))
    assert document is None
    assert reason is ReportReadFailureReason.IS_SYMLINK


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFOs not available on Windows")
def test_fifo_is_rejected(tmp_path: Path) -> None:
    fifo_path = tmp_path / "fifo"
    os.mkfifo(fifo_path)
    document, reason, detail = read_report_file(str(fifo_path))
    assert document is None
    assert reason is ReportReadFailureReason.NOT_REGULAR_FILE


def test_empty_file_is_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.MALFORMED_JSON


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json at all", encoding="utf-8")
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.MALFORMED_JSON


def test_non_object_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.NOT_A_JSON_OBJECT


def test_non_utf8_content_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_encoding.json"
    path.write_bytes(b"\xff\xfe{}")
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.NOT_UTF8


def test_file_size_boundary_exact_limit_accepted(tmp_path: Path) -> None:
    # A document whose serialized length is exactly at the byte limit is
    # accepted -- only content strictly exceeding the limit is rejected.
    document_text = '{"k": "' + ("a" * 40) + '"}'
    max_bytes = len(document_text.encode("utf-8"))
    path = tmp_path / "exact.json"
    path.write_text(document_text, encoding="utf-8")
    document, reason, detail = read_report_file(str(path), max_bytes=max_bytes)
    assert reason is None
    assert document is not None


def test_file_size_boundary_one_byte_over_rejected(tmp_path: Path) -> None:
    document_text = '{"k": "' + ("a" * 40) + '"}'
    max_bytes = len(document_text.encode("utf-8")) - 1
    path = tmp_path / "over.json"
    path.write_text(document_text, encoding="utf-8")
    document, reason, detail = read_report_file(str(path), max_bytes=max_bytes)
    assert document is None
    assert reason is ReportReadFailureReason.TOO_LARGE


def test_oversized_file_rejected_before_open_via_lstat(tmp_path: Path) -> None:
    path = tmp_path / "large.json"
    path.write_text("{" + ("a" * 10000) + "}", encoding="utf-8")
    document, reason, detail = read_report_file(str(path), max_bytes=100)
    assert document is None
    assert reason is ReportReadFailureReason.TOO_LARGE


def test_relative_path_resolved_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rel.json"
    path.write_text('{"overall": "pass"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    document, reason, detail = read_report_file("rel.json")
    assert reason is None
    assert document == {"overall": "pass"}


def test_never_opens_a_socket_special_file(tmp_path: Path) -> None:
    import socket

    sock_path = tmp_path / "socket.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(sock_path))
        document, reason, detail = read_report_file(str(sock_path))
        assert document is None
        assert reason is ReportReadFailureReason.NOT_REGULAR_FILE
    finally:
        server.close()
