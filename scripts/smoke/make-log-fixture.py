#!/usr/bin/env python3
"""Create a small, fixed, deterministic log file for smoke-testing
``maops-py logs parse``/``maops-py logs analyze``.

Uses only the standard library (``json``/``pathlib``) so ``make
smoke-install`` never depends on, or reads, a real system log file. The
fixture is intentionally small and includes: valid JSONL lines, a valid
syslog line, a repeated message (to exercise the repeat-threshold
finding), warning and error severities, one embedded secret value (to
verify default redaction removes it), one deliberately malformed line,
and timezone-aware timestamps.

Usage: make-log-fixture.py <target_file>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

#: The synthetic secret this fixture embeds. Never a real credential --
#: used only to verify that default redaction removes it from output.
SMOKE_SECRET_VALUE = "smoke-test-secret-do-not-use-1234567890"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: make-log-fixture.py <target_file>", file=sys.stderr)
        return 2

    target = Path(argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        json.dumps(
            {
                "timestamp": "2026-08-06T04:00:00Z",
                "severity": "error",
                "hostname": "smoke-host",
                "source": "smoke-api",
                "pid": 1001,
                "message": "database connection failed to 10.0.0.5",
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-08-06T04:00:05Z",
                "severity": "error",
                "hostname": "smoke-host",
                "source": "smoke-api",
                "pid": 1001,
                "message": "database connection failed to 10.0.0.6",
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-08-06T04:00:10Z",
                "severity": "warning",
                "hostname": "smoke-host",
                "source": "smoke-api",
                "message": f"password={SMOKE_SECRET_VALUE} login attempt rejected",
            }
        ),
        (
            "<11>2026-08-06T04:00:15Z smoke-host smoke-svc[2002]: "
            "database connection failed to 10.0.0.7"
        ),
        "this line is not any recognized log format at all",
    ]

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
