"""Detection, normalization, and aggregation of ``maops-py`` JSON reports.

``build_aggregate_report()`` is the sole entry point used by
``commands/report.py`` (external report files, read via
``core/report_reader.py``) and ``core/workflow_runner.py`` (an in-memory
report produced by a workflow step's own ``build_*_report()`` call, via
its already-typed ``to_dict()``). Report-kind detection is purely
structural (a fixed set of distinguishing keys per kind, checked in a
fixed order) -- there is no generic "any JSON object with an ``overall``
field is accepted" fallback, matching the project's "do not heuristically
accept arbitrary JSON objects" requirement.
"""

from __future__ import annotations

from collections.abc import Sequence

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.report_models import (
    AggregateOptions,
    AggregateReport,
    AggregateSummary,
    NormalizedReport,
    ReportKind,
    ReportMetric,
)
from maops_pydevops.core.report_reader import (
    MAX_REPORT_COUNT,
    MAX_REPORT_FILE_BYTES,
    read_report_file,
)
from maops_pydevops.version import get_version

MIN_REPORTS = 1


def _str_field(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def _dict_field(raw: dict[str, object], key: str) -> dict[str, object] | None:
    value = raw.get(key)
    return value if isinstance(value, dict) else None


def _list_field(raw: dict[str, object], key: str) -> list[object] | None:
    value = raw.get(key)
    return value if isinstance(value, list) else None


def _bool_field(raw: dict[str, object], key: str) -> bool | None:
    value = raw.get(key)
    return value if isinstance(value, bool) else None


def _int_field(raw: dict[str, object], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _status_field(raw: dict[str, object], key: str = "overall") -> CheckStatus | None:
    value = raw.get(key)
    if not isinstance(value, str):
        return None
    try:
        return CheckStatus(value)
    except ValueError:
        return None


def _count_statuses(items: Sequence[object]) -> tuple[int, int, int] | None:
    """Count pass/warn/fail among a list of dicts each with a ``status`` key."""
    passed = warned = failed = 0
    for item in items:
        if not isinstance(item, dict):
            return None
        status = _status_field(item, "status")
        if status is None:
            return None
        if status is CheckStatus.PASS:
            passed += 1
        elif status is CheckStatus.WARN:
            warned += 1
        else:
            failed += 1
    return passed, warned, failed


def _detect_kind(raw: dict[str, object]) -> ReportKind | None:
    """Structurally classify a parsed JSON document into a supported report kind.

    Each branch requires a combination of keys unique to exactly one
    ``maops-py`` report schema -- no schema in this package shares its
    full distinguishing key set with another.
    """
    if "protocol" in raw and "results" in raw and "options" in raw:
        protocol = raw.get("protocol")
        if protocol == "http":
            return ReportKind.HEALTH_HTTP
        if protocol == "tcp":
            return ReportKind.HEALTH_TCP
        return None
    if "checks" in raw and "platform" in raw and "python" in raw:
        return ReportKind.DOCTOR
    if "configuration" in raw and "tools" in raw:
        return ReportKind.TOOLS_INSPECT
    if (
        "host" in raw
        and "distribution" in raw
        and "cpu" in raw
        and "memory" in raw
        and "uptime" in raw
    ):
        return ReportKind.INVENTORY_SYSTEM
    if "root" in raw and "largest_files" in raw and "max_depth_reached" in raw:
        return ReportKind.INVENTORY_FILESYSTEM
    if "path" in raw and "events" in raw and "line_limit_reached" in raw:
        return ReportKind.LOGS_PARSE
    if "path" in raw and "severity_counts" in raw and "top_signatures" in raw:
        return ReportKind.LOGS_ANALYZE
    return None


def _normalize_doctor(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    checks = _list_field(raw, "checks")
    if version is None or overall is None or checks is None:
        return None, "malformed doctor report: missing or invalid required field"
    counts = _count_statuses(checks)
    if counts is None:
        return None, "malformed doctor report: invalid checks entry"
    passed, warned, failed = counts
    total = len(checks)
    headline = f"{total} check(s): {passed} pass, {warned} warn, {failed} fail"
    metrics = (
        ReportMetric("checks_total", str(total)),
        ReportMetric("checks_pass", str(passed)),
        ReportMetric("checks_warn", str(warned)),
        ReportMetric("checks_fail", str(failed)),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.DOCTOR,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_tools_inspect(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    tools = _list_field(raw, "tools")
    if version is None or overall is None or tools is None:
        return None, "malformed tools_inspect report: missing or invalid required field"
    counts = _count_statuses(tools)
    if counts is None:
        return None, "malformed tools_inspect report: invalid tools entry"
    passed, warned, failed = counts
    total = len(tools)
    headline = f"{total} tool(s) inspected: {passed} pass, {warned} warn, {failed} fail"
    metrics = (
        ReportMetric("tools_total", str(total)),
        ReportMetric("tools_pass", str(passed)),
        ReportMetric("tools_warn", str(warned)),
        ReportMetric("tools_fail", str(failed)),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.TOOLS_INSPECT,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_inventory_system(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    host = _dict_field(raw, "host")
    issues = _list_field(raw, "issues")
    if version is None or overall is None or host is None or issues is None:
        return None, "malformed inventory_system report: missing or invalid required field"
    hostname = host.get("hostname")
    hostname_str = hostname if isinstance(hostname, str) else "(unknown)"
    os_family = _str_field(host, "os_family") or "(unknown)"
    headline = f"host {hostname_str} ({os_family}): {len(issues)} issue(s)"
    metrics = (
        ReportMetric("hostname", hostname_str),
        ReportMetric("os_family", os_family),
        ReportMetric("issues", str(len(issues))),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.INVENTORY_SYSTEM,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_inventory_filesystem(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    root = _str_field(raw, "root")
    summary = _dict_field(raw, "summary")
    issues = _list_field(raw, "issues")
    truncated = _bool_field(raw, "truncated")
    if (
        version is None
        or overall is None
        or root is None
        or summary is None
        or issues is None
        or truncated is None
    ):
        return None, "malformed inventory_filesystem report: missing or invalid required field"
    scanned = _int_field(summary, "scanned_entries")
    if scanned is None:
        return None, "malformed inventory_filesystem report: invalid summary.scanned_entries"
    headline = f"{scanned} entries scanned under {root}: {len(issues)} issue(s)"
    metrics = (
        ReportMetric("root", root),
        ReportMetric("scanned_entries", str(scanned)),
        ReportMetric("issues", str(len(issues))),
        ReportMetric("truncated", str(truncated).lower()),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.INVENTORY_FILESYSTEM,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_logs_parse(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    path = _str_field(raw, "path")
    summary = _dict_field(raw, "summary")
    truncated = _bool_field(raw, "truncated")
    if version is None or overall is None or path is None or summary is None or truncated is None:
        return None, "malformed logs_parse report: missing or invalid required field"
    events_emitted = _int_field(summary, "events_emitted")
    malformed_lines = _int_field(summary, "malformed_lines")
    if events_emitted is None or malformed_lines is None:
        return None, "malformed logs_parse report: invalid summary fields"
    headline = f"{events_emitted} event(s) parsed from {path}"
    metrics = (
        ReportMetric("path", path),
        ReportMetric("events_emitted", str(events_emitted)),
        ReportMetric("malformed_lines", str(malformed_lines)),
        ReportMetric("truncated", str(truncated).lower()),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.LOGS_PARSE,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_logs_analyze(
    raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    path = _str_field(raw, "path")
    summary = _dict_field(raw, "summary")
    findings = _list_field(raw, "findings")
    truncated = _bool_field(raw, "truncated")
    if (
        version is None
        or overall is None
        or path is None
        or summary is None
        or findings is None
        or truncated is None
    ):
        return None, "malformed logs_analyze report: missing or invalid required field"
    events_parsed = _int_field(summary, "events_parsed")
    if events_parsed is None:
        return None, "malformed logs_analyze report: invalid summary.events_parsed"
    headline = f"{events_parsed} event(s) analyzed from {path}: {len(findings)} finding(s)"
    metrics = (
        ReportMetric("path", path),
        ReportMetric("events_parsed", str(events_parsed)),
        ReportMetric("findings", str(len(findings))),
        ReportMetric("truncated", str(truncated).lower()),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=ReportKind.LOGS_ANALYZE,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def _normalize_health(
    raw: dict[str, object], *, source_path: str, kind: ReportKind
) -> tuple[NormalizedReport | None, str | None]:
    version = _str_field(raw, "version")
    overall = _status_field(raw)
    summary = _dict_field(raw, "summary")
    if version is None or overall is None or summary is None:
        return None, f"malformed {kind.value} report: missing or invalid required field"
    targets = _int_field(summary, "targets")
    passed = _int_field(summary, "passed")
    warned = _int_field(summary, "warned")
    failed = _int_field(summary, "failed")
    if targets is None or passed is None or warned is None or failed is None:
        return None, f"malformed {kind.value} report: invalid summary fields"
    headline = f"{targets} target(s): {passed} passed, {warned} warned, {failed} failed"
    metrics = (
        ReportMetric("targets", str(targets)),
        ReportMetric("passed", str(passed)),
        ReportMetric("warned", str(warned)),
        ReportMetric("failed", str(failed)),
    )
    return (
        NormalizedReport(
            source_path=source_path,
            kind=kind,
            source_version=version,
            status=overall,
            headline=headline,
            metrics=metrics,
        ),
        None,
    )


def normalize_report(
    kind: ReportKind, raw: dict[str, object], *, source_path: str
) -> tuple[NormalizedReport | None, str | None]:
    """Normalize an already-kind-detected raw report document.

    Used both for externally supplied JSON (``report aggregate``, after
    :func:`detect_report_kind`) and for a workflow step's own in-memory
    report (``core/workflow_runner.py``, where the kind is already known
    from the step definition).
    """
    if kind is ReportKind.DOCTOR:
        return _normalize_doctor(raw, source_path=source_path)
    if kind is ReportKind.TOOLS_INSPECT:
        return _normalize_tools_inspect(raw, source_path=source_path)
    if kind is ReportKind.INVENTORY_SYSTEM:
        return _normalize_inventory_system(raw, source_path=source_path)
    if kind is ReportKind.INVENTORY_FILESYSTEM:
        return _normalize_inventory_filesystem(raw, source_path=source_path)
    if kind is ReportKind.LOGS_PARSE:
        return _normalize_logs_parse(raw, source_path=source_path)
    if kind is ReportKind.LOGS_ANALYZE:
        return _normalize_logs_analyze(raw, source_path=source_path)
    return _normalize_health(raw, source_path=source_path, kind=kind)


def detect_report_kind(raw: dict[str, object]) -> ReportKind | None:
    """Public wrapper around the structural report-kind detector."""
    return _detect_kind(raw)


def build_aggregate_report(
    paths: Sequence[str],
    *,
    max_reports: int = MAX_REPORT_COUNT,
    max_file_bytes: int = MAX_REPORT_FILE_BYTES,
) -> tuple[AggregateReport | None, str | None]:
    """Read, detect, normalize, and aggregate every report in ``paths``, in order.

    Returns ``(None, error)`` only for a usage/validation failure (report
    count out of bounds, a file that cannot be safely read, malformed
    JSON, or an unrecognized/malformed report body) -- checked, and
    short-circuiting, file by file in the exact order given. A fully built
    aggregate (even one containing FAIL entries) never returns ``None``;
    per-report operational status is folded into ``reports``/``overall``
    instead.
    """
    if not (MIN_REPORTS <= len(paths) <= max_reports):
        return (
            None,
            f"report count must be between {MIN_REPORTS} and {max_reports}, got {len(paths)}",
        )

    normalized: list[NormalizedReport] = []
    for path in paths:
        raw, _failure_reason, detail = read_report_file(path, max_bytes=max_file_bytes)
        if raw is None:
            return None, f"{path}: {detail}"
        kind = _detect_kind(raw)
        if kind is None:
            return None, f"{path}: unsupported or unrecognized MAOps report type"
        normalized_report, error = normalize_report(kind, raw, source_path=path)
        if normalized_report is None:
            return None, f"{path}: {error}"
        normalized.append(normalized_report)

    pass_count = sum(1 for report in normalized if report.status is CheckStatus.PASS)
    warn_count = sum(1 for report in normalized if report.status is CheckStatus.WARN)
    fail_count = sum(1 for report in normalized if report.status is CheckStatus.FAIL)

    if fail_count > 0:
        overall = CheckStatus.FAIL
    elif warn_count > 0:
        overall = CheckStatus.WARN
    else:
        overall = CheckStatus.PASS

    report = AggregateReport(
        version=get_version(),
        options=AggregateOptions(max_reports=max_reports, max_file_bytes=max_file_bytes),
        summary=AggregateSummary(
            reports=len(normalized),
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
        ),
        reports=tuple(normalized),
        overall=overall,
    )
    return report, None
