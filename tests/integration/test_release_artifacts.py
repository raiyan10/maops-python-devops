"""The authoritative `make build` step leaves exactly one, correctly named wheel."""

import subprocess
from pathlib import Path

from maops_pydevops.version import get_version

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_make_build_produces_exactly_one_expected_wheel() -> None:
    result = subprocess.run(
        ["make", "build"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    dist_dir = REPO_ROOT / "dist"
    wheels = sorted(dist_dir.glob("*.whl"))
    expected_name = f"maops_pydevops-{get_version()}-py3-none-any.whl"
    assert [wheel.name for wheel in wheels] == [expected_name]
