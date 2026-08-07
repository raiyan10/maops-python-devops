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
from pathlib import Path

from maops_pydevops.commands.config import (
    build_show_report,
    get_config_path,
    init_config,
    validate_config,
)
from maops_pydevops.commands.doctor import build_report
from maops_pydevops.commands.inventory import build_filesystem_report, build_system_report
from maops_pydevops.commands.logs import build_log_analysis_report, build_log_parse_report
from maops_pydevops.commands.tools import TOOL_ALLOWLIST, build_inspect_report
from maops_pydevops.core.config import resolve_effective_config
from maops_pydevops.core.config_models import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MIN_COMMAND_TIMEOUT_SECONDS,
    ConfigFileStatus,
    ConfigInitStatus,
    is_valid_command_timeout_seconds,
)
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.models import CheckStatus, OutputFormat
from maops_pydevops.core.output import (
    render_config_show_json,
    render_config_show_text,
    render_inventory_filesystem_json,
    render_inventory_filesystem_text,
    render_inventory_system_json,
    render_inventory_system_text,
    render_json,
    render_logs_analyze_json,
    render_logs_analyze_text,
    render_logs_parse_json,
    render_logs_parse_text,
    render_text,
    render_tools_inspect_json,
    render_tools_inspect_text,
)
from maops_pydevops.version import get_version

PROG_NAME = "maops-py"

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE_ERROR = 2

_ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(name for name, _ in TOOL_ALLOWLIST)


def _parse_timeout_seconds(raw: str) -> float:
    """argparse ``type=`` callback: parse and range-check a ``--timeout`` value."""
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid timeout value: {raw!r}") from exc
    if not is_valid_command_timeout_seconds(value):
        raise argparse.ArgumentTypeError(
            f"timeout must be greater than {MIN_COMMAND_TIMEOUT_SECONDS} "
            f"and at most {MAX_COMMAND_TIMEOUT_SECONDS}"
        )
    return value


