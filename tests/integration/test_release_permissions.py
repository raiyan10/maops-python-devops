"""The authoritative build step normalizes archive permissions.

Building on a filesystem that always reports files as mode 0777 (e.g. a
WSL drvfs-mounted Windows path) leaks those permissions into the built
wheel and sdist unless normalized. This proves `make build` always
produces clean, policy-compliant modes: no world-writable entries, and
plain `.py` source files at exactly 0644.
"""

import subprocess
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD_WRITABLE = 0o002
EXPECTED_PY_MODE = 0o644


def _run_build() -> None:
    result = subprocess.run(
        ["make", "build"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_wheel_has_no_world_writable_entries_and_py_files_are_0644() -> None:
    _run_build()
    (wheel,) = sorted((REPO_ROOT / "dist").glob("*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            mode = (info.external_attr >> 16) & 0o777
            assert mode & WORLD_WRITABLE == 0, f"{info.filename} is world-writable ({oct(mode)})"
            if info.filename.endswith(".py"):
                assert mode == EXPECTED_PY_MODE, (
                    f"{info.filename} has mode {oct(mode)}, expected {oct(EXPECTED_PY_MODE)}"
                )


def test_sdist_has_no_world_writable_entries_and_py_files_are_0644() -> None:
    _run_build()
    (sdist,) = sorted((REPO_ROOT / "dist").glob("*.tar.gz"))

    with tarfile.open(sdist, "r:gz") as archive:
        for member in archive.getmembers():
            assert member.mode & WORLD_WRITABLE == 0, (
                f"{member.name} is world-writable ({oct(member.mode)})"
            )
            if member.isfile() and member.name.endswith(".py"):
                assert member.mode == EXPECTED_PY_MODE, (
                    f"{member.name} has mode {oct(member.mode)}, expected {oct(EXPECTED_PY_MODE)}"
                )
