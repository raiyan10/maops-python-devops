"""Typed data models for aggregated MAOps operational reports.

An :class:`AggregateReport` never blindly embeds a raw input report -- each
input JSON document is normalized into a small, explicitly typed
:class:`NormalizedReport` (a status, a one-line headline, and a bounded set
of typed ``metrics``) before it ever reaches an aggregate. This keeps the
aggregate's own schema stable and independent of any single source
command's internal field layout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from maops_pydevops.core.models import CheckStatus


class ReportOutputFormat(StrEnum):
    """Output formats for ``report aggregate``/``workflow run``.

    Deliberately a separate enum from :class:`maops_pydevops.core.models.OutputFormat`
    (``text``/``json``): every other command's ``--format`` choices are
    built from that shared enum, so adding ``markdown`` to it would leak
    an unsupported choice onto every other command's CLI surface.
    """

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class ReportKind(StrEnum):
    """The closed set of ``maops-py`` JSON report types accepted by ``report aggregate``."""

    DOCTOR = "doctor"
    TOOLS_INSPECT = "tools_inspect"
    INVENTORY_SYSTEM = "inventory_system"
    INVENTORY_FILESYSTEM = "inventory_filesystem"
    LOGS_PARSE = "logs_parse"
    LOGS_ANALYZE = "logs_analyze"
    HEALTH_HTTP = "health_http"
    HEALTH_TCP = "health_tcp"


@dataclass(frozen=True)
class ReportMetric:
    """One small, named, already-sanitized fact extracted from a source report."""

    label: str
    value: str

    def to_dict(self) -> dict[str, object]:
        return {"label": self.label, "value": self.value}


@dataclass(frozen=True)
class NormalizedReport:
    """A source report normalized into a small, typed, bounded summary.

    ``source_path`` is the path supplied on the command line (for
    ``report aggregate``) or the workflow step id (for ``workflow run``) --
    never the source report's own internal ``path``/``root`` field
    verbatim, which could be arbitrarily long or contain untrusted bytes.
    """

    source_path: str
    kind: ReportKind
    source_version: str
    status: CheckStatus
    headline: str
    metrics: tuple[ReportMetric, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "kind": self.kind.value,
            "source_version": self.source_version,
            "status": self.status.value,
            "headline": self.headline,
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


@dataclass(frozen=True)
class AggregateOptions:
    """The bounds in effect for a ``report aggregate`` run."""

    max_reports: int
    max_file_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"max_reports": self.max_reports, "max_file_bytes": self.max_file_bytes}


@dataclass(frozen=True)
class AggregateSummary:
    """Aggregate counters across every normalized report."""

    reports: int
    pass_count: int
    warn_count: int
    fail_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "reports": self.reports,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
        }


@dataclass(frozen=True)
class AggregateReport:
    """The full report rendered by ``maops-py report aggregate``."""

    version: str
    options: AggregateOptions
    summary: AggregateSummary
    reports: tuple[NormalizedReport, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "reports": [report.to_dict() for report in self.reports],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