def _parse_bounded_int(raw: str, *, minimum: int, maximum: int, label: str) -> int:
    """argparse ``type=`` callback: parse and range-check a bounded integer value."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{label} must be an integer between {minimum} and {maximum}"
        ) from exc
    if not (minimum <= value <= maximum):
        raise argparse.ArgumentTypeError(
            f"{label} must be an integer between {minimum} and {maximum}"
        )
    return value


def _parse_max_depth(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=0, maximum=64, label="--max-depth")


def _parse_max_entries(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=1, maximum=1_000_000, label="--max-entries")


def _parse_top(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=0, maximum=100, label="--top")


def _parse_max_lines(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=1, maximum=1_000_000, label="--max-lines")


def _parse_max_bytes(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=1024, maximum=104_857_600, label="--max-bytes")


def _parse_max_line_bytes(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=256, maximum=1_048_576, label="--max-line-bytes")


def _parse_max_events(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=0, maximum=10_000, label="--max-events")


def _parse_bucket_seconds(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=1, maximum=86_400, label="--bucket-seconds")


def _parse_repeat_threshold(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=2, maximum=1_000_000, label="--repeat-threshold")


def _parse_error_threshold(raw: str) -> int:
    return _parse_bounded_int(raw, minimum=1, maximum=1_000_000, label="--error-threshold")


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

    config_parser = subparsers.add_parser("config", help="Manage maops-py configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_subparsers.add_parser("path", help="Print the selected configuration file path.")

    config_init_parser = config_subparsers.add_parser(
        "init", help="Create a documented configuration template."
    )
    config_init_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing regular configuration file.",
    )

    config_validate_parser = config_subparsers.add_parser(
        "validate", help="Validate a configuration file."
    )
    config_validate_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Configuration file to validate (default: the selected path).",
    )

    config_show_parser = config_subparsers.add_parser(
        "show", help="Show effective configuration and sources."
    )
    config_show_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=None,
        help="Output format (default: effective output_format).",
    )

    tools_parser = subparsers.add_parser("tools", help="Read-only external tool inspection.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_inspect_parser = tools_subparsers.add_parser(
        "inspect", help="Inspect allowlisted DevOps tool versions."
    )
    tools_inspect_parser.add_argument(
        "tool",
        nargs="*",
        help="Tools to inspect (default: all supported tools).",
    )
    tools_inspect_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=None,
        help="Output format (default: effective output_format).",
    )
    tools_inspect_parser.add_argument(
        "--timeout",
        type=_parse_timeout_seconds,
        default=None,
        help="Per-tool timeout in seconds (default: effective command_timeout_seconds).",
    )

    inventory_parser = subparsers.add_parser(
        "inventory", help="Read-only system and filesystem inventory."
    )
    inventory_subparsers = inventory_parser.add_subparsers(dest="inventory_command", required=True)

    inventory_system_parser = inventory_subparsers.add_parser(
        "system",
        help=(
            "Report host, OS, CPU, memory, and uptime facts. Always exits 0 unless a "
            "report cannot be built at all; see 'overall' in the report for "
            "degraded-data warnings."
        ),
    )
    inventory_system_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="Output format (default: text).",
    )

    inventory_filesystem_parser = inventory_subparsers.add_parser(
        "filesystem", help="Report a bounded filesystem tree summary."
    )
    inventory_filesystem_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Root path to scan (default: current working directory).",
    )
    inventory_filesystem_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="Output format (default: text).",
    )
    inventory_filesystem_parser.add_argument(
        "--max-depth",
        type=_parse_max_depth,
        default=2,
        help="Maximum traversal depth, 0-64 (default: 2).",
    )
    inventory_filesystem_parser.add_argument(
        "--max-entries",
        type=_parse_max_entries,
        default=10000,
        help="Maximum entries to scan, 1-1000000 (default: 10000).",
    )
    inventory_filesystem_parser.add_argument(
        "--top",
        type=_parse_top,
        default=10,
        help="Number of largest files to report, 0-100 (default: 10).",
    )

    logs_parser = subparsers.add_parser(
        "logs", help="Bounded, structured log parsing and deterministic analysis."
    )
    logs_subparsers = logs_parser.add_subparsers(dest="logs_command", required=True)

    logs_parse_parser = logs_subparsers.add_parser(
        "parse", help="Parse a log file into structured events."
    )
    logs_parse_parser.add_argument("path", help="Log file to parse.")
    logs_parse_parser.add_argument(
        "--input-format",
        choices=[fmt.value for fmt in LogInputFormat],
        default=LogInputFormat.AUTO.value,
        help="Input format (default: auto).",
    )
    logs_parse_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=None,
        help="Output format (default: effective output_format).",
    )
    logs_parse_parser.add_argument(
        "--max-lines",
        type=_parse_max_lines,
        default=10000,
        help="Maximum lines to read, 1-1000000 (default: 10000).",
    )
    logs_parse_parser.add_argument(
        "--max-bytes",
        type=_parse_max_bytes,
        default=10485760,
        help="Maximum bytes to read, 1024-104857600 (default: 10485760).",
    )
    logs_parse_parser.add_argument(
        "--max-line-bytes",
        type=_parse_max_line_bytes,
        default=65536,
        help="Maximum bytes per line, 256-1048576 (default: 65536).",
    )
    logs_parse_parser.add_argument(
        "--max-events",
        type=_parse_max_events,
        default=1000,
        help="Maximum events retained in the report, 0-10000 (default: 1000).",
    )
    logs_parse_parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable default secret redaction (sensitive values may be displayed and stored).",
    )

    logs_analyze_parser = logs_subparsers.add_parser(
        "analyze", help="Aggregate deterministic operational signal from a log file."
    )
    logs_analyze_parser.add_argument("path", help="Log file to analyze.")
    logs_analyze_parser.add_argument(
        "--input-format",
        choices=[fmt.value for fmt in LogInputFormat],
        default=LogInputFormat.AUTO.value,
        help="Input format (default: auto).",
    )
    logs_analyze_parser.add_argument(
        "--format",
        choices=[fmt.value for fmt in OutputFormat],
        default=None,
        help="Output format (default: effective output_format).",
    )
    logs_analyze_parser.add_argument(
        "--max-lines",
        type=_parse_max_lines,
        default=10000,
        help="Maximum lines to read, 1-1000000 (default: 10000).",
    )
    logs_analyze_parser.add_argument(
        "--max-bytes",
        type=_parse_max_bytes,
        default=10485760,
        help="Maximum bytes to read, 1024-104857600 (default: 10485760).",
    )
    logs_analyze_parser.add_argument(
        "--max-line-bytes",
        type=_parse_max_line_bytes,
        default=65536,
        help="Maximum bytes per line, 256-1048576 (default: 65536).",
    )
    logs_analyze_parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable default secret redaction (sensitive values may be displayed and stored).",
    )
    logs_analyze_parser.add_argument(
        "--top",
        type=_parse_top,
        default=10,
        help="Number of top signatures/sources to report, 0-100 (default: 10).",
    )
    logs_analyze_parser.add_argument(
        "--bucket-seconds",
        type=_parse_bucket_seconds,
        default=300,
        help="Fixed time-bucket width in seconds, 1-86400 (default: 300).",
    )
    logs_analyze_parser.add_argument(
        "--repeat-threshold",
        type=_parse_repeat_threshold,
        default=5,
        help="Signature repeat count that triggers a finding, 2-1000000 (default: 5).",
    )
    logs_analyze_parser.add_argument(
        "--error-threshold",
        type=_parse_error_threshold,
        default=1,
        help="Error-volume count that triggers a finding, 1-1000000 (default: 1).",
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


def run_config_path() -> int:
    """Print the selected configuration file path. Creates nothing."""
    print(get_config_path())
    return EXIT_SUCCESS


def run_config_init(*, force: bool) -> int:
    """Create a documented configuration template at the selected path."""
    path = get_config_path()
    result = init_config(path, force=force)
    if result.status is ConfigInitStatus.CREATED:
        print(result.detail)
        return EXIT_SUCCESS
    print(f"Error: {result.detail}", file=sys.stderr)
    return EXIT_FAILURE


def run_config_validate(path_arg: str | None) -> int:
    """Validate a configuration file. Exits 1 if missing, malformed, or invalid."""
    path = Path(path_arg) if path_arg is not None else None
    status, error, resolved_path = validate_config(path)
    if status is ConfigFileStatus.VALID:
        print(f"{resolved_path}: valid")
        return EXIT_SUCCESS
    detail = error if error is not None else f"configuration file {status.value}"
    print(f"Error: {resolved_path}: {detail}", file=sys.stderr)
    return EXIT_FAILURE


def run_config_show(format_arg: str | None) -> int:
    """Show effective configuration and sources. Exits 1 on an invalid config."""
    report, error = build_show_report()
    if report is None:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_FAILURE

    if format_arg is not None:
        output_format = OutputFormat(format_arg)
    else:
        output_format = report.values.output_format
    if output_format is OutputFormat.JSON:
        print(render_config_show_json(report))
    else:
        print(render_config_show_text(report), end="")
    return EXIT_SUCCESS


def run_tools_inspect(
    tool_names: Sequence[str], format_arg: str | None, timeout_arg: float | None
) -> int:
    """Inspect allowlisted DevOps tool versions.

    Exits 2 if any requested tool name is not allowlisted, 1 on overall
    warn or fail, 0 on overall pass. Tool-name validation is performed
    here rather than via argparse ``choices=`` because ``choices=`` on a
    zero-or-more positional produces version-dependent argparse behavior
    when no tool names are supplied at all: Python 3.11's argparse raises
    ``ArgumentError: invalid choice: []`` in that case, while 3.12 does
    not (CHANGELOG.md's [0.2.0] "Fixed" entry has the full explanation).
    """
    unsupported = [name for name in tool_names if name not in _ALLOWED_TOOL_NAMES]
    if unsupported:
        allowed = ", ".join(sorted(_ALLOWED_TOOL_NAMES))
        print(
            f"Error: unsupported tool name(s): {', '.join(unsupported)} (choose from {allowed})",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    resolution = resolve_effective_config(cli_command_timeout_seconds=timeout_arg)
    if resolution.config is None:
        print(f"Error: {resolution.error}", file=sys.stderr)
        return EXIT_FAILURE

    report = build_inspect_report(
        tool_names=tool_names,
        version=get_version(),
        timeout_seconds=resolution.config.command_timeout_seconds,
        max_output_bytes=resolution.config.max_output_bytes,
        config_path=resolution.path,
    )

    if format_arg is not None:
        output_format = OutputFormat(format_arg)
    else:
        output_format = resolution.config.output_format
    if output_format is OutputFormat.JSON:
        print(render_tools_inspect_json(report))
    else:
        print(render_tools_inspect_text(report), end="")
    return EXIT_SUCCESS if report.overall is CheckStatus.PASS else EXIT_FAILURE


def run_inventory_system(format_arg: str) -> int:
    """Report host, OS, CPU, memory, and uptime facts.

    Always exits 0 unless report construction itself raises (unreachable
    in practice, since every optional field independently degrades to
    null plus a warning issue rather than aborting). See ``overall`` in
    the report body for degraded-data warnings -- the exit code does not
    reflect partial/optional data being unavailable. ``--format`` is not
    resolved from the configuration file: a broken config file must never
    affect this command's exit code.
    """
    report = build_system_report()
    output_format = OutputFormat(format_arg)
    if output_format is OutputFormat.JSON:
        print(render_inventory_system_json(report))
    else:
        print(render_inventory_system_text(report), end="")
    return EXIT_SUCCESS


def run_inventory_filesystem(
    path_arg: str | None, format_arg: str, max_depth: int, max_entries: int, top: int
) -> int:
    """Report a bounded filesystem tree summary.

    Exits 1 only if the root itself cannot be classified at all
    (nonexistent or inaccessible); recoverable per-entry issues during an
    otherwise-successful scan never affect the exit code. ``--format`` is
    not resolved from the configuration file, for the same reason as
    ``inventory system``.
    """
    report, error = build_filesystem_report(
        path_arg, max_depth=max_depth, max_entries=max_entries, top=top
    )
    if report is None:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_FAILURE

    output_format = OutputFormat(format_arg)
    if output_format is OutputFormat.JSON:
        print(render_inventory_filesystem_json(report))
    else:
        print(render_inventory_filesystem_text(report), end="")
    return EXIT_SUCCESS


def run_logs_parse(
    path_arg: str,
    input_format_arg: str,
    format_arg: str | None,
    max_lines: int,
    max_bytes: int,
    max_line_bytes: int,
    max_events: int,
    *,
    redact: bool,
) -> int:
    """Parse a log file into structured events.

    Exits 1 if the file itself cannot be opened at all, or if it is
    non-empty but contains zero parseable events. A meaningful report
    with warnings (malformed/overlong lines, truncation) still exits 0.
    """
    resolution = resolve_effective_config(cli_output_format=format_arg)
    if resolution.config is None:
        print(f"Error: {resolution.error}", file=sys.stderr)
        return EXIT_FAILURE

    report, error = build_log_parse_report(
        path_arg,
        input_format=LogInputFormat(input_format_arg),
        max_lines=max_lines,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        max_events=max_events,
        redact=redact,
    )
    if report is None:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_FAILURE

    if format_arg is not None:
        output_format = OutputFormat(format_arg)
    else:
        output_format = resolution.config.output_format
    if output_format is OutputFormat.JSON:
        print(render_logs_parse_json(report))
    else:
        print(render_logs_parse_text(report), end="")
    return EXIT_SUCCESS if report.overall is not CheckStatus.FAIL else EXIT_FAILURE


def run_logs_analyze(
    path_arg: str,
    input_format_arg: str,
    format_arg: str | None,
    max_lines: int,
    max_bytes: int,
    max_line_bytes: int,
    top: int,
    bucket_seconds: int,
    repeat_threshold: int,
    error_threshold: int,
    *,
    redact: bool,
) -> int:
    """Stream a log file into deterministic operational analysis.

    Exits 1 if the file itself cannot be opened at all, or if it is
    non-empty but contains zero parseable events. A meaningful report
    with advisory findings still exits 0.
    """
    resolution = resolve_effective_config(cli_output_format=format_arg)
    if resolution.config is None:
        print(f"Error: {resolution.error}", file=sys.stderr)
        return EXIT_FAILURE

    report, error = build_log_analysis_report(
        path_arg,
        input_format=LogInputFormat(input_format_arg),
        max_lines=max_lines,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        top=top,
        bucket_seconds=bucket_seconds,
        repeat_threshold=repeat_threshold,
        error_threshold=error_threshold,
        redact=redact,
    )
    if report is None:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_FAILURE

    if format_arg is not None:
        output_format = OutputFormat(format_arg)
    else:
        output_format = resolution.config.output_format
    if output_format is OutputFormat.JSON:
        print(render_logs_analyze_json(report))
    else:
        print(render_logs_analyze_text(report), end="")
    return EXIT_SUCCESS if report.overall is not CheckStatus.FAIL else EXIT_FAILURE


def _dispatch_version(args: argparse.Namespace) -> int:
    del args
    return run_version()


def _dispatch_doctor(args: argparse.Namespace) -> int:
    return run_doctor(OutputFormat(args.format))


def _dispatch_config_path(args: argparse.Namespace) -> int:
    del args
    return run_config_path()


def _dispatch_config_init(args: argparse.Namespace) -> int:
    return run_config_init(force=args.force)


def _dispatch_config_validate(args: argparse.Namespace) -> int:
    return run_config_validate(args.path)


def _dispatch_config_show(args: argparse.Namespace) -> int:
    return run_config_show(args.format)


def _dispatch_tools_inspect(args: argparse.Namespace) -> int:
    return run_tools_inspect(args.tool, args.format, args.timeout)


def _dispatch_inventory_system(args: argparse.Namespace) -> int:
    return run_inventory_system(args.format)


def _dispatch_inventory_filesystem(args: argparse.Namespace) -> int:
    return run_inventory_filesystem(
        args.path, args.format, args.max_depth, args.max_entries, args.top
    )


def _dispatch_logs_parse(args: argparse.Namespace) -> int:
    return run_logs_parse(
        args.path,
        args.input_format,
        args.format,
        args.max_lines,
        args.max_bytes,
        args.max_line_bytes,
        args.max_events,
        redact=not args.no_redact,
    )


def _dispatch_logs_analyze(args: argparse.Namespace) -> int:
    return run_logs_analyze(
        args.path,
        args.input_format,
        args.format,
        args.max_lines,
        args.max_bytes,
        args.max_line_bytes,
        args.top,
        args.bucket_seconds,
        args.repeat_threshold,
        args.error_threshold,
        redact=not args.no_redact,
    )


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "version": _dispatch_version,
    "doctor": _dispatch_doctor,
}

_CONFIG_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "path": _dispatch_config_path,
    "init": _dispatch_config_init,
    "validate": _dispatch_config_validate,
    "show": _dispatch_config_show,
}

_TOOLS_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "inspect": _dispatch_tools_inspect,
}

_INVENTORY_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "system": _dispatch_inventory_system,
    "filesystem": _dispatch_inventory_filesystem,
}

_LOGS_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "parse": _dispatch_logs_parse,
    "analyze": _dispatch_logs_analyze,
}

_COMMAND_GROUPS: dict[str, dict[str, Callable[[argparse.Namespace], int]]] = {
    "config": _CONFIG_COMMANDS,
    "tools": _TOOLS_COMMANDS,
    "inventory": _INVENTORY_COMMANDS,
    "logs": _LOGS_COMMANDS,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Shared entry point for the console script and ``python -m`` invocation.

    ``--version`` short-circuits whenever ``parser.parse_args()`` itself
    succeeds -- e.g. ``maops-py --version doctor`` prints only the version
    and exits 0, regardless of ``--version``'s position on the command
    line. It does not short-circuit an *incomplete* two-level command
    group given with no leaf subcommand (``config``, ``tools``, or
    ``inventory`` alone): argparse raises a required-subcommand usage
    error during parsing itself, before this function ever inspects
    ``args.version``, so e.g. ``maops-py --version tools`` exits 2 with a
    usage error rather than printing the version.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        return run_version()

    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE_ERROR

    if args.command in _COMMAND_GROUPS:
        subcommand = getattr(args, f"{args.command}_command")
        return _COMMAND_GROUPS[args.command][subcommand](args)

    return _COMMANDS[args.command](args)
