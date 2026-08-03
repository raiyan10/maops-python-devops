#!/usr/bin/env python3
"""Verify dist/ contains exactly one wheel, and that it has the expected name.

Used by ``make smoke-install`` to select the wheel to install deterministically,
instead of a glob-and-take-the-first-match. Fails loudly (exit 1) if dist/
contains zero wheels, more than one wheel, or a wheel that doesn't match the
expected release artifact name.

Usage: verify_wheel.py <dist_dir> <expected_wheel_name>
On success, prints the full path to the verified wheel and exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: verify_wheel.py <dist_dir> <expected_wheel_name>", file=sys.stderr)
        return 2

    dist_dir = Path(argv[1])
    expected_name = argv[2]

    wheels = sorted(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        found = [wheel.name for wheel in wheels]
        print(
            f"ERROR: expected exactly 1 wheel in '{dist_dir}', found {len(wheels)}: {found}. "
            "Run 'make build' to produce a clean, single release artifact.",
            file=sys.stderr,
        )
        return 1

    wheel = wheels[0]
    if wheel.name != expected_name:
        print(
            f"ERROR: expected wheel '{expected_name}' but found '{wheel.name}' in "
            f"'{dist_dir}'. This usually means pyproject.toml's version and the built "
            "artifact are out of sync.",
            file=sys.stderr,
        )
        return 1

    print(wheel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
