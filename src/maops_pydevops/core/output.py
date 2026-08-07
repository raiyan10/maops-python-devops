"""Text and JSON rendering for toolkit reports. No ANSI, no logging."""

from __future__ import annotations

from maops_pydevops.core.config_models import ConfigShowReport
from maops_pydevops.core.inventory_models import FilesystemInventoryReport, SystemInventoryReport
from maops_pydevops.core.log_models import LogAnalysisReport, LogParseReport
from maops_pydevops.core.models import DoctorReport, ToolsInspectReport

_LABEL_WIDTH = 20
_STATUS_WIDTH = 4


def render_text(report: DoctorReport) -> str:
    """Render a DoctorReport as plain, deterministic text."""
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Doctor Report",
        f"Version:              {report.version}",
        f"Python version:       {report.python.version}",
        f"Python executable:    {report.python.executable}",
        f"Operating system:     {report.platform.system} {report.platform.release}".rstrip(),
        f"Architecture:         {report.platform.architecture}",
        f"Filesystem encoding:  {report.platform.filesystem_encoding}",
        "",
        "Required checks:",
    ]
    for check in report.checks:
        if check.required:
            lines.append(_format_check_line(check.status.value, check.name, check.detail))

    lines.append("")
    lines.append("Optional tools:")
    for check in report.checks:
        if not check.required:
            lines.append(_format_check_line(check.status.value, check.name, check.detail))

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def _format_check_line(status: str, name: str, detail: str) -> str:
    return f"  [{status.upper():<{_STATUS_WIDTH}}] {name:<{_LABEL_WIDTH}} {detail}"


_CONTROL_CHAR_TRANSLATION = {codepoint: f"\\x{codepoint:02x}" for codepoint in range(0x20)}
_CONTROL_CHAR_TRANSLATION[0x09] = "\\t"
_CONTROL_CHAR_TRANSLATION[0x0A] = "\\n"
_CONTROL_CHAR_TRANSLATION[0x0D] = "\\r"
_CONTROL_CHAR_TRANSLATION[0x7F] = "\\x7f"


def _sanitize_for_text(value: str) -> str:
    """Escape control characters (including newlines) in log-derived text.

    A log event's ``message``/``source`` field comes from the file being
    parsed, not from this toolkit -- interpolating it unescaped into a
    line-oriented text report would let a crafted log line forge extra
    report lines (including a fake ``Overall status`` footer). JSON
    output is unaffected (``json.dumps`` already escapes control
    characters correctly); this sanitization applies only to the text
    renderer.
    """
    return value.translate(_CONTROL_CHAR_TRANSLATION)


def render_json(report: DoctorReport) -> str:
    """Render a DoctorReport as a single, deterministic JSON document."""
    return report.to_json()


def render_config_show_text(report: ConfigShowReport) -> str:
    """Render a ConfigShowReport as plain, deterministic text."""
    values = report.values.to_dict()
    sources = report.sources.to_dict()
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Configuration",
        f"Path:   {report.path}",
        f"Exists: {report.exists}",
        f"Valid:  {report.valid}",
        "",
        "Effective values:",
    ]
    for key in ("output_format", "command_timeout_seconds", "max_output_bytes"):
        lines.append(f"  {key:<26} {values[key]!s:<10} (source: {sources[key]})")
    return "\n".join(lines) + "\n"


def render_config_show_json(report: ConfigShowReport) -> str:
    """Render a ConfigShowReport as a single, deterministic JSON document."""
    return report.to_json()


def render_tools_inspect_text(report: ToolsInspectReport) -> str:
    """Render a ToolsInspectReport as plain, deterministic text."""
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Tool Inspection",
        f"Version:     {report.version}",
        f"Config path: {report.configuration.path}",
        "",
        "Tools:",
    ]
    for tool in report.tools:
        lines.append(_format_check_line(tool.status.value, tool.name, tool.detail))

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_tools_inspect_json(report: ToolsInspectReport) -> str:
    """Render a ToolsInspectReport as a single, deterministic JSON document."""
    return report.to_json()


