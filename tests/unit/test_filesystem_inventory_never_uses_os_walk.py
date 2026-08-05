"""The filesystem scanner never uses unrestricted os.walk() or Path.rglob()."""

from pathlib import Path

SRC_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "maops_pydevops"
    / "core"
    / "filesystem_inventory.py"
)


def test_source_never_uses_os_walk_or_unrestricted_rglob() -> None:
    text = SRC_FILE.read_text(encoding="utf-8")
    assert "os.walk" not in text
    assert ".rglob(" not in text
    assert 'glob("**' not in text


def test_source_uses_scandir_for_traversal() -> None:
    text = SRC_FILE.read_text(encoding="utf-8")
    assert "os.scandir" in text
