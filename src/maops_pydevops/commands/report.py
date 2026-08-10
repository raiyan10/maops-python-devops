"""CLI-facing orchestration for ``maops-py report aggregate``.

Real orchestration lives here (validate report count -> read/detect/
normalize every input -> assemble a frozen aggregate) via
:mod:`maops_pydevops.core.report_aggregate`, plus the secure atomic
``--output`` write path shared with ``commands/workflow.py``'s
``workflow run``.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path

from maops_pydevops.core.report_aggregate import build_aggregate_report
from maops_pydevops.core.report_models import AggregateReport

__all__ = ["build_aggregate_report", "AggregateReport", "write_report_output"]


def write_report_output(path: Path, content: str, *, force: bool) -> tuple[bool, str | None]:
    """Atomically write ``content`` to ``path``, mode ``0600``.

    Returns ``(True, None)`` on success or ``(False, detail)`` on any
    refusal or failure. Never creates the parent directory (it must
    already exist), never follows a symbolic link at ``path`` (with or
    without ``force``), and never leaves a temporary file behind on
    failure. Shared verbatim by ``commands/workflow.py``'s ``workflow
    run --output``.
    """
    parent = path.parent
    if not parent.is_dir():
        return False, f"parent directory does not exist: {parent}"

    try:
        target_stat = os.lstat(path)
    except FileNotFoundError:
        target_stat = None

    if target_stat is not None:
        if stat.S_ISLNK(target_stat.st_mode):
            return False, "refusing to write through a symbolic link, even with --force"
        if not stat.S_ISREG(target_stat.st_mode):
            return False, "target exists and is not a regular file"
        if not force:
            return False, "output file already exists; use --force to overwrite"

    fd: int | None = None
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), prefix=".maops-py-report.", suffix=".tmp")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    except OSError as exc:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
        return False, f"failed to write output file: {exc}"

    return True, None


def build_report_aggregate(paths: Sequence[str]) -> tuple[AggregateReport | None, str | None]:
    """Thin CLI-facing wrapper around :func:`build_aggregate_report`."""
    return build_aggregate_report(paths)
