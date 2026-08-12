"""Text and JSON rendering for toolkit reports. No ANSI, no logging."""

from __future__ import annotations

from maops_pydevops.core.config_models import ConfigShowReport
from maops_pydevops.core.health_models import HttpReport, TcpReport
from maops_pydevops.core.inventory_models import FilesystemInventoryReport, SystemInventoryReport
from maops_pydevops.core.log_models import LogAnalysisReport, LogParseReport
from maops_pydevops.core.models import DoctorReport, ToolsInspectReport
from maops_pydevops.core.report_models import AggregateReport, NormalizedReport
from maops_pydevops.core.workflow_models import WorkflowRunReport, WorkflowValidationReport

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

#: Zero-width and bidi-override/isolate formatting characters. These are
#: valid, printable-width-zero Unicode codepoints (not C0/C1 controls), so
#: the control-character table above never touches them -- but a crafted
#: log line could still use them to visually reorder or hide report text
#: (e.g. RIGHT-TO-LEFT OVERRIDE around a forged "Overall status" line).
#: Escaped the same way control characters are: never emitted raw into a
#: line-oriented text report.
_FORMATTING_CHAR_TRANSLATION = {
    codepoint: f"\\u{codepoint:04x}"
    for codepoint in (
        0x200B,  # ZERO WIDTH SPACE
        0x200C,  # ZERO WIDTH NON-JOINER
        0x200D,  # ZERO WIDTH JOINER
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
    )
}
_CONTROL_CHAR_TRANSLATION.update(_FORMATTING_CHAR_TRANSLATION)


