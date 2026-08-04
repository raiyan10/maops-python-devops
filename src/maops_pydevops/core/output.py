"""Text and JSON rendering for toolkit reports. No ANSI, no logging."""

from __future__ import annotations

from maops_pydevops.core.config_models import ConfigShowReport
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
