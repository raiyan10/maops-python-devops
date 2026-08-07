"""Bounded-read limit behavior of ``core/log_reader.py``: exact boundaries,
truncation, overlong lines, CRLF, and non-whole-file reading.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maops_pydevops.core.log_reader import open_bounded_log_file


def _read_all(
    path: Path, *, max_lines: int = 10000, max_bytes: int = 10_485_760, max_line_bytes: int = 65536
) -> tuple[list[str], object]:
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=max_lines, max_bytes=max_bytes, max_line_bytes=max_line_bytes
    )
    assert reader is not None, (reason, detail)
    lines = [line.text for line in reader.read_lines() if not line.overlong]
    reader.close()
    return lines, reader


def test_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    lines, reader = _read_all(path)
    assert lines == []
    assert reader.bytes_read == 0
    assert reader.lines_read == 0
    assert reader.truncated is False


def test_one_line(tmp_path: Path) -> None:
    path = tmp_path / "one.log"
    path.write_bytes(b"only line\n")
    lines, reader = _read_all(path)
    assert lines == ["only line"]
    assert reader.lines_read == 1


def test_blank_lines_preserved_as_lines(tmp_path: Path) -> None:
    path = tmp_path / "blanks.log"
    path.write_bytes(b"a\n\n\nb\n")
    lines, reader = _read_all(path)
    assert lines == ["a", "", "", "b"]
    assert reader.lines_read == 4


def test_max_lines_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "exact.log"
    path.write_bytes(b"a\nb\nc\n")
    _lines, reader = _read_all(path, max_lines=3)
    assert reader.lines_read == 3
    assert reader.line_limit_reached is False
    assert reader.truncated is False


def test_max_lines_truncation(tmp_path: Path) -> None:
    path = tmp_path / "over.log"
    path.write_bytes(b"a\nb\nc\nd\n")
    _lines, reader = _read_all(path, max_lines=3)
    assert reader.lines_read == 3
    assert reader.line_limit_reached is True
    assert reader.truncated is True


def test_max_bytes_exact_boundary(tmp_path: Path) -> None:
    content = b"abcde\n"
    path = tmp_path / "exact_bytes.log"
    path.write_bytes(content)
    _lines, reader = _read_all(path, max_bytes=len(content))
    assert reader.byte_limit_reached is False
    assert reader.truncated is False


def test_max_bytes_truncation(tmp_path: Path) -> None:
    content = b"abcde\n"
    path = tmp_path / "over_bytes.log"
    path.write_bytes(content + b"more data here\n")
    _lines, reader = _read_all(path, max_bytes=len(content))
    assert reader.byte_limit_reached is True
    assert reader.truncated is True


def test_max_line_bytes_exact_boundary(tmp_path: Path) -> None:
    line = b"1234567890"  # exactly 10 bytes
    path = tmp_path / "exact_line.log"
    path.write_bytes(line + b"\nafter\n")
    lines, reader = _read_all(path, max_line_bytes=10)
    assert lines == ["1234567890", "after"]
    assert reader.overlong_lines_skipped == 0
    assert reader.truncated is False


def test_overlong_line_is_skipped_and_not_retained(tmp_path: Path) -> None:
    overlong = b"x" * 200
    path = tmp_path / "overlong.log"
    path.write_bytes(b"short\n" + overlong + b"\nafter\n")
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=1000, max_bytes=1_000_000, max_line_bytes=10
    )
    assert reader is not None
    raw_lines = list(reader.read_lines())
    reader.close()
    assert [line.overlong for line in raw_lines] == [False, True, False]
    assert raw_lines[1].text == ""  # overlong content is never retained
    assert reader.overlong_lines_skipped == 1
    assert reader.truncated is True


def test_utf8_replacement_for_invalid_bytes(tmp_path: Path) -> None:
    path = tmp_path / "invalid_utf8.log"
    path.write_bytes(b"good\n" + b"\xff\xfe bad utf8\n")
    lines, _reader = _read_all(path)
    assert lines[0] == "good"
    assert "�" in lines[1]


def test_crlf_line_endings_stripped(tmp_path: Path) -> None:
    path = tmp_path / "crlf.log"
    path.write_bytes(b"line one\r\nline two\r\n")
    lines, _reader = _read_all(path)
    assert lines == ["line one", "line two"]


def test_final_line_without_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "no_final_nl.log"
    path.write_bytes(b"first\nsecond without newline")
    lines, reader = _read_all(path)
    assert lines == ["first", "second without newline"]
    assert reader.lines_read == 2


def test_bytes_read_accounting(tmp_path: Path) -> None:
    content = b"abc\ndef\n"
    path = tmp_path / "count.log"
    path.write_bytes(content)
    _lines, reader = _read_all(path)
    assert reader.bytes_read == len(content)


def test_reader_never_reads_whole_file_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large.log"
    # Bigger than the reader's internal chunk size (65536) so a
    # whole-file read would look different from chunked reads.
    path.write_bytes((b"x" * 100 + b"\n") * 2000)

    import os as os_module

    real_read = os_module.read
    max_requested = 0

    def _spy_read(fd: int, n: int) -> bytes:
        nonlocal max_requested
        max_requested = max(max_requested, n)
        return real_read(fd, n)

    monkeypatch.setattr(os_module, "read", _spy_read)
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=100000, max_bytes=10_000_000, max_line_bytes=65536
    )
    assert reader is not None
    list(reader.read_lines())
    reader.close()
    assert max_requested <= 65536
    assert max_requested < path.stat().st_size


def test_reader_module_never_imports_mmap() -> None:
    import maops_pydevops.core.log_reader as log_reader_module

    source = Path(log_reader_module.__file__).read_text(encoding="utf-8")
    assert "import mmap" not in source