def _sanitize_for_text(value: str) -> str:
    """Escape control and formatting characters in untrusted, external text.

    Untrusted text (a log event's ``message``/``source`` field, a health
    target string, a report path) does not come from this toolkit --
    interpolating it unescaped into a line-oriented text report would let
    crafted input forge extra report lines (including a fake "Overall
    status" footer) or visually reorder/hide report content via Unicode
    bidi-override or zero-width characters. JSON output is unaffected
    (``json.dumps`` already escapes control characters correctly, and
    Unicode formatting characters are valid JSON string content); this
    sanitization applies only to the text renderer.
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
        hostname = _sanitize_for_text(event.hostname) if event.hostname is not None else "(none)"
        source = _sanitize_for_text(event.source) if event.source is not None else "(none)"
        message = _sanitize_for_text(event.message)
        lines.append(
            f"  [{event.severity.value.upper():<9}] line {event.line_number:>6} "
            f"{timestamp:<25} {hostname:<15} {source:<15} {message}"
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


def render_health_http_text(report: HttpReport) -> str:
    """Render an HttpReport as plain, deterministic text."""
    options = report.options
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - HTTP Health Check",
        f"Version:            {report.version}",
        f"Protocol:           {report.protocol.value}",
        f"Method:             {options.method.value}",
        f"Expected status:    {options.expected_status_min}-{options.expected_status_max}",
        f"Timeout (s):        {options.timeout_seconds}",
        f"Retries:            {options.retries}",
        f"Retry delay (s):    {options.retry_delay_seconds}",
        f"Workers:            {options.workers}",
        f"Follow redirects:   {options.follow_redirects}",
        f"TLS verify:         {options.tls_verify}",
        "",
        "Targets:",
    ]
    for result in report.results:
        target = _sanitize_for_text(result.target)
        final_attempt = result.attempts[-1] if result.attempts else None
        detail = (
            _sanitize_for_text(final_attempt.detail)
            if final_attempt is not None and final_attempt.detail is not None
            else "(none)"
        )
        peer_ip = result.peer_ip or "(none)"
        final_status = (
            str(result.final_http_status) if result.final_http_status is not None else "(none)"
        )
        detail_line = (
            f"attempts={result.attempts_used} final_status={final_status} "
            f"peer_ip={peer_ip} duration_ms={result.total_duration_ms} detail={detail}"
        )
        lines.append(
            _format_check_line(result.status.value, f"#{result.index} {target}", detail_line)
        )

    lines.append("")
    lines.append("Summary:")
    lines.append(
        f"  targets={summary.targets} passed={summary.passed} "
        f"warned={summary.warned} failed={summary.failed} attempts={summary.attempts}"
    )
    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_health_http_json(report: HttpReport) -> str:
    """Render an HttpReport as a single, deterministic JSON document."""
    return report.to_json()


def render_health_tcp_text(report: TcpReport) -> str:
    """Render a TcpReport as plain, deterministic text."""
    options = report.options
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - TCP Health Check",
        f"Version:            {report.version}",
        f"Protocol:           {report.protocol.value}",
        f"Timeout (s):        {options.timeout_seconds}",
        f"Retries:            {options.retries}",
        f"Retry delay (s):    {options.retry_delay_seconds}",
        f"Workers:            {options.workers}",
        "",
        "Targets:",
    ]
    for result in report.results:
        target = _sanitize_for_text(result.target)
        final_attempt = result.attempts[-1] if result.attempts else None
        detail = (
            _sanitize_for_text(final_attempt.detail)
            if final_attempt is not None and final_attempt.detail is not None
            else "(none)"
        )
        peer_ip = result.peer_ip or "(none)"
        detail_line = (
            f"host={result.host} port={result.port} attempts={result.attempts_used} "
            f"peer_ip={peer_ip} duration_ms={result.total_duration_ms} detail={detail}"
        )
        lines.append(
            _format_check_line(result.status.value, f"#{result.index} {target}", detail_line)
        )

    lines.append("")
    lines.append("Summary:")
    lines.append(
        f"  targets={summary.targets} passed={summary.passed} "
        f"warned={summary.warned} failed={summary.failed} attempts={summary.attempts}"
    )
    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_health_tcp_json(report: TcpReport) -> str:
    """Render a TcpReport as a single, deterministic JSON document."""
    return report.to_json()


#: GitHub-flavored-Markdown-significant characters, escaped so external
#: text can never forge table cells, emphasis runs, links, or raw HTML/
#: autolinks. Full per-character rationale: docs/aggregated-reports.md,
#: "Markdown escaping rationale".
_MARKDOWN_SPECIAL_CHARS = str.maketrans(
    {
        "\\": "\\\\",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "|": "\\|",
        "[": "\\[",
        "]": "\\]",
        "<": "\\<",
        ">": "\\>",
    }
)


def _sanitize_for_markdown(value: str) -> str:
    """Escape Markdown-significant characters in untrusted, external text.

    Applied after :func:`_sanitize_for_text`'s control/formatting-character
    escaping, so input is already free of raw control characters and
    newlines by this point -- this step only prevents *Markdown* syntax
    injection (forging a table cell boundary, emphasis run, or heading)
    from externally sourced text such as a report path or hostname.
    """
    return _sanitize_for_text(value).translate(_MARKDOWN_SPECIAL_CHARS)


def render_report_aggregate_text(report: AggregateReport) -> str:
    """Render an AggregateReport as plain, deterministic text."""
    options = report.options
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Aggregated Report",
        f"Version:            {report.version}",
        f"Max reports:        {options.max_reports}",
        f"Max file bytes:     {options.max_file_bytes}",
        "",
        (
            f"Reports:            {summary.reports} "
            f"({summary.pass_count} pass, {summary.warn_count} warn, {summary.fail_count} fail)"
        ),
        "",
        "Reports:",
    ]
    for normalized in report.reports:
        lines.append(
            _format_check_line(
                normalized.status.value,
                f"{normalized.kind.value} {_sanitize_for_text(normalized.source_path)}",
                _sanitize_for_text(normalized.headline),
            )
        )
        for metric in normalized.metrics:
            lines.append(f"      {metric.label}: {_sanitize_for_text(metric.value)}")

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_report_aggregate_json(report: AggregateReport) -> str:
    """Render an AggregateReport as a single, deterministic JSON document."""
    return report.to_json()


def _render_normalized_report_markdown(normalized: NormalizedReport) -> list[str]:
    lines = [
        f"### {_sanitize_for_markdown(normalized.source_path)} "
        f"({normalized.kind.value}) — {normalized.status.value.upper()}",
        "",
        _sanitize_for_markdown(normalized.headline),
        "",
    ]
    if normalized.metrics:
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for metric in normalized.metrics:
            lines.append(f"| {metric.label} | {_sanitize_for_markdown(metric.value)} |")
        lines.append("")
    return lines


def render_report_aggregate_markdown(report: AggregateReport) -> str:
    """Render an AggregateReport as deterministic GitHub-flavored Markdown."""
    summary = report.summary
    lines: list[str] = [
        "# MAOps Aggregated Report",
        "",
        f"**Version:** {report.version}  ",
        f"**Overall status:** {report.overall.value.upper()}  ",
        (
            f"**Summary:** {summary.reports} report(s) — {summary.pass_count} pass, "
            f"{summary.warn_count} warn, {summary.fail_count} fail"
        ),
        "",
    ]
    for normalized in report.reports:
        lines.extend(_render_normalized_report_markdown(normalized))
    return "\n".join(lines).rstrip("\n") + "\n"


def render_workflow_validate_text(report: WorkflowValidationReport) -> str:
    """Render a WorkflowValidationReport as plain, deterministic text."""
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Workflow Validation",
        f"Version:      {report.version}",
        f"Path:         {_sanitize_for_text(report.path)}",
        f"Status:       {report.status.value.upper()}",
        (
            f"Workflow:     "
            f"{_sanitize_for_text(report.workflow_name) if report.workflow_name else '(none)'}"
        ),
        f"Step count:   {report.step_count}",
        f"Error:        {_sanitize_for_text(report.error) if report.error else '(none)'}",
    ]
    return "\n".join(lines) + "\n"


def render_workflow_validate_json(report: WorkflowValidationReport) -> str:
    """Render a WorkflowValidationReport as a single, deterministic JSON document."""
    return report.to_json()


def render_workflow_run_text(report: WorkflowRunReport) -> str:
    """Render a WorkflowRunReport as plain, deterministic text."""
    summary = report.summary
    lines: list[str] = [
        "MAOps Python DevOps Toolkit - Workflow Run",
        f"Version:            {report.version}",
        f"Path:               {_sanitize_for_text(report.path)}",
        f"Name:               {_sanitize_for_text(report.name)}",
        f"Max steps:          {report.options.max_steps}",
        "",
        (
            f"Steps:              {summary.steps} "
            f"({summary.pass_count} pass, {summary.warn_count} warn, {summary.fail_count} fail)"
        ),
        "",
        "Steps:",
    ]
    for step in report.steps:
        lines.append(
            _format_check_line(
                step.status.value,
                f"{step.kind.value} {_sanitize_for_text(step.id)}",
                _sanitize_for_text(step.headline),
            )
        )
        for metric in step.metrics:
            lines.append(f"      {metric.label}: {_sanitize_for_text(metric.value)}")

    lines.append("")
    lines.append(f"Overall status: {report.overall.value.upper()}")
    return "\n".join(lines) + "\n"


def render_workflow_run_json(report: WorkflowRunReport) -> str:
    """Render a WorkflowRunReport as a single, deterministic JSON document."""
    return report.to_json()


def render_workflow_run_markdown(report: WorkflowRunReport) -> str:
    """Render a WorkflowRunReport as deterministic GitHub-flavored Markdown."""
    summary = report.summary
    lines: list[str] = [
        f"# MAOps Workflow Run: {_sanitize_for_markdown(report.name)}",
        "",
        f"**Version:** {report.version}  ",
        f"**Path:** {_sanitize_for_markdown(report.path)}  ",
        f"**Overall status:** {report.overall.value.upper()}  ",
        (
            f"**Summary:** {summary.steps} step(s) — {summary.pass_count} pass, "
            f"{summary.warn_count} warn, {summary.fail_count} fail"
        ),
        "",
    ]
    for step in report.steps:
        step_heading = (
            f"### {_sanitize_for_markdown(step.id)} ({step.kind.value}) — "
            f"{step.status.value.upper()}"
        )
        lines.append(step_heading)
        lines.append("")
        lines.append(_sanitize_for_markdown(step.headline))
        lines.append("")
        if step.metrics:
            lines.append("| Metric | Value |")
            lines.append("|---|---|")
            for metric in step.metrics:
                lines.append(f"| {metric.label} | {_sanitize_for_markdown(metric.value)} |")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
