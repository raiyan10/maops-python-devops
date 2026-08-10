"""Rarely-hit error branches of ``core/report_reader.py``: lstat/open
permission and OS errors, ELOOP, fstat-detected races, and post-open
non-regular/oversized detection.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from maops_pydevops.core.report_reader import ReportReadFailureReason, read_report_file


def test_lstat_permission_error_maps_to_permission_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_lstat = os.lstat

    def _raise_permission(target: str, *args: object, **kwargs: object) -> os.stat_result:
        if target == str(path):
            raise PermissionError("denied")
        return real_lstat(target, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", _raise_permission)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.PERMISSION_DENIED


def test_lstat_generic_os_error_maps_to_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_lstat = os.lstat

    def _raise_os_error(target: str, *args: object, **kwargs: object) -> os.stat_result:
        if target == str(path):
            raise OSError(errno.EIO, "simulated I/O error")
        return real_lstat(target, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", _raise_os_error)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.OS_ERROR


def test_open_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_open = os.open

    def _raise_permission(target: str, *args: object, **kwargs: object) -> int:
        if target == str(path):
            raise PermissionError("denied")
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(os, "open", _raise_permission)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.PERMISSION_DENIED


def test_open_eloop_maps_to_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_open = os.open

    def _raise_eloop(target: str, *args: object, **kwargs: object) -> int:
        if target == str(path):
            raise OSError(errno.ELOOP, "simulated ELOOP")
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(os, "open", _raise_eloop)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.IS_SYMLINK


def test_open_generic_os_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_open = os.open

    def _raise_os_error(target: str, *args: object, **kwargs: object) -> int:
        if target == str(path):
            raise OSError(errno.EMFILE, "simulated: too many open files")
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(os, "open", _raise_os_error)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.OS_ERROR


def test_fstat_reports_race_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_fstat = os.fstat

    def _fake_fstat(fd: int) -> os.stat_result:
        real_result = real_fstat(fd)
        fields = list(real_result)
        fields[1] = real_result.st_ino + 999999  # falsify st_ino
        return os.stat_result(fields)

    monkeypatch.setattr(os, "fstat", _fake_fstat)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.RACE_DETECTED


def test_fstat_reports_non_regular_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_fstat = os.fstat

    def _fake_fstat(fd: int) -> os.stat_result:
        real_result = real_fstat(fd)
        fields = list(real_result)
        fields[0] = 0o140000 | 0o600  # S_IFSOCK
        return os.stat_result(fields)

    monkeypatch.setattr(os, "fstat", _fake_fstat)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.NOT_REGULAR_FILE


def test_fstat_os_error_after_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")

    def _raise_on_fstat(fd: int) -> os.stat_result:
        raise OSError(errno.EBADF, "simulated bad descriptor")

    monkeypatch.setattr(os, "fstat", _raise_on_fstat)
    document, reason, detail = read_report_file(str(path))
    assert document is None
    assert reason is ReportReadFailureReason.OS_ERROR


def test_fstat_detects_growth_past_max_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "a.json"
    path.write_text("{}", encoding="utf-8")
    real_fstat = os.fstat

    def _fake_fstat(fd: int) -> os.stat_result:
        real_result = real_fstat(fd)
        fields = list(real_result)
        fields[6] = 999_999_999  # falsify st_size
        return os.stat_result(fields)

    monkeypatch.setattr(os, "fstat", _fake_fstat)
    document, reason, detail = read_report_file(str(path), max_bytes=100)
    assert document is None
    assert reason is ReportReadFailureReason.TOO_LARGE
