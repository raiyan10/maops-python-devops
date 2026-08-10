"""TOML parsing and schema validation for declarative ``maops-py`` workflows.

Parses and validates only -- never executes a step, opens a socket, or
resolves a tool executable. Reuses the package's actual existing target
validators (``core/health_http.py:validate_http_target``,
``core/health_tcp.py:validate_tcp_target``, both pure syntax/semantics
checks with no network I/O) and the real tool allowlist
(``commands/tools.py:TOOL_ALLOWLIST``), so a workflow's target/tool
mistakes are caught at validation time using the identical rules
``health http``/``health tcp``/``tools inspect`` enforce at the CLI layer,
not a second, potentially drifting copy of them. See
``docs/workflow-security.md`` for the full "declarative data, not
executable code" contract.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from maops_pydevops.commands.tools import TOOL_ALLOWLIST
from maops_pydevops.core.config_models import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MIN_COMMAND_TIMEOUT_SECONDS,
)
from maops_pydevops.core.health_http import validate_http_target
from maops_pydevops.core.health_tcp import validate_tcp_target
from maops_pydevops.core.log_models import LogInputFormat
from maops_pydevops.core.workflow_models import (
    MAX_WORKFLOW_STEPS,
    MIN_WORKFLOW_STEPS,
    SUPPORTED_SCHEMA_VERSION,
    DoctorStepParams,
    HealthHttpStepParams,
    HealthTcpStepParams,
    InventoryFilesystemStepParams,
    InventorySystemStepParams,
    LogsAnalyzeStepParams,
    StepParams,
    ToolsInspectStepParams,
    Workflow,
    WorkflowStep,
    WorkflowStepKind,
)

_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"schema_version", "name", "steps"})
_COMMON_STEP_KEYS: frozenset[str] = frozenset({"id", "kind"})
_ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(name for name, _ in TOOL_ALLOWLIST)

#: Mirrors ``commands/health.py``'s ``MIN_TARGETS``/``MAX_TARGETS`` -- kept
#: as a local literal rather than a cross-layer import from ``commands/``,
#: matching this project's existing convention of duplicating small,
#: stable numeric bounds (e.g. ``cli.py``'s ``_parse_*`` callbacks) rather
#: than reaching into a sibling command module for a constant.
_MIN_TARGETS = 1
_MAX_TARGETS = 100


def _unknown_keys_error(
    raw: dict[str, object], allowed: frozenset[str], *, label: str
) -> str | None:
    unknown = set(raw.keys()) - allowed
    if unknown:
        return f"{label}: unknown field(s): {', '.join(sorted(unknown))}"
    return None


def _opt_str(
    raw: dict[str, object],
    key: str,
    default: str,
    *,
    label: str,
    choices: frozenset[str] | None = None,
) -> tuple[str | None, str | None]:
    if key not in raw:
        return default, None
    value = raw[key]
    if not isinstance(value, str):
        return None, f"{label}: {key} must be a string"
    if choices is not None and value not in choices:
        return None, f"{label}: {key} must be one of {', '.join(sorted(choices))}"
    return value, None


def _opt_str_or_none(
    raw: dict[str, object], key: str, *, label: str
) -> tuple[str | None, str | None]:
    if key not in raw:
        return None, None
    value = raw[key]
    if not isinstance(value, str) or not value:
        return None, f"{label}: {key} must be a non-empty string"
    return value, None


def _req_str(raw: dict[str, object], key: str, *, label: str) -> tuple[str | None, str | None]:
    if key not in raw:
        return None, f"{label}: {key} is required"
    value = raw[key]
    if not isinstance(value, str) or not value:
        return None, f"{label}: {key} must be a non-empty string"
    return value, None


def _opt_int(
    raw: dict[str, object], key: str, default: int, *, minimum: int, maximum: int, label: str
) -> tuple[int | None, str | None]:
    if key not in raw:
        return default, None
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        return None, f"{label}: {key} must be an integer"
    if not (minimum <= value <= maximum):
        return None, f"{label}: {key} must be between {minimum} and {maximum}"
    return value, None


def _opt_float(
    raw: dict[str, object],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
    min_exclusive: bool,
    label: str,
) -> tuple[float | None, str | None]:
    if key not in raw:
        return default, None
    value = raw[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None, f"{label}: {key} must be a number"
    numeric = float(value)
    lower_ok = numeric > minimum if min_exclusive else numeric >= minimum
    if not (lower_ok and numeric <= maximum):
        bound = f"greater than {minimum}" if min_exclusive else f"at least {minimum}"
        return None, f"{label}: {key} must be {bound} and at most {maximum}"
    return numeric, None


def _opt_float_or_none(
    raw: dict[str, object],
    key: str,
    *,
    minimum: float,
    maximum: float,
    min_exclusive: bool,
    label: str,
) -> tuple[float | None, str | None]:
    if key not in raw:
        return None, None
    value = raw[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None, f"{label}: {key} must be a number"
    numeric = float(value)
    lower_ok = numeric > minimum if min_exclusive else numeric >= minimum
    if not (lower_ok and numeric <= maximum):
        bound = f"greater than {minimum}" if min_exclusive else f"at least {minimum}"
        return None, f"{label}: {key} must be {bound} and at most {maximum}"
    return numeric, None


def _opt_bool(
    raw: dict[str, object], key: str, default: bool, *, label: str
) -> tuple[bool | None, str | None]:
    if key not in raw:
        return default, None
    value = raw[key]
    if not isinstance(value, bool):
        return None, f"{label}: {key} must be a boolean"
    return value, None


def _opt_str_tuple(
    raw: dict[str, object], key: str, *, label: str
) -> tuple[tuple[str, ...] | None, str | None]:
    if key not in raw:
        return (), None
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None, f"{label}: {key} must be an array of non-empty strings"
    return tuple(value), None


def _req_str_tuple(
    raw: dict[str, object], key: str, *, label: str, min_items: int, max_items: int
) -> tuple[tuple[str, ...] | None, str | None]:
    if key not in raw:
        return None, f"{label}: {key} is required"
    value = raw[key]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None, f"{label}: {key} must be an array of non-empty strings"
    if not (min_items <= len(value) <= max_items):
        return (
            None,
            f"{label}: {key} count must be between {min_items} and {max_items}, got {len(value)}",
        )
    return tuple(value), None


_DOCTOR_KEYS = _COMMON_STEP_KEYS
_INVENTORY_SYSTEM_KEYS = _COMMON_STEP_KEYS
_TOOLS_INSPECT_KEYS = _COMMON_STEP_KEYS | {"tools", "timeout_seconds"}
_INVENTORY_FILESYSTEM_KEYS = _COMMON_STEP_KEYS | {"path", "max_depth", "max_entries", "top"}
_LOGS_ANALYZE_KEYS = _COMMON_STEP_KEYS | {
    "path",
    "input_format",
    "max_lines",
    "max_bytes",
    "max_line_bytes",
    "top",
    "bucket_seconds",
    "repeat_threshold",
    "error_threshold",
    "redact",
}
_HEALTH_HTTP_KEYS = _COMMON_STEP_KEYS | {
    "urls",
    "method",
    "expect_status_min",
    "expect_status_max",
    "timeout_seconds",
    "retries",
    "retry_delay_seconds",
    "workers",
}
_HEALTH_TCP_KEYS = _COMMON_STEP_KEYS | {
    "targets",
    "timeout_seconds",
    "retries",
    "retry_delay_seconds",
    "workers",
}


def _parse_doctor(raw: dict[str, object], *, label: str) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _DOCTOR_KEYS, label=label)
    if error is not None:
        return None, error
    return DoctorStepParams(), None


def _parse_inventory_system(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _INVENTORY_SYSTEM_KEYS, label=label)
    if error is not None:
        return None, error
    return InventorySystemStepParams(), None


def _parse_tools_inspect(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _TOOLS_INSPECT_KEYS, label=label)
    if error is not None:
        return None, error
    tools, error = _opt_str_tuple(raw, "tools", label=label)
    if error is not None:
        return None, error
    assert tools is not None
    unsupported = sorted(set(tools) - _ALLOWED_TOOL_NAMES)
    if unsupported:
        allowed = ", ".join(sorted(_ALLOWED_TOOL_NAMES))
        return (
            None,
            f"{label}: unsupported tool name(s): {', '.join(unsupported)} (choose from {allowed})",
        )
    timeout_seconds, error = _opt_float_or_none(
        raw,
        "timeout_seconds",
        minimum=MIN_COMMAND_TIMEOUT_SECONDS,
        maximum=MAX_COMMAND_TIMEOUT_SECONDS,
        min_exclusive=True,
        label=label,
    )
    if error is not None:
        return None, error
    return ToolsInspectStepParams(tools=tools, timeout_seconds=timeout_seconds), None


def _parse_inventory_filesystem(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _INVENTORY_FILESYSTEM_KEYS, label=label)
    if error is not None:
        return None, error
    path, error = _opt_str_or_none(raw, "path", label=label)
    if error is not None:
        return None, error
    max_depth, error = _opt_int(raw, "max_depth", 2, minimum=0, maximum=64, label=label)
    if error is not None:
        return None, error
    max_entries, error = _opt_int(
        raw, "max_entries", 10000, minimum=1, maximum=1_000_000, label=label
    )
    if error is not None:
        return None, error
    top, error = _opt_int(raw, "top", 10, minimum=0, maximum=100, label=label)
    if error is not None:
        return None, error
    assert max_depth is not None and max_entries is not None and top is not None
    return (
        InventoryFilesystemStepParams(
            path=path, max_depth=max_depth, max_entries=max_entries, top=top
        ),
        None,
    )


def _parse_logs_analyze(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _LOGS_ANALYZE_KEYS, label=label)
    if error is not None:
        return None, error
    path, error = _req_str(raw, "path", label=label)
    if error is not None:
        return None, error
    input_format, error = _opt_str(
        raw,
        "input_format",
        "auto",
        label=label,
        choices=frozenset(fmt.value for fmt in LogInputFormat),
    )
    if error is not None:
        return None, error
    max_lines, error = _opt_int(raw, "max_lines", 10000, minimum=1, maximum=1_000_000, label=label)
    if error is not None:
        return None, error
    max_bytes, error = _opt_int(
        raw, "max_bytes", 10485760, minimum=1024, maximum=104_857_600, label=label
    )
    if error is not None:
        return None, error
    max_line_bytes, error = _opt_int(
        raw, "max_line_bytes", 65536, minimum=256, maximum=1_048_576, label=label
    )
    if error is not None:
        return None, error
    top, error = _opt_int(raw, "top", 10, minimum=0, maximum=100, label=label)
    if error is not None:
        return None, error
    bucket_seconds, error = _opt_int(
        raw, "bucket_seconds", 300, minimum=1, maximum=86_400, label=label
    )
    if error is not None:
        return None, error
    repeat_threshold, error = _opt_int(
        raw, "repeat_threshold", 5, minimum=2, maximum=1_000_000, label=label
    )
    if error is not None:
        return None, error
    error_threshold, error = _opt_int(
        raw, "error_threshold", 1, minimum=1, maximum=1_000_000, label=label
    )
    if error is not None:
        return None, error
    redact, error = _opt_bool(raw, "redact", True, label=label)
    if error is not None:
        return None, error
    assert (
        path is not None
        and input_format is not None
        and max_lines is not None
        and max_bytes is not None
        and max_line_bytes is not None
        and top is not None
        and bucket_seconds is not None
        and repeat_threshold is not None
        and error_threshold is not None
        and redact is not None
    )
    return (
        LogsAnalyzeStepParams(
            path=path,
            input_format=input_format,
            max_lines=max_lines,
            max_bytes=max_bytes,
            max_line_bytes=max_line_bytes,
            top=top,
            bucket_seconds=bucket_seconds,
            repeat_threshold=repeat_threshold,
            error_threshold=error_threshold,
            redact=redact,
        ),
        None,
    )


def _parse_health_http(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _HEALTH_HTTP_KEYS, label=label)
    if error is not None:
        return None, error
    urls, error = _req_str_tuple(
        raw, "urls", label=label, min_items=_MIN_TARGETS, max_items=_MAX_TARGETS
    )
    if error is not None:
        return None, error
    assert urls is not None
    for index, url in enumerate(urls, start=1):
        _target, target_error = validate_http_target(url, index=index)
        if target_error is not None:
            return None, f"{label}: {target_error}"
    method, error = _opt_str(raw, "method", "GET", label=label, choices=frozenset({"GET", "HEAD"}))
    if error is not None:
        return None, error
    expect_status_min, error = _opt_int(
        raw, "expect_status_min", 200, minimum=100, maximum=599, label=label
    )
    if error is not None:
        return None, error
    expect_status_max, error = _opt_int(
        raw, "expect_status_max", 399, minimum=100, maximum=599, label=label
    )
    if error is not None:
        return None, error
    assert expect_status_min is not None and expect_status_max is not None
    if expect_status_min > expect_status_max:
        return None, f"{label}: expect_status_min must be <= expect_status_max"
    timeout_seconds, error = _opt_float(
        raw, "timeout_seconds", 3.0, minimum=0.0, maximum=60.0, min_exclusive=True, label=label
    )
    if error is not None:
        return None, error
    retries, error = _opt_int(raw, "retries", 1, minimum=0, maximum=5, label=label)
    if error is not None:
        return None, error
    retry_delay_seconds, error = _opt_float(
        raw,
        "retry_delay_seconds",
        0.25,
        minimum=0.0,
        maximum=30.0,
        min_exclusive=False,
        label=label,
    )
    if error is not None:
        return None, error
    workers, error = _opt_int(raw, "workers", 4, minimum=1, maximum=32, label=label)
    if error is not None:
        return None, error
    assert (
        method is not None
        and timeout_seconds is not None
        and retries is not None
        and retry_delay_seconds is not None
        and workers is not None
    )
    return (
        HealthHttpStepParams(
            urls=urls,
            method=method,
            expect_status_min=expect_status_min,
            expect_status_max=expect_status_max,
            timeout_seconds=timeout_seconds,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
            workers=workers,
        ),
        None,
    )


def _parse_health_tcp(
    raw: dict[str, object], *, label: str
) -> tuple[StepParams | None, str | None]:
    error = _unknown_keys_error(raw, _HEALTH_TCP_KEYS, label=label)
    if error is not None:
        return None, error
    targets, error = _req_str_tuple(
        raw, "targets", label=label, min_items=_MIN_TARGETS, max_items=_MAX_TARGETS
    )
    if error is not None:
        return None, error
    assert targets is not None
    for index, target in enumerate(targets, start=1):
        _validated, target_error = validate_tcp_target(target, index=index)
        if target_error is not None:
            return None, f"{label}: {target_error}"
    timeout_seconds, error = _opt_float(
        raw, "timeout_seconds", 3.0, minimum=0.0, maximum=60.0, min_exclusive=True, label=label
    )
    if error is not None:
        return None, error
    retries, error = _opt_int(raw, "retries", 1, minimum=0, maximum=5, label=label)
    if error is not None:
        return None, error
    retry_delay_seconds, error = _opt_float(
        raw,
        "retry_delay_seconds",
        0.25,
        minimum=0.0,
        maximum=30.0,
        min_exclusive=False,
        label=label,
    )
    if error is not None:
        return None, error
    workers, error = _opt_int(raw, "workers", 4, minimum=1, maximum=32, label=label)
    if error is not None:
        return None, error
    assert (
        timeout_seconds is not None
        and retries is not None
        and retry_delay_seconds is not None
        and workers is not None
    )
    return (
        HealthTcpStepParams(
            targets=targets,
            timeout_seconds=timeout_seconds,
            retries=retries,
            retry_delay_seconds=retry_delay_seconds,
            workers=workers,
        ),
        None,
    )


_ParamParser = Callable[..., tuple[StepParams | None, str | None]]

_PARAM_PARSERS: dict[WorkflowStepKind, _ParamParser] = {
    WorkflowStepKind.DOCTOR: _parse_doctor,
    WorkflowStepKind.TOOLS_INSPECT: _parse_tools_inspect,
    WorkflowStepKind.INVENTORY_SYSTEM: _parse_inventory_system,
    WorkflowStepKind.INVENTORY_FILESYSTEM: _parse_inventory_filesystem,
    WorkflowStepKind.LOGS_ANALYZE: _parse_logs_analyze,
    WorkflowStepKind.HEALTH_HTTP: _parse_health_http,
    WorkflowStepKind.HEALTH_TCP: _parse_health_tcp,
}


def _parse_step(raw: object, *, index: int) -> tuple[WorkflowStep | None, str | None]:
    if not isinstance(raw, dict):
        return None, f"step {index}: must be a table"

    id_raw = raw.get("id")
    if not isinstance(id_raw, str) or not id_raw:
        return None, f"step {index}: id must be a non-empty string"

    kind_raw = raw.get("kind")
    if not isinstance(kind_raw, str):
        return None, f"step {index} ({id_raw!r}): kind must be a string"
    try:
        kind = WorkflowStepKind(kind_raw)
    except ValueError:
        allowed = ", ".join(sorted(k.value for k in WorkflowStepKind))
        return (
            None,
            f"step {index} ({id_raw!r}): unknown step kind {kind_raw!r} (choose from {allowed})",
        )

    label = f"step {index} ({id_raw!r})"
    params, error = _PARAM_PARSERS[kind](raw, label=label)
    if params is None:
        return None, error
    return WorkflowStep(id=id_raw, kind=kind, params=params), None


def validate_workflow_document(raw: object) -> tuple[Workflow | None, str | None]:
    """Validate an already-TOML-parsed document against the workflow schema.

    Performs no I/O of any kind -- pure structural/type/range validation.
    """
    if not isinstance(raw, dict):
        return None, "workflow document must be a TOML table"

    unknown = set(raw.keys()) - _TOP_LEVEL_KEYS
    if unknown:
        return None, f"unknown top-level key(s): {', '.join(sorted(unknown))}"

    schema_version_raw = raw.get("schema_version")
    if schema_version_raw is None:
        return None, "schema_version is required"
    if not isinstance(schema_version_raw, int) or isinstance(schema_version_raw, bool):
        return None, "schema_version must be an integer"
    if schema_version_raw != SUPPORTED_SCHEMA_VERSION:
        return None, (
            f"unsupported schema_version {schema_version_raw!r}; "
            f"only {SUPPORTED_SCHEMA_VERSION} is supported"
        )

    name_raw = raw.get("name")
    if name_raw is None:
        return None, "name is required"
    if not isinstance(name_raw, str) or not name_raw.strip():
        return None, "name must be a non-empty string"

    steps_raw = raw.get("steps")
    if steps_raw is None:
        return None, "at least one [[steps]] entry is required"
    if not isinstance(steps_raw, list):
        return None, "steps must be an array of tables ([[steps]])"
    if not (MIN_WORKFLOW_STEPS <= len(steps_raw) <= MAX_WORKFLOW_STEPS):
        return None, (
            f"steps count must be between {MIN_WORKFLOW_STEPS} and {MAX_WORKFLOW_STEPS}, "
            f"got {len(steps_raw)}"
        )

    steps: list[WorkflowStep] = []
    seen_ids: set[str] = set()
    for index, step_raw in enumerate(steps_raw, start=1):
        step, error = _parse_step(step_raw, index=index)
        if step is None:
            return None, error
        if step.id in seen_ids:
            return None, f"step {index}: duplicate step id {step.id!r}"
        seen_ids.add(step.id)
        steps.append(step)

    return Workflow(schema_version=schema_version_raw, name=name_raw, steps=tuple(steps)), None


def parse_workflow_file(path: Path) -> tuple[Workflow | None, str | None]:
    """Parse and validate ``path`` as a declarative workflow document.

    Mirrors ``core/config.py:parse_toml_file()``'s file-reading style (a
    plain ``tomllib.load()`` over ``Path.open("rb")``) rather than
    ``core/report_reader.py``'s hardened fd-safety path: a workflow file
    is a locally authored, explicitly supplied CLI argument at the same
    trust level as a configuration file, not adversarial input read on a
    remote report-ingestion path.
    """
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        return None, f"workflow file not found: {path}"
    except IsADirectoryError:
        return None, f"workflow file is a directory: {path}"
    except tomllib.TOMLDecodeError as exc:
        return None, f"workflow file is not valid TOML: {exc}"
    except OSError as exc:
        return None, f"workflow file could not be read: {exc}"

    return validate_workflow_document(raw)
