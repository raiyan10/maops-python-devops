"""File-safety guarantees of ``core/log_reader.py``: rejection rules,
fd verification, and no unwanted filesystem side effects.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from maops_pydevops.core.log_reader import LogReadFailureReason, open_bounded_log_file

_LIMITS: dict[str, int] = {"max_lines": 1000, "max_bytes": 65536, "max_line_bytes": 4096}


def test_regular_file_accepted(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert detail is None
    assert reader is not None
    reader.close()


def test_missing_path_rejected(tmp_path: Path) -> None:
    reader, reason, detail = open_bounded_log_file(str(tmp_path / "nope.log"), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.NOT_FOUND
    assert detail is not None


def test_directory_rejected(tmp_path: Path) -> None:
    reader, reason, detail = open_bounded_log_file(str(tmp_path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.IS_DIRECTORY


def test_symlink_rejected(tmp_path: Path) -> None:
    target = tmp_path / "real.log"
    target.write_text("data\n", encoding="utf-8")
    link = tmp_path / "link.log"
    link.symlink_to(target)
    reader, reason, detail = open_bounded_log_file(str(link), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.IS_SYMLINK


@pytest.mark.skipif(sys.platform.startswith("win"), reason="os.mkfifo is POSIX-only")
def test_fifo_rejected(tmp_path: Path) -> None:
    fifo_path = tmp_path / "fifo"
    os.mkfifo(fifo_path)
    reader, reason, detail = open_bounded_log_file(str(fifo_path), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.NOT_REGULAR_FILE


def test_path_with_spaces_accepted(tmp_path: Path) -> None:
    path = tmp_path / "a file with spaces.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()


def test_unicode_path_accepted(tmp_path: Path) -> None:
    path = tmp_path / "日志-файл-😀.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()


def test_shell_metacharacters_in_path_are_inert(tmp_path: Path) -> None:
    # A path containing shell metacharacters must be treated as a literal
    # filesystem path -- never interpreted, never expanded, never executed.
    name = "log;rm -rf `whoami` $(id) [test] {a,b}.log"
    path = tmp_path / name
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    assert reader.path == os.path.abspath(str(path))
    reader.close()


def test_reported_path_is_lexical_abspath_not_resolved(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    target = sub / "real.log"
    target.write_text("data\n", encoding="utf-8")
    relative = str(sub) + "/../sub/real.log"
    reader, reason, detail = open_bounded_log_file(relative, **_LIMITS)
    assert reason is None
    assert reader is not None
    assert reader.path == os.path.abspath(relative)
    reader.close()


def test_o_nofollow_used_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("O_NOFOLLOW not available on this platform")

    captured_flags: list[int] = []
    real_open = os.open

    def _spy_open(target_path: str, flags: int, *args: object) -> int:
        captured_flags.append(flags)
        return real_open(target_path, flags, *args)

    monkeypatch.setattr(os, "open", _spy_open)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()
    assert any(flags & os.O_NOFOLLOW for flags in captured_flags)


def test_descriptor_verified_with_fstat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    calls: list[int] = []
    real_fstat = os.fstat

    def _spy_fstat(fd: int) -> os.stat_result:
        calls.append(fd)
        return real_fstat(fd)

    monkeypatch.setattr(os, "fstat", _spy_fstat)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()
    assert len(calls) == 1


def test_race_detected_when_file_replaced_between_check_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "a.log"
    original.write_text("hello\n", encoding="utf-8")
    replacement_dir = tmp_path / "replacement_dir"
    replacement_dir.mkdir()

    real_open = os.open

    def _swap_then_open(target_path: str, flags: int, *args: object) -> int:
        # Simulate: something else replaced the regular file with a
        # different regular file between the pre-open lstat() and the
        # actual open() -- verified here by opening a *different* file
        # than the one lstat() inspected, so dev/inode will mismatch.
        other = tmp_path / "swapped.log"
        other.write_text("swapped\n", encoding="utf-8")
        return real_open(str(other), flags, *args)

    monkeypatch.setattr(os, "open", _swap_then_open)
    reader, reason, detail = open_bounded_log_file(str(original), **_LIMITS)
    assert reader is None
    assert reason is LogReadFailureReason.RACE_DETECTED


def test_no_real_home_interaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = tmp_path / "a.log"
    path.write_text("hello\n", encoding="utf-8")
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reason is None
    assert reader is not None
    reader.close()


def test_no_mtime_atime_mode_mutation(tmp_path: Path) -> None:
    path = tmp_path / "a.log"
    path.write_text("hello\nworld\n", encoding="utf-8")
    before = os.stat(path)
    reader, reason, detail = open_bounded_log_file(str(path), **_LIMITS)
    assert reader is not None
    list(reader.read_lines())
    reader.close()
    after = os.stat(path)
    assert before.st_mtime == after.st_mtime
    assert before.st_mode == after.st_mode
    assert stat.S_IMODE(before.st_mode) == stat.S_IMODE(after.st_mode)
