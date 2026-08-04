"""End-to-end ``tools inspect`` via a real subprocess, using a deterministic stub."""

import json
import stat
import subprocess
import sys
from pathlib import Path

FAKE_GIT_SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "smoke" / "fake-git"


def _install_fake_git(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "git"
    target.write_text(FAKE_GIT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _isolated_env(tmp_path: Path, bin_dir: Path) -> dict[str, str]:
    # PATH is *only* bin_dir -- deliberately excludes /usr/bin and friends,
    # so a real host-installed git/docker/etc. can never be found and mask
    # what this test is actually asserting about the stub (or its absence).
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {"PATH": str(bin_dir), "HOME": str(home)}


def test_tools_inspect_git_with_fake_git_on_path(tmp_path: Path) -> None:
    bin_dir = tmp_path / "fake-bin"
    _install_fake_git(bin_dir)

    env = _isolated_env(tmp_path, bin_dir)

    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "tools", "inspect", "git", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["overall"] == "pass"
    assert data["tools"][0]["name"] == "git"
    assert data["tools"][0]["status"] == "pass"
    assert "maops-py smoke-test stub" in data["tools"][0]["stdout"]


def test_tools_inspect_without_git_on_path_reports_warn(tmp_path: Path) -> None:
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = _isolated_env(tmp_path, empty_bin)

    result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "tools", "inspect", "git", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["overall"] == "warn"
    assert data["tools"][0]["status"] == "warn"


def test_tools_inspect_json_validates_via_json_tool(tmp_path: Path) -> None:
    bin_dir = tmp_path / "fake-bin"
    _install_fake_git(bin_dir)
    env = _isolated_env(tmp_path, bin_dir)

    inspect_result = subprocess.run(
        [sys.executable, "-m", "maops_pydevops", "tools", "inspect", "git", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    tool_check = subprocess.run(
        [sys.executable, "-m", "json.tool"],
        input=inspect_result.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tool_check.returncode == 0
