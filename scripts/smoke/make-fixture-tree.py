#!/usr/bin/env python3
"""Create a small, fixed, deterministic directory tree for smoke-testing
``maops-py inventory filesystem``.

Uses only the standard library (``os``/``pathlib``) so ``make
smoke-install`` never depends on, or scans, the real repository tree or
real HOME. The fixture is intentionally tiny: a couple of regular files,
one nested subdirectory, and one symlink.

Usage: make-fixture-tree.py <target_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: make-fixture-tree.py <target_dir>", file=sys.stderr)
        return 2

    target = Path(argv[1])
    target.mkdir(parents=True, exist_ok=True)

    (target / "a.txt").write_text("smoke-test fixture file a\n", encoding="utf-8")
    (target / "b.txt").write_text("smoke-test fixture file b, slightly longer\n", encoding="utf-8")

    nested = target / "nested"
    nested.mkdir(exist_ok=True)
    (nested / "c.txt").write_text("smoke-test fixture file c\n", encoding="utf-8")

    link = target / "link-to-a"
    if not link.exists():
        link.symlink_to(target / "a.txt")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
