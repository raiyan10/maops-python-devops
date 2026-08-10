"""JSON field-type coverage for report-aggregate models."""

from __future__ import annotations

import json

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.report_models import (
    AggregateOptions,
    AggregateReport,
    AggregateSummary,
    NormalizedReport,
    ReportKind,
    ReportMetric,
)


def _sample_report() -> AggregateReport:
    normalized = NormalizedReport(
        source_path="doctor.json",
        kind=ReportKind.DOCTOR,
        source_version="0.6.0",
        status=CheckStatus.PASS,
        headline="1 check(s): 1 pass, 0 warn, 0 fail",
        metrics=(ReportMetric("checks_total", "1"),),
    )
    return AggregateReport(
        version="0.6.0",
        options=AggregateOptions(max_reports=50, max_file_bytes=5242880),
        summary=AggregateSummary(reports=1, pass_count=1, warn_count=0, fail_count=0),
        reports=(normalized,),
        overall=CheckStatus.PASS,
    )


def test_aggregate_report_json_field_types() -> None:
    data = json.loads(_sample_report().to_json())
    assert isinstance(data["version"], str)
    assert isinstance(data["options"], dict)
    assert isinstance(data["options"]["max_reports"], int)
    assert isinstance(data["options"]["max_file_bytes"], int)
    assert isinstance(data["summary"], dict)
    assert isinstance(data["summary"]["reports"], int)
    assert isinstance(data["summary"]["pass_count"], int)
    assert isinstance(data["summary"]["warn_count"], int)
    assert isinstance(data["summary"]["fail_count"], int)
    assert isinstance(data["reports"], list)
    entry = data["reports"][0]
    assert isinstance(entry["source_path"], str)
    assert isinstance(entry["kind"], str)
    assert isinstance(entry["source_version"], str)
    assert isinstance(entry["status"], str)
    assert isinstance(entry["headline"], str)
    assert isinstance(entry["metrics"], list)
    metric = entry["metrics"][0]
    assert isinstance(metric["label"], str)
    assert isinstance(metric["value"], str)
    assert isinstance(data["overall"], str)


def test_aggregate_report_json_is_deterministic() -> None:
    report = _sample_report()
    assert report.to_json() == report.to_json()


def test_aggregate_report_to_dict_never_uses_dataclasses_asdict() -> None:
    import inspect

    source = inspect.getsource(AggregateReport.to_dict)
    assert "asdict" not in source
