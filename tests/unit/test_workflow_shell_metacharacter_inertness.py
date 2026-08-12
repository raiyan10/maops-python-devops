"""Shell-looking workflow field values remain inert data, never command execution.

The workflow engine's headline architectural claim (``docs/workflow-
security.md``: "the workflow file is data, not code") was previously
hand-verified only by ad hoc adversarial scripts run during engineering
review, never pinned by a committed regression test (Day 6 test-review
L-4). These tests supply real shell metacharacter payloads as a
``logs_analyze`` step's ``path`` and prove, with a real filesystem canary
(a marker file the payload would create if it were ever actually passed
to a shell) plus a monkeypatched ``subprocess``/``os.system`` seam that
raises if called, that the payload is only ever treated as a literal,
nonexistent path string.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.workflow_models import (
    LogsAnalyzeStepParams,
    Workflow,
    WorkflowStep,
    WorkflowStepKind,
)
from maops_pydevops.core.workflow_runner import run_workflow

#: Each payload embeds a marker-file-creation attempt via a shell
#: metacharacter this codebase must never interpret. ``{canary}`` is
#: substituted with a fresh ``tmp_path``-scoped file per test.
_SHELL_METACHARACTER_PAYLOADS = [
    pytest.param("app.log; touch {canary}", id="semicolon"),
    pytest.param("app.log`touch {canary}`", id="backticks"),
    pytest.param("app.log$(touch {canary})", id="dollar-paren-command-substitution"),
    pytest.param("app.log | touch {canary}", id="pipe"),
    pytest.param("app.log > {canary}", id="redirect-out"),
    pytest.param("app.log < {canary}", id="redirect-in"),
    pytest.param("app.log && touch {canary}", id="and-and"),
]


def _disallow_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess/os.system invoked from workflow-supplied path data")

    monkeypatch.setattr(subprocess, "Popen", _fail)
    monkeypatch.setattr(subprocess, "run", _fail)
    monkeypatch.setattr(subprocess, "call", _fail)
    monkeypatch.setattr(os, "system", _fail)


@pytest.mark.parametrize("payload_template", _SHELL_METACHARACTER_PAYLOADS)
def test_shell_metacharacter_path_remains_inert(
    payload_template: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _disallow_subprocess(monkeypatch)
    canary = tmp_path / "PWNED_CANARY"
    payload = payload_template.format(canary=canary)

    step = WorkflowStep(
        id="logs",
        kind=WorkflowStepKind.LOGS_ANALYZE,
        params=LogsAnalyzeStepParams(path=payload),
    )
    workflow = Workflow(schema_version=1, name="canary", steps=(step,))

    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)

    assert not canary.exists(), "shell metacharacter payload was interpreted, not treated as data"
    assert len(report.steps) == 1
    result = report.steps[0]
    assert result.status is CheckStatus.FAIL
    assert result.error is not None
    assert payload in result.error


def test_dollar_brace_home_value_is_never_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``${HOME}`` inside a workflow field must survive as the four literal
    characters ``$``, ``{``, ``H``... -- never shell/env-expanded to the
    real invoking user's home directory."""
    _disallow_subprocess(monkeypatch)
    payload = "${HOME}/app.log"

    step = WorkflowStep(
        id="logs",
        kind=WorkflowStepKind.LOGS_ANALYZE,
        params=LogsAnalyzeStepParams(path=payload),
    )
    workflow = Workflow(schema_version=1, name="canary", steps=(step,))

    report = run_workflow(workflow, workflow_path="wf.toml", workflow_dir=tmp_path)

    assert len(report.steps) == 1
    result = report.steps[0]
    assert result.status is CheckStatus.FAIL
    assert result.error is not None
    # The resolved path is workflow_dir joined with the literal, unexpanded
    # "${HOME}/app.log" string -- never the real $HOME value.
    assert "${HOME}/app.log" in result.error
    real_home = os.environ.get("HOME")
    if real_home:
        assert real_home not in result.error
