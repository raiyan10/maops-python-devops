"""TOML parsing and schema validation for declarative workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from maops_pydevops.core.workflow_models import (
    DoctorStepParams,
    HealthHttpStepParams,
    HealthTcpStepParams,
    InventoryFilesystemStepParams,
    InventorySystemStepParams,
    LogsAnalyzeStepParams,
    ToolsInspectStepParams,
    WorkflowStepKind,
)
from maops_pydevops.core.workflow_parser import parse_workflow_file, validate_workflow_document


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_minimal_workflow(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "wf.toml",
        """
        schema_version = 1
        name = "minimal"

        [[steps]]
        id = "d1"
        kind = "doctor"
        """,
    )
    workflow, error = parse_workflow_file(path)
    assert error is None
    assert workflow is not None
    assert workflow.schema_version == 1
    assert workflow.name == "minimal"
    assert len(workflow.steps) == 1
    assert workflow.steps[0].kind is WorkflowStepKind.DOCTOR
    assert isinstance(workflow.steps[0].params, DoctorStepParams)


def test_every_supported_step_kind_parses(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "wf.toml",
        """
        schema_version = 1
        name = "all kinds"

        [[steps]]
        id = "s1"
        kind = "doctor"

        [[steps]]
        id = "s2"
        kind = "tools_inspect"
        tools = ["git"]

        [[steps]]
        id = "s3"
        kind = "inventory_system"

        [[steps]]
        id = "s4"
        kind = "inventory_filesystem"
        path = "."

        [[steps]]
        id = "s5"
        kind = "logs_analyze"
        path = "app.log"

        [[steps]]
        id = "s6"
        kind = "health_http"
        urls = ["http://127.0.0.1:8080/health"]

        [[steps]]
        id = "s7"
        kind = "health_tcp"
        targets = ["127.0.0.1:5432"]
        """,
    )
    workflow, error = parse_workflow_file(path)
    assert error is None
    assert workflow is not None
    assert len(workflow.steps) == 7
    kinds = [step.kind for step in workflow.steps]
    assert kinds == [
        WorkflowStepKind.DOCTOR,
        WorkflowStepKind.TOOLS_INSPECT,
        WorkflowStepKind.INVENTORY_SYSTEM,
        WorkflowStepKind.INVENTORY_FILESYSTEM,
        WorkflowStepKind.LOGS_ANALYZE,
        WorkflowStepKind.HEALTH_HTTP,
        WorkflowStepKind.HEALTH_TCP,
    ]
    assert isinstance(workflow.steps[1].params, ToolsInspectStepParams)
    assert workflow.steps[1].params.tools == ("git",)
    assert isinstance(workflow.steps[2].params, InventorySystemStepParams)
    assert isinstance(workflow.steps[3].params, InventoryFilesystemStepParams)
    assert workflow.steps[3].params.path == "."
    assert isinstance(workflow.steps[4].params, LogsAnalyzeStepParams)
    assert workflow.steps[4].params.path == "app.log"
    assert isinstance(workflow.steps[5].params, HealthHttpStepParams)
    assert workflow.steps[5].params.urls == ("http://127.0.0.1:8080/health",)
    assert isinstance(workflow.steps[6].params, HealthTcpStepParams)
    assert workflow.steps[6].params.targets == ("127.0.0.1:5432",)


def test_unknown_step_kind_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "rm_rf"}]}
    )
    assert workflow is None
    assert error is not None
    assert "unknown step kind" in error


def test_duplicate_step_id_rejected() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "doctor"}, {"id": "a", "kind": "inventory_system"}],
        }
    )
    assert workflow is None
    assert error is not None
    assert "duplicate" in error


def test_missing_schema_version_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"name": "x", "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None
    assert "schema_version" in error


def test_unsupported_schema_version_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 2, "name": "x", "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None
    assert "schema_version" in error


def test_schema_version_wrong_type_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": "1", "name": "x", "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None


def test_missing_name_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None
    assert "name" in error


def test_empty_name_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "  ", "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None


def test_empty_steps_rejected() -> None:
    workflow, error = validate_workflow_document({"schema_version": 1, "name": "x", "steps": []})
    assert workflow is None
    assert error is not None
    assert "steps count" in error


def test_missing_steps_rejected() -> None:
    workflow, error = validate_workflow_document({"schema_version": 1, "name": "x"})
    assert workflow is None
    assert error is not None


def test_32_step_boundary_accepted() -> None:
    steps = [{"id": f"s{i}", "kind": "doctor"} for i in range(32)]
    workflow, error = validate_workflow_document({"schema_version": 1, "name": "x", "steps": steps})
    assert error is None
    assert workflow is not None
    assert len(workflow.steps) == 32


def test_33_step_rejected_before_execution() -> None:
    steps = [{"id": f"s{i}", "kind": "doctor"} for i in range(33)]
    workflow, error = validate_workflow_document({"schema_version": 1, "name": "x", "steps": steps})
    assert workflow is None
    assert error is not None
    assert "steps count" in error


def test_wrong_toml_field_types_rejected() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "inventory_filesystem", "max_depth": "two"}],
        }
    )
    assert workflow is None
    assert error is not None
    assert "max_depth" in error


def test_unknown_top_level_field_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "doctor"}], "extra": True}
    )
    assert workflow is None
    assert error is not None
    assert "unknown top-level" in error


def test_unknown_step_field_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "doctor", "bogus": 1}]}
    )
    assert workflow is None
    assert error is not None
    assert "unknown field" in error


def test_step_missing_id_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None


def test_step_missing_kind_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a"}]}
    )
    assert workflow is None
    assert error is not None


def test_logs_analyze_missing_required_path_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "logs_analyze"}]}
    )
    assert workflow is None
    assert error is not None
    assert "path" in error


def test_health_http_missing_required_urls_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "health_http"}]}
    )
    assert workflow is None
    assert error is not None
    assert "urls" in error


def test_health_tcp_missing_required_targets_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": [{"id": "a", "kind": "health_tcp"}]}
    )
    assert workflow is None
    assert error is not None
    assert "targets" in error


def test_health_http_invalid_url_syntax_rejected_at_validation_time() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "health_http", "urls": ["not a valid url"]}],
        }
    )
    assert workflow is None
    assert error is not None


def test_health_http_userinfo_url_rejected_at_validation_time() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [
                {"id": "a", "kind": "health_http", "urls": ["http://user:pass@example.com/"]}
            ],
        }
    )
    assert workflow is None
    assert error is not None
    assert "userinfo" in error


def test_health_tcp_invalid_target_syntax_rejected_at_validation_time() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "health_tcp", "targets": ["not-a-target"]}],
        }
    )
    assert workflow is None
    assert error is not None


def test_tools_inspect_unsupported_tool_name_rejected() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "tools_inspect", "tools": ["rm"]}],
        }
    )
    assert workflow is None
    assert error is not None
    assert "unsupported tool" in error


def test_health_http_expect_status_min_greater_than_max_rejected() -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [
                {
                    "id": "a",
                    "kind": "health_http",
                    "urls": ["http://example.com/"],
                    "expect_status_min": 500,
                    "expect_status_max": 200,
                }
            ],
        }
    )
    assert workflow is None
    assert error is not None


def test_non_dict_workflow_document_rejected() -> None:
    workflow, error = validate_workflow_document(["not", "a", "table"])
    assert workflow is None
    assert error is not None


def test_non_dict_step_rejected() -> None:
    workflow, error = validate_workflow_document(
        {"schema_version": 1, "name": "x", "steps": ["nope"]}
    )
    assert workflow is None
    assert error is not None


def test_missing_workflow_file_produces_error(tmp_path: Path) -> None:
    workflow, error = parse_workflow_file(tmp_path / "nope.toml")
    assert workflow is None
    assert error is not None
    assert "not found" in error


def test_directory_as_workflow_file_produces_error(tmp_path: Path) -> None:
    workflow, error = parse_workflow_file(tmp_path)
    assert workflow is None
    assert error is not None


def test_malformed_toml_produces_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.toml", "this is not [ valid toml")
    workflow, error = parse_workflow_file(path)
    assert workflow is None
    assert error is not None
    assert "TOML" in error


def test_bool_schema_version_rejected() -> None:
    # bool is a subtype of int in Python -- must not be silently accepted
    # as schema_version 1 via `True == 1`.
    workflow, error = validate_workflow_document(
        {"schema_version": True, "name": "x", "steps": [{"id": "a", "kind": "doctor"}]}
    )
    assert workflow is None
    assert error is not None


@pytest.mark.parametrize("max_depth", [-1, 65])
def test_inventory_filesystem_max_depth_out_of_range_rejected(max_depth: int) -> None:
    workflow, error = validate_workflow_document(
        {
            "schema_version": 1,
            "name": "x",
            "steps": [{"id": "a", "kind": "inventory_filesystem", "max_depth": max_depth}],
        }
    )
    assert workflow is None
    assert error is not None
