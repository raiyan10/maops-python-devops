"""CLI-facing orchestration for ``maops-py workflow validate``/``workflow run``.

Thin wiring only: parsing/validation lives in
``core/workflow_parser.py``, execution lives in
``core/workflow_runner.py``. ``build_workflow_validation_report()`` never
executes a step, opens a socket, or resolves a tool executable -- it only
parses and validates.
"""

from __future__ import annotations

import os
from pathlib import Path

from maops_pydevops.core.workflow_models import (
    WorkflowRunReport,
    WorkflowValidationReport,
    WorkflowValidationStatus,
)
from maops_pydevops.core.workflow_parser import parse_workflow_file
from maops_pydevops.core.workflow_runner import run_workflow
from maops_pydevops.version import get_version


def build_workflow_validation_report(path_arg: str) -> WorkflowValidationReport:
    """Parse and validate a workflow file. Performs no execution of any kind."""
    path = Path(path_arg)
    workflow, error = parse_workflow_file(path)
    if workflow is None:
        return WorkflowValidationReport(
            version=get_version(),
            path=str(path),
            status=WorkflowValidationStatus.INVALID,
            workflow_name=None,
            step_count=0,
            error=error,
        )
    return WorkflowValidationReport(
        version=get_version(),
        path=str(path),
        status=WorkflowValidationStatus.VALID,
        workflow_name=workflow.name,
        step_count=len(workflow.steps),
        error=None,
    )


def build_workflow_run_report(path_arg: str) -> tuple[WorkflowRunReport | None, str | None]:
    """Validate, then sequentially execute, a workflow file's declared steps.

    Returns ``(None, error)`` only for a schema/validation failure --
    checked entirely before any step runs. A fully executed workflow
    (even one containing FAIL steps) never returns ``None``. Relative
    step paths resolve against the workflow file's own directory (a pure
    lexical join via ``os.path.abspath``, never ``Path.resolve()``, and
    never a process ``os.chdir()``), not the process working directory.
    """
    path = Path(path_arg)
    workflow, error = parse_workflow_file(path)
    if workflow is None:
        return None, error

    workflow_dir = Path(os.path.abspath(path_arg)).parent
    report = run_workflow(workflow, workflow_path=str(path), workflow_dir=workflow_dir)
    return report, None
