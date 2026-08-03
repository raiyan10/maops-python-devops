"""Text and JSON rendering for a DoctorReport. No ANSI, no logging."""

from __future__ import annotations

from maops_pydevops.core.models import DoctorReport

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
