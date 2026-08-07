"""Error-handling and rarely-hit branches of ``core/log_reader.py``: the
O_NOATIME fallback, permission/OS-error propagation, fstat-detected
non-regular files, context-manager usage, and multi-chunk overlong lines.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

import maops_pydevops.core.log_reader as log_reader_module
from maops_pydevops.core.log_reader import LogReadFailureReason, open_bounded_log_file

_LIMITS: dict[str, int] = {"max_lines": 1000, "max_bytes": 65536, "max_line_bytes": 32}


def test_context_manager_closes_reader(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is not None
    with reader as opened:
        list(opened.read_lines())
    assert reader._closed is True  # noqa: SLF001


def test_double_close_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is not None
    reader.close()
    reader.close()  # must not raise or double-close the fd


def test_lstat_permission_error_maps_to_permission_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    real_lstat = os.lstat

    def _raise_permission(target: str, *args: object, **kwargs: object) -> os.stat_result:
        if target == str(path):
            raise PermissionError("denied")
        return real_lstat(target, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", _raise_permission)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.PERMISSION_DENIED


def test_lstat_generic_os_error_maps_to_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    real_lstat = os.lstat

    def _raise_os_error(target: str, *args: object, **kwargs: object) -> os.stat_result:
        if target == str(path):
            raise OSError(errno.EIO, "simulated I/O error")
        return real_lstat(target, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", _raise_os_error)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.OS_ERROR


def test_open_noatime_eperm_falls_back_without_noatime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOATIME"):
        pytest.skip("O_NOATIME not available on this platform")

    real_open = os.open
    attempts: list[int] = []

    def _fake_open(target: str, flags: int, *args: object) -> int:
        attempts.append(flags)
        if flags & os.O_NOATIME:
            raise OSError(errno.EPERM, "simulated: O_NOATIME requires ownership")
        return real_open(target, flags & ~os.O_NOATIME, *args)

    monkeypatch.setattr(os, "open", _fake_open)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()
    assert len(attempts) == 2
    assert attempts[0] & os.O_NOATIME
    assert not (attempts[1] & os.O_NOATIME)


def test_open_generic_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")

    def _raise_permission(target: str, flags: int, *args: object) -> int:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "open", _raise_permission)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.PERMISSION_DENIED


def test_open_generic_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")

    def _raise_os_error(target: str, flags: int, *args: object) -> int:
        raise OSError(errno.EMFILE, "simulated: too many open files")

    monkeypatch.setattr(os, "open", _raise_os_error)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.OS_ERROR


def test_open_eloop_after_noatime_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOATIME"):
        pytest.skip("O_NOATIME not available on this platform")

    def _raise_eperm_then_eloop(target: str, flags: int, *args: object) -> int:
        if flags & os.O_NOATIME:
            raise OSError(errno.EPERM, "simulated EPERM")
        raise OSError(errno.ELOOP, "simulated ELOOP on fallback")

    monkeypatch.setattr(os, "open", _raise_eperm_then_eloop)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.IS_SYMLINK


def test_fstat_os_error_after_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")

    def _raise_on_fstat(fd: int) -> os.stat_result:
        raise OSError(errno.EBADF, "simulated bad descriptor")

    monkeypatch.setattr(os, "fstat", _raise_on_fstat)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.OS_ERROR


def test_fstat_reports_non_regular_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    real_fstat = os.fstat
    real_result = real_fstat(os.open(str(path), os.O_RDONLY))

    class _FakeStat:
        st_mode = 0o140644  # S_IFSOCK
        st_dev = real_result.st_dev
        st_ino = real_result.st_ino

    def _fake_fstat(fd: int) -> object:
        return _FakeStat()

    monkeypatch.setattr(os, "fstat", _fake_fstat)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.NOT_REGULAR_FILE


def test_overlong_line_spanning_multiple_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force a small internal chunk size so an overlong line's terminating
    # newline arrives several reads after the buffer already exceeded
    # max_line_bytes -- exercising the "still accumulating, no newline
    # yet" overlong-detection branch and its multi-chunk continuation,
    # not just the single-chunk case.
    monkeypatch.setattr(log_reader_module, "_CHUNK_SIZE", 8)
    path = tmp_path / "a.log"
    path.write_bytes(b"short\n" + b"y" * 100 + b"\n" + b"after\n")
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=1000, max_bytes=1_000_000, max_line_bytes=10
    )
    assert reader is not None
    lines = list(reader.read_lines())
    reader.close()
    assert [line.overlong for line in lines] == [False, True, False]
    assert lines[1].text == ""
    assert reader.overlong_lines_skipped == 1


def test_overlong_line_unterminated_at_eof(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_bytes(b"short\n" + b"z" * 100)  # no trailing newline
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=1000, max_bytes=1_000_000, max_line_bytes=10
    )
    assert reader is not None
    lines = list(reader.read_lines())
    reader.close()
    assert [line.overlong for line in lines] == [False, True]
    assert reader.overlong_lines_skipped == 1
    assert reader.truncated is True


def test_line_limit_reached_while_resolving_a_multichunk_overlong_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader_module, "_CHUNK_SIZE", 8)
    path = tmp_path / "a.log"
    path.write_bytes(b"short\n" + b"y" * 100 + b"\n" + b"never read\n")
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=2, max_bytes=1_000_000, max_line_bytes=10
    )
    assert reader is not None
    lines = list(reader.read_lines())
    reader.close()
    assert [line.overlong for line in lines] == [False, True]
    assert reader.line_limit_reached is True


def test_open_not_found_via_toctou_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # lstat() succeeds (file exists at check time) but the file is
    # deleted before open() runs -- open() itself must still surface a
    # clean NOT_FOUND rather than an uncaught exception.
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")

    def _raise_not_found(target: str, flags: int, *args: object) -> int:
        raise FileNotFoundError("simulated: deleted between check and open")

    monkeypatch.setattr(os, "open", _raise_not_found)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.NOT_FOUND


def test_open_eloop_on_first_attempt_without_noatime_complication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")

    def _raise_eloop(target: str, flags: int, *args: object) -> int:
        raise OSError(errno.ELOOP, "simulated ELOOP on first attempt")

    monkeypatch.setattr(os, "open", _raise_eloop)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.IS_SYMLINK


def test_open_not_found_after_noatime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOATIME"):
        pytest.skip("O_NOATIME not available on this platform")

    def _eperm_then_not_found(target: str, flags: int, *args: object) -> int:
        if flags & os.O_NOATIME:
            raise OSError(errno.EPERM, "simulated EPERM")
        raise FileNotFoundError("simulated: deleted before fallback open")

    monkeypatch.setattr(os, "open", _eperm_then_not_found)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.NOT_FOUND


def test_open_permission_denied_after_noatime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOATIME"):
        pytest.skip("O_NOATIME not available on this platform")

    def _eperm_then_permission_error(target: str, flags: int, *args: object) -> int:
        if flags & os.O_NOATIME:
            raise OSError(errno.EPERM, "simulated EPERM")
        raise PermissionError("simulated: permission denied on fallback open")

    monkeypatch.setattr(os, "open", _eperm_then_permission_error)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.PERMISSION_DENIED


def test_open_generic_os_error_after_noatime_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOATIME"):
        pytest.skip("O_NOATIME not available on this platform")

    def _eperm_then_os_error(target: str, flags: int, *args: object) -> int:
        if flags & os.O_NOATIME:
            raise OSError(errno.EPERM, "simulated EPERM")
        raise OSError(errno.EMFILE, "simulated: too many open files on fallback")

    monkeypatch.setattr(os, "open", _eperm_then_os_error)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.OS_ERROR


def test_line_limit_reached_with_byte_limit_already_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reach max_lines exactly when byte_limit_reached is already True
    # (more data existed but was cut off by the byte cap first) --
    # _more_data_exists() must report True via the byte_limit_reached
    # shortcut without needing to probe the fd again.
    path = tmp_path / "a.log"
    path.write_bytes(b"a\nb\nc\nd\n")
    reader, reason, detail = open_bounded_log_file(
        str(path), max_lines=2, max_bytes=4, max_line_bytes=32
    )
    assert reader is not None
    list(reader.read_lines())
    reader.close()
    assert reader.byte_limit_reached is True
    assert reader.line_limit_reached is True
