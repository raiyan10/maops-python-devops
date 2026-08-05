"""The filesystem scanner never opens or reads file content, never hashes."""

import builtins
import hashlib
from pathlib import Path

import pytest

from maops_pydevops.core.filesystem_inventory import build_filesystem_report


def test_scan_never_calls_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.txt").write_text("real content here", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("more content", encoding="utf-8")

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("open() must never be called by the filesystem scanner")

    monkeypatch.setattr(builtins, "open", _fail)
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
    assert report.summary.files == 2


def test_scan_never_calls_path_open_on_scanned_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")
    real_open = Path.open

    def _guard(self: Path, *args: object, **kwargs: object) -> object:
        assert not str(self).startswith(str(tmp_path)), (
            f"filesystem scanner must never open scanned content: {self}"
        )
        return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", _guard)
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None


def test_scan_never_hashes_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.txt").write_text("data", encoding="utf-8")

    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("hashlib must never be used by the filesystem scanner")

    monkeypatch.setattr(hashlib, "sha256", _fail)
    monkeypatch.setattr(hashlib, "md5", _fail)
    report, error = build_filesystem_report(str(tmp_path), max_depth=5, max_entries=100, top=5)
    assert error is None
    assert report is not None
