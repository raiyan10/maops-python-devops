"""Bounded, fd-safe sequential binary reader for log files.

The only module that opens and reads file *content* in this package
(``core/filesystem_inventory.py`` only ever calls
``os.lstat``/``os.scandir``/``entry.stat`` metadata, never opens a file).
Opens exactly one regular file, read-only, with pre-open and post-open
symlink/race verification, and reads it in fixed-size, strictly bounded
binary chunks -- never ``mmap``, never a whole-file read. Never writes to
the input file, never changes its mode, ownership, access, or
modification times, never follows a symbolic link, and never imports
``subprocess`` or ``socket``.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

_CHUNK_SIZE = 65536


class LogReadFailureReason(StrEnum):
    """Closed set of reasons a log file could not be opened for reading."""

    NOT_FOUND = "not_found"
    IS_DIRECTORY = "is_directory"
    IS_SYMLINK = "is_symlink"
    NOT_REGULAR_FILE = "not_regular_file"
    PERMISSION_DENIED = "permission_denied"
    RACE_DETECTED = "race_detected"
    OS_ERROR = "os_error"


_FAILURE_DETAILS: dict[LogReadFailureReason, str] = {
    LogReadFailureReason.NOT_FOUND: "path not found",
    LogReadFailureReason.IS_DIRECTORY: "path is a directory",
    LogReadFailureReason.IS_SYMLINK: "refusing to read a symbolic link",
    LogReadFailureReason.NOT_REGULAR_FILE: "not a regular file",
    LogReadFailureReason.PERMISSION_DENIED: "permission denied",
    LogReadFailureReason.RACE_DETECTED: "path changed between check and open",
    LogReadFailureReason.OS_ERROR: "operating system error",
}


@dataclass(frozen=True)
class RawLogLine:
    """One decoded logical line, or a marker for a skipped/truncated line.

    ``overlong`` marks a line longer than ``max_line_bytes`` (content
    dropped before decoding). ``truncated_fragment`` marks the final
    partial physical line left in the buffer when ``max_bytes`` was
    exhausted mid-line -- this fragment is never decoded or treated as
    genuine content; it is a truncation artifact, not a short line.
    """

    line_number: int
    text: str
    overlong: bool
    truncated_fragment: bool = False


def _strip_trailing_cr(data: bytes) -> bytes:
    return data[:-1] if data.endswith(b"\r") else data


@dataclass
class BoundedLogReader:
    """Sequential, bounded binary reader over one already-opened file descriptor.

    Not frozen: internal counters mutate as ``read_lines()`` is consumed.
    Construct only via :func:`open_bounded_log_file`.
    """

    fd: int = field(repr=False)
    path: str
    max_lines: int
    max_bytes: int
    max_line_bytes: int
    bytes_read: int = field(default=0, init=False)
    lines_read: int = field(default=0, init=False)
    overlong_lines_skipped: int = field(default=0, init=False)
    line_limit_reached: bool = field(default=False, init=False)
    byte_limit_reached: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def truncated(self) -> bool:
        """True if any hard limit was hit or any line was dropped as overlong."""
        return self.line_limit_reached or self.byte_limit_reached or self.overlong_lines_skipped > 0

    def close(self) -> None:
        if not self._closed:
            os.close(self.fd)
            self._closed = True

    def __enter__(self) -> BoundedLogReader:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _read_bounded_chunk(self) -> bytes:
        """Read at most the remaining byte budget -- never past it.

        Once the budget is exhausted, a single one-byte probe read
        distinguishes "the file ends exactly at the limit" from "more
        data exists beyond the limit", so ``byte_limit_reached`` reflects
        genuine truncation rather than a coincidental exact-size match.
        The probed byte itself is discarded; reading stops permanently
        once the budget is exhausted regardless of the probe result.
        """
        if self.byte_limit_reached:
            return b""
        remaining = self.max_bytes - self.bytes_read
        if remaining <= 0:
            probe = os.read(self.fd, 1)
            self.byte_limit_reached = len(probe) > 0
            return b""
        chunk = os.read(self.fd, min(_CHUNK_SIZE, remaining))
        self.bytes_read += len(chunk)
        if chunk == b"":
            return b""
        if self.bytes_read >= self.max_bytes:
            probe = os.read(self.fd, 1)
            self.byte_limit_reached = len(probe) > 0
        return chunk

    def _more_data_exists(self, buffer: bytearray) -> bool:
        """Whether unconsumed data remains after stopping at ``max_lines``."""
        if buffer:
            return True
        if self.byte_limit_reached:
            return True
        probe = os.read(self.fd, 1)
        return len(probe) > 0

    def read_lines(self) -> Iterator[RawLogLine]:
        """Yield one :class:`RawLogLine` per logical line, in order.

        Stops deterministically once ``max_lines`` or ``max_bytes`` is
        reached -- no further ``os.read`` calls are made to compute a
        total once a limit fires. Overlong lines (longer than
        ``max_line_bytes`` before a newline is found) are reported with
        ``overlong=True`` and empty ``text``; their content is dropped
        the moment it is known to be overlong and is never buffered or
        decoded.
        """
        buffer = bytearray()
        in_overlong = False
        line_number = 0
        eof = False

        while True:
            while True:
                newline_index = buffer.find(b"\n")
                if newline_index == -1:
                    break
                raw = _strip_trailing_cr(bytes(buffer[:newline_index]))
                del buffer[: newline_index + 1]
                line_number += 1
                self.lines_read += 1
                if len(raw) > self.max_line_bytes:
                    self.overlong_lines_skipped += 1
                    yield RawLogLine(line_number=line_number, text="", overlong=True)
                else:
                    yield RawLogLine(
                        line_number=line_number,
                        text=raw.decode("utf-8", errors="replace"),
                        overlong=False,
                    )
                if self.lines_read >= self.max_lines:
                    self.line_limit_reached = self._more_data_exists(buffer)
                    return

            if not in_overlong and len(buffer) > self.max_line_bytes:
                buffer.clear()
                in_overlong = True

            if eof:
                break

            chunk = self._read_bounded_chunk()
            if chunk == b"":
                eof = True
                continue

            if in_overlong:
                newline_index = chunk.find(b"\n")
                if newline_index == -1:
                    continue
                line_number += 1
                self.lines_read += 1
                self.overlong_lines_skipped += 1
                in_overlong = False
                buffer += chunk[newline_index + 1 :]
                yield RawLogLine(line_number=line_number, text="", overlong=True)
                if self.lines_read >= self.max_lines:
                    self.line_limit_reached = self._more_data_exists(buffer)
                    return
                continue

            buffer += chunk

        if in_overlong:
            line_number += 1
            self.lines_read += 1
            self.overlong_lines_skipped += 1
            yield RawLogLine(line_number=line_number, text="", overlong=True)
        elif buffer:
            line_number += 1
            self.lines_read += 1
            if self.byte_limit_reached:
                # More data existed beyond max_bytes: this trailing buffer
                # is a genuine mid-line truncation artifact, not a valid
                # (if unterminated) final line -- skip it rather than
                # decoding a fragment as if it were complete content.
                yield RawLogLine(
                    line_number=line_number, text="", overlong=False, truncated_fragment=True
                )
            else:
                raw = _strip_trailing_cr(bytes(buffer))
                yield RawLogLine(
                    line_number=line_number,
                    text=raw.decode("utf-8", errors="replace"),
                    overlong=False,
                )


def _open_regular_file(path: str) -> tuple[int | None, LogReadFailureReason | None, str | None]:
    """Open ``path`` read-only with symlink/inheritance/atime hardening.

    ``O_NOATIME`` (Linux-only) requires the caller to own the file or hold
    ``CAP_FOWNER``; if the initial open is refused specifically for that
    reason (``EPERM``), a second attempt is made without it so reading a
    file owned by another user still succeeds -- just without the
    access-time guarantee in that one case.
    """
    base_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    noatime_flag = getattr(os, "O_NOATIME", 0)

    try:
        return os.open(path, base_flags | noatime_flag), None, None
    except FileNotFoundError:
        reason = LogReadFailureReason.NOT_FOUND
        return None, reason, _FAILURE_DETAILS[reason]
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            reason = LogReadFailureReason.IS_SYMLINK
            return None, reason, _FAILURE_DETAILS[reason]
        if not (noatime_flag and exc.errno == errno.EPERM):
            if isinstance(exc, PermissionError):
                reason = LogReadFailureReason.PERMISSION_DENIED
                return None, reason, _FAILURE_DETAILS[reason]
            return None, LogReadFailureReason.OS_ERROR, str(exc)

    try:
        return os.open(path, base_flags), None, None
    except FileNotFoundError:
        reason = LogReadFailureReason.NOT_FOUND
        return None, reason, _FAILURE_DETAILS[reason]
    except PermissionError:
        reason = LogReadFailureReason.PERMISSION_DENIED
        return None, reason, _FAILURE_DETAILS[reason]
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            reason = LogReadFailureReason.IS_SYMLINK
            return None, reason, _FAILURE_DETAILS[reason]
        return None, LogReadFailureReason.OS_ERROR, str(exc)


def open_bounded_log_file(
    path_arg: str,
    *,
    max_lines: int,
    max_bytes: int,
    max_line_bytes: int,
) -> tuple[BoundedLogReader | None, LogReadFailureReason | None, str | None]:
    """Validate, open, and wrap ``path_arg`` for bounded sequential reading.

    Returns ``(reader, None, None)`` on success, or ``(None, reason,
    detail)`` if the file itself cannot be safely opened at all -- this
    is the operational-failure boundary (maps to exit 1 in the CLI). Any
    degraded condition encountered while *reading* content (overlong
    lines, malformed events) is never reported here; it is folded into
    the caller's per-line issue list instead.

    The reported path is ``os.path.abspath(path_arg)`` -- a purely
    lexical (cwd-join, ``.``/``..`` collapse) normalization with no
    filesystem access, deliberately never ``Path.resolve()``, which would
    silently walk through symlink components in parent directories and
    change the reported string away from what the caller supplied.
    """
    normalized_path = os.path.abspath(path_arg)

    try:
        pre_stat = os.lstat(normalized_path)
    except FileNotFoundError:
        reason = LogReadFailureReason.NOT_FOUND
        return None, reason, _FAILURE_DETAILS[reason]
    except PermissionError:
        reason = LogReadFailureReason.PERMISSION_DENIED
        return None, reason, _FAILURE_DETAILS[reason]
    except OSError as exc:
        return None, LogReadFailureReason.OS_ERROR, str(exc)

    if stat.S_ISLNK(pre_stat.st_mode):
        reason = LogReadFailureReason.IS_SYMLINK
        return None, reason, _FAILURE_DETAILS[reason]
    if stat.S_ISDIR(pre_stat.st_mode):
        reason = LogReadFailureReason.IS_DIRECTORY
        return None, reason, _FAILURE_DETAILS[reason]
    if not stat.S_ISREG(pre_stat.st_mode):
        reason = LogReadFailureReason.NOT_REGULAR_FILE
        return None, reason, _FAILURE_DETAILS[reason]

    # O_NOFOLLOW/O_CLOEXEC/O_NOATIME may not exist on every platform (e.g.
    # Windows); _open_regular_file() falls back gracefully via getattr(...,
    # 0). CI only runs ubuntu-latest, but mypy --strict type-checks this
    # file unconditionally.
    fd, open_failure_reason, open_failure_detail = _open_regular_file(normalized_path)
    if fd is None:
        return None, open_failure_reason, open_failure_detail

    try:
        os.set_inheritable(fd, False)
        post_stat = os.fstat(fd)
    except OSError as exc:
        os.close(fd)
        return None, LogReadFailureReason.OS_ERROR, str(exc)

    if not stat.S_ISREG(post_stat.st_mode):
        os.close(fd)
        reason = LogReadFailureReason.NOT_REGULAR_FILE
        return None, reason, _FAILURE_DETAILS[reason]

    # TOCTOU defense: O_NOFOLLOW alone only proves the final open wasn't a
    # symlink, not that it's the same object the earlier lstat() inspected.
    if post_stat.st_dev != pre_stat.st_dev or post_stat.st_ino != pre_stat.st_ino:
        os.close(fd)
        reason = LogReadFailureReason.RACE_DETECTED
        return None, reason, _FAILURE_DETAILS[reason]

    reader = BoundedLogReader(
        fd=fd,
        path=normalized_path,
        max_lines=max_lines,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
    )
    return reader, None, None