def render_inventory_system_text(report: SystemInventoryReport) -> str:
    """Render a SystemInventoryReport as plain, deterministic text."""
    load_average = "(unavailable)"
    if report.cpu.load_average_1m is not None:
        load_average = (
            f"{report.cpu.load_average_1m} {report.cpu.load_average_5m} "
            f"{report.cpu.load_average_15m}"
        )
    memory_line = "(unavailable)"
    if report.memory.used_percent is not None:
        memory_line = f"{report.memory.used_percent}% of {report.memory.total_bytes} bytes"
    uptime_line = "(unavailable)"
    if report.uptime.seconds is not None:
        uptime_line = f"{report.uptime.seconds}s"

    lines: list[str] = [
        "MAOps Python DevOps Toolkit - System Inventory",
        f"Version:               {report.version}",
        f"Hostname:              {report.host.hostname or '(unknown)'}",
        f"OS:                    {report.host.os_family} {report.host.os_release}".rstrip(),
        f"OS version:            {report.host.os_version or '(unknown)'}",
        f"Machine:               {report.host.machine}",
        (
            f"Distribution:          {report.distribution.name or '(unavailable)'} "
            f"{report.distribution.version_id or ''}"
        ).rstrip(),
        f"Python:                {report.python.version} ({report.python.implementation})",
        f"Python executable:     {report.python.executable}",
        (
            "CPU logical count:     "
            f"{report.cpu.logical_count if report.cpu.logical_count is not None else '(unknown)'}"
        ),
        f"Load average (1/5/15): {load_average}",
        f"Memory used:           {memory_line}",
        f"Uptime:                {uptime_line}",
        "",
        "Issues:",
    ]
    for issue in report.issues:
        lines.append(_format_check_line(issue.status.value, issue.component, issue.detail))

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_inventory_system_json(report: SystemInventoryReport) -> str:
    """Render a SystemInventoryReport as a single, deterministic JSON document."""
    return report.to_json()


def render_inventory_filesystem_text(report: FilesystemInventoryReport) -> str:
    """Render a FilesystemInventoryReport as plain, deterministic text."""
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Filesystem Inventory",
        f"Version:            {report.version}",
        f"Root:               {report.root}",
        f"Max depth:          {report.options.max_depth}",
        f"Max entries:        {report.options.max_entries}",
        f"Scanned entries:    {summary.scanned_entries}",
        f"Directories:        {summary.directories}",
        f"Files:              {summary.files}",
        f"Symlinks:           {summary.symlinks}",
        f"Other:              {summary.other}",
        f"Total file bytes:   {summary.total_file_bytes}",
        f"Skipped entries:    {summary.skipped_entries}",
        f"Inaccessible:       {summary.inaccessible_entries}",
        f"Different fs:       {summary.different_filesystem_entries}",
        f"Max depth reached:  {report.max_depth_reached}",
        f"Truncated:          {report.truncated}",
        "",
        "Largest files:",
    ]
    for entry in report.largest_files:
        lines.append(f"  {entry.size_bytes:>12}  {entry.relative_path}")

    lines.append("")
    lines.append("Issues:")
    for issue in report.issues:
        lines.append(_format_check_line(issue.status.value, issue.component, issue.detail))

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_inventory_filesystem_json(report: FilesystemInventoryReport) -> str:
    """Render a FilesystemInventoryReport as a single, deterministic JSON document."""
    return report.to_json()


