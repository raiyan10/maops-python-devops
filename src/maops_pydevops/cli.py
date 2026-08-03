"""Command-line interface: argparse construction and dispatch only.

Command logic lives in ``run_*`` functions, never inside parser
construction. Both the ``maops-py`` console script and
``python -m maops_pydevops`` call :func:`main` directly, so there is no
duplicated command logic between the two entry points.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from maops_pydevops.commands.doctor import build_report
from maops_pydevops.core.models import CheckStatus, OutputFormat
from maops_pydevops.core.output import render_json, render_text
from maops_pydevops.version import get_version

PROG_NAME = "maops-py"

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser. No command logic runs here."""
    parser = argparse.ArgumentParser(
        prog=PROG_NAME,
        description="MAOps Python DevOps Automation Toolkit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the toolkit version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version", help="Show the toolkit version and exit.")

    doctor_parser = subparsers.add_parser("doctor", help="Run read-only environment diagnostics.")
    doctor_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="Output format (default: text).",
    )

    return parser


def run_version() -> int:
    """Print the toolkit version. Always exits 0."""
    print(get_version())
    return EXIT_SUCCESS


def run_doctor(output_format: OutputFormat) -> int:
    """Run doctor checks and render the report.

    Exits 1 if any required check failed, 0 otherwise.
    """
    report = build_report()
    if output_format is OutputFormat.JSON:
        print(render_json(report))
    else:
        print(render_text(report), end="")
    return EXIT_SUCCESS if report.overall is CheckStatus.PASS else EXIT_FAILURE


def _dispatch_version(args: argparse.Namespace) -> int:
    del args
    return run_version()


def _dispatch_doctor(args: argparse.Namespace) -> int:
    return run_doctor(OutputFormat(args.format))


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "version": _dispatch_version,
    "doctor": _dispatch_doctor,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Shared entry point for the console script and ``python -m`` invocation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        if args.version:
            return run_version()
        parser.print_help(sys.stderr)
        return EXIT_USAGE_ERROR

    return _COMMANDS[args.command](args)
