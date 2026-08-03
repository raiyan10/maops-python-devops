"""scripts/verify_wheel.py deterministically selects exactly one expected wheel."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_wheel.py"
EXPECTED_NAME = "maops_pydevops-0.1.0-py3-none-any.whl"


def _run(dist_dir: Path, expected_name: str = EXPECTED_NAME) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(dist_dir), expected_name],
        capture_output=True,
        text=True,
        check=False,
    )


def test_fails_when_no_wheel_present(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "found 0" in result.stderr


def test_succeeds_and_prints_path_for_exactly_one_matching_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / EXPECTED_NAME
    wheel.write_bytes(b"")

    result = _run(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == str(wheel)


def test_fails_when_the_single_wheel_has_the_wrong_name(tmp_path: Path) -> None:
    wheel = tmp_path / "maops_pydevops-0.0.9-py3-none-any.whl"
    wheel.write_bytes(b"")

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "expected wheel" in result.stderr


def test_fails_when_a_stale_extra_wheel_is_present(tmp_path: Path) -> None:
    (tmp_path / EXPECTED_NAME).write_bytes(b"")
    (tmp_path / "maops_pydevops-0.0.9-py3-none-any.whl").write_bytes(b"")

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "found 2" in result.stderr