def render_logs_parse_text(report: LogParseReport) -> str:
    """Render a LogParseReport as plain, deterministic text."""
    options = report.options
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Log Parse Report",
        f"Version:            {report.version}",
        f"Path:               {report.path}",
        f"Input format:       {options.input_format.value}",
        f"Max lines:          {options.max_lines}",
        f"Max bytes:          {options.max_bytes}",
        f"Max line bytes:     {options.max_line_bytes}",
        f"Max events:         {options.max_events}",
        f"Redaction enabled:  {options.redact}",
        "",
        f"Bytes read:         {summary.bytes_read}",
        f"Lines read:         {summary.lines_read}",
        f"Blank lines:        {summary.blank_lines}",
        f"Events parsed:      {summary.events_parsed}",
        f"Events emitted:     {summary.events_emitted}",
        f"Malformed lines:    {summary.malformed_lines}",
        f"Overlong lines:     {summary.overlong_lines}",
        f"Line limit reached: {report.line_limit_reached}",
        f"Byte limit reached: {report.byte_limit_reached}",
        f"Truncated:          {report.truncated}",
        "",
        "Events:",
    ]
    for event in report.events:
        timestamp = event.timestamp if event.timestamp is not None else "(none)"
        source = _sanitize_for_text(event.source) if event.source is not None else "(none)"
        message = _sanitize_for_text(event.message)
        lines.append(
            f"  [{event.severity.value.upper():<9}] line {event.line_number:>6} "
            f"{timestamp:<25} {source:<15} {message}"
        )

    lines.append("")
    lines.append("Issues:")
    for issue in report.issues:
        detail = f"line {issue.line_number}: {issue.detail}"
        lines.append(_format_check_line(issue.status.value, issue.code.value, detail))

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_logs_parse_json(report: LogParseReport) -> str:
    """Render a LogParseReport as a single, deterministic JSON document."""
    return report.to_json()


def render_logs_analyze_text(report: LogAnalysisReport) -> str:
    """Render a LogAnalysisReport as plain, deterministic text."""
    options = report.options
    summary = report.summary
    time_info = report.time
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Log Analysis Report",
        f"Version:            {report.version}",
        f"Path:               {report.path}",
        f"Input format:       {options.input_format.value}",
        f"Max lines:          {options.max_lines}",
        f"Max bytes:          {options.max_bytes}",
        f"Max line bytes:     {options.max_line_bytes}",
        f"Top:                {options.top}",
        f"Bucket seconds:     {options.bucket_seconds}",
        f"Repeat threshold:   {options.repeat_threshold}",
        f"Error threshold:    {options.error_threshold}",
        f"Redaction enabled:  {options.redact}",
        "",
        f"Bytes read:         {summary.bytes_read}",
        f"Lines read:         {summary.lines_read}",
        f"Events parsed:      {summary.events_parsed}",
        f"Malformed lines:    {summary.malformed_lines}",
        f"Overlong lines:     {summary.overlong_lines}",
        "",
        "Severity counts:",
    ]
    for severity, count in report.severity_counts:
        lines.append(f"  {severity.value:<10} {count}")

    lines.append("")
    lines.append("Top sources:")
    for source in report.source_counts:
        lines.append(f"  {source.count:>6}  {_sanitize_for_text(source.source)}")

    lines.append("")
    lines.append("Top signatures:")
    for signature in report.top_signatures:
        lines.append(
            f"  {signature.count:>6}  (lines {signature.first_line}-{signature.last_line})  "
            f"{_sanitize_for_text(signature.signature)}"
        )

    lines.append("")
    lines.append("Time:")
    lines.append(f"  Timestamped events: {time_info.timestamped_events}")
    lines.append(f"  First timestamp:    {time_info.first_timestamp or '(none)'}")
    lines.append(f"  Last timestamp:     {time_info.last_timestamp or '(none)'}")
    lines.append(f"  Out of order:       {time_info.out_of_order_events}")
    lines.append(f"  Bucket seconds:     {time_info.bucket_seconds}")
    lines.append(f"  Peak bucket start:  {time_info.peak_bucket_start or '(none)'}")
    lines.append(f"  Peak bucket count:  {time_info.peak_bucket_count}")

    lines.append("")
    lines.append("Findings:")
    for finding in report.findings:
        lines.append(_format_check_line(finding.status.value, finding.code.value, finding.detail))

    lines.append("")
    lines.append("Issues:")
    for issue in report.issues:
        detail = f"line {issue.line_number}: {issue.detail}"
        lines.append(_format_check_line(issue.status.value, issue.code.value, detail))

    lines.append("")
    lines.append(f"Truncated: {report.truncated}")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_logs_analyze_json(report: LogAnalysisReport) -> str:
    """Render a LogAnalysisReport as a single, deterministic JSON document."""
    return report.to_json()
