"""Typed data models for declarative ``maops-py`` automation workflows.

A workflow file is declarative data (TOML), never executable code -- see
``docs/workflow-security.md``. Each supported step kind has its own fixed,
explicitly typed parameter dataclass; there is no generic "arbitrary
key/value bag" step representation and no way to express a shell command,
a loop, a condition, or a schedule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.report_models import ReportMetric

#: The only workflow schema version this release understands.
SUPPORTED_SCHEMA_VERSION = 1

#: Hard upper bound on the number of ``[[steps]]`` a workflow file may
#: declare, checked before any step is executed.
MAX_WORKFLOW_STEPS = 32
MIN_WORKFLOW_STEPS = 1


class WorkflowStepKind(StrEnum):
    """The closed set of step kinds a workflow file may declare."""

    DOCTOR = "doctor"
    TOOLS_INSPECT = "tools_inspect"
    INVENTORY_SYSTEM = "inventory_system"
    INVENTORY_FILESYSTEM = "inventory_filesystem"
    LOGS_ANALYZE = "logs_analyze"
    HEALTH_HTTP = "health_http"
    HEALTH_TCP = "health_tcp"


@dataclass(frozen=True)
class DoctorStepParams:
    """``doctor`` takes no parameters -- mirrors ``maops-py doctor``'s own CLI surface."""


@dataclass(frozen=True)
class ToolsInspectStepParams:
    tools: tuple[str, ...] = ()
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class InventorySystemStepParams:
    """``inventory_system`` takes no parameters."""


@dataclass(frozen=True)
class InventoryFilesystemStepParams:
    path: str | None = None
    max_depth: int = 2
    max_entries: int = 10000
    top: int = 10


@dataclass(frozen=True)
class LogsAnalyzeStepParams:
    path: str
    input_format: str = "auto"
    max_lines: int = 10000
    max_bytes: int = 10485760
    max_line_bytes: int = 65536
    top: int = 10
    bucket_seconds: int = 300
    repeat_threshold: int = 5
    error_threshold: int = 1
    redact: bool = True


@dataclass(frozen=True)
class HealthHttpStepParams:
    urls: tuple[str, ...]
    method: str = "GET"
    expect_status_min: int = 200
    expect_status_max: int = 399
    timeout_seconds: float = 3.0
    retries: int = 1
    retry_delay_seconds: float = 0.25
    workers: int = 4


@dataclass(frozen=True)
class HealthTcpStepParams:
    targets: tuple[str, ...]
    timeout_seconds: float = 3.0
    retries: int = 1
    retry_delay_seconds: float = 0.25
    workers: int = 4


StepParams = (
    DoctorStepParams
    | ToolsInspectStepParams
    | InventorySystemStepParams
    | InventoryFilesystemStepParams
    | LogsAnalyzeStepParams
    | HealthHttpStepParams
    | HealthTcpStepParams
)


@dataclass(frozen=True)
class WorkflowStep:
    """One parsed, validated ``[[steps]]`` entry."""

    id: str
    kind: WorkflowStepKind
    params: StepParams


@dataclass(frozen=True)
class Workflow:
    """A fully parsed and schema-validated workflow document."""

    schema_version: int
    name: str
    steps: tuple[WorkflowStep, ...]


class WorkflowValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class WorkflowValidationReport:
    """The full report rendered by ``maops-py workflow validate``."""

    version: str
    path: str
    status: WorkflowValidationStatus
    workflow_name: str | None
    step_count: int
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "path": self.path,
            "status": self.status.value,
            "workflow_name": self.workflow_name,
            "step_count": self.step_count,
            "error": self.error,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


@dataclass(frozen=True)
class WorkflowRunOptions:
    """The bounds in effect for a ``workflow run`` invocation."""

    max_steps: int

    def to_dict(self) -> dict[str, object]:
        return {"max_steps": self.max_steps}


@dataclass(frozen=True)
class WorkflowRunSummary:
    """Aggregate counters across every executed step."""

    steps: int
    pass_count: int
    warn_count: int
    fail_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "steps": self.steps,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
        }


@dataclass(frozen=True)
class WorkflowStepResult:
    """The outcome of running one declared step.

    ``error`` is set only when the step could not produce a report at all
    (e.g. an ``inventory_filesystem`` root that vanished between
    validation and execution) -- in that case ``status`` is always
    :data:`CheckStatus.FAIL` and ``metrics`` is empty, but the step still
    appears in ``WorkflowRunReport.steps`` like any other, per the "a
    failed step must not discard already-completed results" contract.
    """

    id: str
    kind: WorkflowStepKind
    status: CheckStatus
    headline: str
    metrics: tuple[ReportMetric, ...]
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "status": self.status.value,
            "headline": self.headline,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "error": self.error,
        }


@dataclass(frozen=True)
class WorkflowRunReport:
    """The full report rendered by ``maops-py workflow run``."""

    version: str
    path: str
    name: str
    options: WorkflowRunOptions
    summary: WorkflowRunSummary
    steps: tuple[WorkflowStepResult, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "path": self.path,
            "name": self.name,
            "options": self.options.to_dict(),
            "summary": self.summary.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
