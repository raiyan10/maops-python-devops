"""``commands/report.py:write_report_output()`` edge cases not reached via the CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from maops_pydevops.commands.report import write_report_output


def test_refuses_non_regular_target(tmp_path: Path) -> None:
    fifo_path = tmp_path / "fifo"
    os.mkfifo(fifo_path)
    ok, detail = write_report_output(fifo_path, "content", force=True)
    assert ok is False
    assert detail is not None
    assert "not a regular file" in detail


def test_write_failure_cleans_up_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_replace(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", _raise_replace)
    out_path = tmp_path / "out.txt"
    ok, detail = write_report_output(out_path, "content", force=False)
    assert ok is False
    assert detail is not None
    assert "failed to write output file" in detail
    assert not out_path.exists()
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".maops-py-report.")]
    assert leftovers == []


def test_write_success_returns_true_none(tmp_path: Path) -> None:
    out_path = tmp_path / "out.txt"
    ok, detail = write_report_output(out_path, "hello", force=False)
    assert ok is True
    assert detail is None
    assert out_path.read_text(encoding="utf-8") == "hello"
