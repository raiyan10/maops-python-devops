"""``maops-py workflow validate``/``workflow run`` as real subprocesses."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(home)}


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "maops_pydevops", *args],
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_env(tmp_path),
    )


_WORKFLOW_TOML = """
schema_version = 1
name = "integration workflow"

[[steps]]
id = "doc"
kind = "doctor"

[[steps]]
id = "sysinv"
kind = "inventory_system"

[[steps]]
id = "fsinv"
kind = "inventory_filesystem"
path = "."
max_depth = 1
top = 3
"""


def test_workflow_validate_and_run_end_to_end(tmp_path: Path) -> None:
    workflow_path = tmp_path / "wf.toml"
    workflow_path.write_text(_WORKFLOW_TOML, encoding="utf-8")

    validate_result = _run(tmp_path, "workflow", "validate", str(workflow_path), "--format", "json")
    assert validate_result.returncode == 0
    validate_data = json.loads(validate_result.stdout)
    assert validate_data["status"] == "valid"
    assert validate_data["step_count"] == 3

    run_result = _run(tmp_path, "workflow", "run", str(workflow_path), "--format", "json")
    assert run_result.returncode in (0, 1)
    run_data = json.loads(run_result.stdout)
    assert run_data["summary"]["steps"] == 3
    assert [step["id"] for step in run_data["steps"]] == ["doc", "sysinv", "fsinv"]
    # inventory_filesystem's relative "." path resolves against the
    # workflow file's own directory, not this test process's cwd.
    fs_step = run_data["steps"][2]
    metrics = {m["label"]: m["value"] for m in fs_step["metrics"]}
    assert metrics["root"] == str(tmp_path)


def test_workflow_relative_path_resolves_against_workflow_file_directory(tmp_path: Path) -> None:
    subdir = tmp_path / "workflows"
    subdir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "marker.txt").write_text("x", encoding="utf-8")

    workflow_path = subdir / "wf.toml"
    workflow_path.write_text(
        """
schema_version = 1
name = "relpath"

[[steps]]
id = "fs"
kind = "inventory_filesystem"
path = "../target"
""",
        encoding="utf-8",
    )
    result = _run(tmp_path, "workflow", "run", str(workflow_path), "--format", "json")
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    metrics = {m["label"]: m["value"] for m in data["steps"][0]["metrics"]}
    assert metrics["root"] == str(target_dir)


def test_workflow_console_script_matches_module_invocation(tmp_path: Path) -> None:
    import shutil

    console_script = shutil.which("maops-py")
    if console_script is None:
        import pytest

        pytest.skip("maops-py console script not installed")

    workflow_path = tmp_path / "wf.toml"
    workflow_path.write_text(
        """
schema_version = 1
name = "parity"

[[steps]]
id = "doc"
kind = "doctor"
""",
        encoding="utf-8",
    )
    # Both invocations must share the identical PATH: the workflow's
    # doctor step checks optional-tool presence (git/docker/...) against
    # PATH, so a broader PATH for one invocation than the other would make
    # their outputs legitimately differ for reasons unrelated to entry
    # point parity.
    script_dir = str(Path(console_script).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    module_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maops_pydevops",
            "workflow",
            "run",
            str(workflow_path),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    console_result = subprocess.run(
        ["maops-py", "workflow", "run", str(workflow_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert json.loads(module_result.stdout) == json.loads(console_result.stdout)
    assert module_result.returncode == console_result.returncode
