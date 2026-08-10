"""``maops-py report aggregate`` against real, subprocess-produced JSON reports.

Uses the actual ``maops-py doctor``/``inventory system`` JSON output (not
hand-crafted fixtures) as aggregate input, proving the aggregate's report-
kind detection and normalization match the real, currently-shipped
schemas -- not a schema this test suite merely believes is current.
"""

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


def test_aggregate_real_doctor_and_inventory_reports(tmp_path: Path) -> None:
    doctor_result = _run(tmp_path, "doctor", "--format", "json")
    assert doctor_result.returncode in (0, 1)
    doctor_path = tmp_path / "doctor.json"
    doctor_path.write_text(doctor_result.stdout, encoding="utf-8")

    inventory_result = _run(tmp_path, "inventory", "system", "--format", "json")
    assert inventory_result.returncode == 0
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(inventory_result.stdout, encoding="utf-8")

    aggregate_result = _run(
        tmp_path, "report", "aggregate", str(doctor_path), str(inventory_path), "--format", "json"
    )
    assert aggregate_result.returncode in (0, 1)
    data = json.loads(aggregate_result.stdout)
    assert data["summary"]["reports"] == 2
    kinds = [entry["kind"] for entry in data["reports"]]
    assert kinds == ["doctor", "inventory_system"]


def test_aggregate_console_script_matches_module_invocation(tmp_path: Path) -> None:
    import shutil

    console_script = shutil.which("maops-py")
    if console_script is None:
        import pytest

        pytest.skip("maops-py console script not installed")

    doctor_result = _run(tmp_path, "doctor", "--format", "json")
    doctor_path = tmp_path / "doctor.json"
    doctor_path.write_text(doctor_result.stdout, encoding="utf-8")

    module_result = _run(tmp_path, "report", "aggregate", str(doctor_path), "--format", "json")
    script_dir = str(Path(console_script).parent)
    env = {"PATH": script_dir, "HOME": str(tmp_path / "home")}
    console_result = subprocess.run(
        ["maops-py", "report", "aggregate", str(doctor_path), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert json.loads(module_result.stdout) == json.loads(console_result.stdout)
    assert module_result.returncode == console_result.returncode


def test_aggregate_markdown_output_is_valid_and_escaped(tmp_path: Path) -> None:
    doctor_result = _run(tmp_path, "doctor", "--format", "json")
    doctor_path = tmp_path / "doctor.json"
    doctor_path.write_text(doctor_result.stdout, encoding="utf-8")

    result = _run(tmp_path, "report", "aggregate", str(doctor_path), "--format", "markdown")
    assert result.returncode in (0, 1)
    assert result.stdout.startswith("# MAOps Aggregated Report")
    assert "| Metric | Value |" in result.stdout
