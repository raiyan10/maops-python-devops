"""Bounded, fd-safe reader for ``maops-py`` JSON report input files.

Mirrors ``core/log_reader.py``'s established fd-safety pattern (``os.lstat``
pre-check, ``O_NOFOLLOW``/``O_CLOEXEC`` open, ``os.fstat()`` dev/inode
verification against the pre-open ``lstat()`` result) rather than reusing
it directly: a report file is a single, small, whole JSON document that
must be fully buffered to parse at all, unlike a log file's unbounded
sequential line stream. Regular files only; never follows a symbolic
link; never writes to, or changes the metadata of, the input file.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from enum import StrEnum

#: A report is a small, structured JSON document -- 5 MiB comfortably
#: covers even a large ``inventory filesystem``/``logs analyze`` report
#: while still bounding worst-case memory use for a hostile input file.
MAX_REPORT_FILE_BYTES = 5_242_880

#: Bounds the number of report files a single ``report aggregate``
#: invocation will ever open.
MAX_REPORT_COUNT = 50


class ReportReadFailureReason(StrEnum):
    """Closed set of reasons a report file could not be read as JSON."""

    NOT_FOUND = "not_found"
    IS_DIRECTORY = "is_directory"
    IS_SYMLINK = "is_symlink"
    NOT_REGULAR_FILE = "not_regular_file"
    PERMISSION_DENIED = "permission_denied"
    RACE_DETECTED = "race_detected"
    TOO_LARGE = "too_large"
    NOT_UTF8 = "not_utf8"
    MALFORMED_JSON = "malformed_json"
    NOT_A_JSON_OBJECT = "not_a_json_object"
    OS_ERROR = "os_error"


_FAILURE_DETAILS: dict[ReportReadFailureReason, str] = {
    ReportReadFailureReason.NOT_FOUND: "path not found",
    ReportReadFailureReason.IS_DIRECTORY: "path is a directory",
    ReportReadFailureReason.IS_SYMLINK: "refusing to read a symbolic link",
    ReportReadFailureReason.NOT_REGULAR_FILE: "not a regular file",
    ReportReadFailureReason.PERMISSION_DENIED: "permission denied",
    ReportReadFailureReason.RACE_DETECTED: "path changed between check and open",
    ReportReadFailureReason.TOO_LARGE: "report file exceeds the maximum allowed size",
    ReportReadFailureReason.NOT_UTF8: "report file is not valid UTF-8",
    ReportReadFailureReason.MALFORMED_JSON: "report file is not valid JSON",
    ReportReadFailureReason.NOT_A_JSON_OBJECT: "report file does not contain a JSON object",
    ReportReadFailureReason.OS_ERROR: "operating system error",
}


def _open_regular_file(path: str) -> tuple[int | None, ReportReadFailureReason | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(path, flags), None, None
    except FileNotFoundError:
        reason = ReportReadFailureReason.NOT_FOUND
        return None, reason, _FAILURE_DETAILS[reason]
    except PermissionError:
        reason = ReportReadFailureReason.PERMISSION_DENIED
        return None, reason, _FAILURE_DETAILS[reason]
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            reason = ReportReadFailureReason.IS_SYMLINK
            return None, reason, _FAILURE_DETAILS[reason]
        return None, ReportReadFailureReason.OS_ERROR, str(exc)


def read_report_file(
    path_arg: str, *, max_bytes: int = MAX_REPORT_FILE_BYTES
) -> tuple[dict[str, object] | None, ReportReadFailureReason | None, str | None]:
    """Validate, open, and parse ``path_arg`` as a bounded JSON object.

    Returns ``(document, None, None)`` on success, or ``(None, reason,
    detail)`` on any failure -- a malformed, oversized, non-UTF-8,
    non-object, symlinked, or non-regular input is always a controlled,
    typed failure. Never raises for adversarial or malformed input; only a
    genuine programming error (not a condition this function's callers can
    supply) would propagate.
    """
    normalized_path = os.path.abspath(path_arg)

    try:
        pre_stat = os.lstat(normalized_path)
    except FileNotFoundError:
        reason = ReportReadFailureReason.NOT_FOUND
        return None, reason, _FAILURE_DETAILS[reason]
    except PermissionError:
        reason = ReportReadFailureReason.PERMISSION_DENIED
        return None, reason, _FAILURE_DETAILS[reason]
    except OSError as exc:
        return None, ReportReadFailureReason.OS_ERROR, str(exc)

    if stat.S_ISLNK(pre_stat.st_mode):
        reason = ReportReadFailureReason.IS_SYMLINK
        return None, reason, _FAILURE_DETAILS[reason]
    if stat.S_ISDIR(pre_stat.st_mode):
        reason = ReportReadFailureReason.IS_DIRECTORY
        return None, reason, _FAILURE_DETAILS[reason]
    if not stat.S_ISREG(pre_stat.st_mode):
        reason = ReportReadFailureReason.NOT_REGULAR_FILE
        return None, reason, _FAILURE_DETAILS[reason]
    if pre_stat.st_size > max_bytes:
        reason = ReportReadFailureReason.TOO_LARGE
        return None, reason, _FAILURE_DETAILS[reason]

    fd, open_failure_reason, open_failure_detail = _open_regular_file(normalized_path)
    if fd is None:
        return None, open_failure_reason, open_failure_detail

    try:
        os.set_inheritable(fd, False)
        post_stat = os.fstat(fd)
        if not stat.S_ISREG(post_stat.st_mode):
            reason = ReportReadFailureReason.NOT_REGULAR_FILE
            return None, reason, _FAILURE_DETAILS[reason]
        # TOCTOU defense: O_NOFOLLOW alone only proves the final open
        # wasn't a symlink, not that it's the same object the earlier
        # lstat() inspected.
        if post_stat.st_dev != pre_stat.st_dev or post_stat.st_ino != pre_stat.st_ino:
            reason = ReportReadFailureReason.RACE_DETECTED
            return None, reason, _FAILURE_DETAILS[reason]
        if post_stat.st_size > max_bytes:
            reason = ReportReadFailureReason.TOO_LARGE
            return None, reason, _FAILURE_DETAILS[reason]

        # Read one byte past the bound so a file that grew between the
        # fstat() above and this read is still caught as TOO_LARGE rather
        # than silently parsed from a truncated read.
        raw = os.read(fd, max_bytes + 1)
    except OSError as exc:
        return None, ReportReadFailureReason.OS_ERROR, str(exc)
    finally:
        os.close(fd)

    if len(raw) > max_bytes:
        reason = ReportReadFailureReason.TOO_LARGE
        return None, reason, _FAILURE_DETAILS[reason]

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        reason = ReportReadFailureReason.NOT_UTF8
        return None, reason, _FAILURE_DETAILS[reason]

    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        reason = ReportReadFailureReason.MALFORMED_JSON
        return None, reason, _FAILURE_DETAILS[reason]

    if not isinstance(document, dict):
        reason = ReportReadFailureReason.NOT_A_JSON_OBJECT
        return None, reason, _FAILURE_DETAILS[reason]

    return document, None, None
