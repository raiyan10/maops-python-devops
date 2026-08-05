"""The authoritative build step normalizes archive permissions.

Building on a filesystem that always reports files as mode 0777 (e.g. a
WSL drvfs-mounted Windows path) leaks those permissions into the built
wheel and sdist unless normalized. This proves `make build` always
produces clean, policy-compliant modes: no world-writable entries, and
plain `.py` source files at exactly 0644.
"""

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD_WRITABLE = 0o002
EXPECTED_PY_MODE = 0o644
_BUILD_INPUT_FILES = ("pyproject.toml", "README.md", "LICENSE", "MANIFEST.in")


def _isolated_source_copy(tmp_path: Path) -> Path:
    """Copy the minimum package source into a tmp_path-scoped tree.

    ``python -m build --outdir <isolated>`` alone is not sufficient to
    make this test safe under a concurrent ``make build``/``make
    quality`` run: setuptools' sdist step still stages into a transient
    ``<repo_root>/maops_pydevops-<version>/`` directory (unaffected by
    ``--outdir``) and writes ``<repo_root>/src/maops_pydevops.egg-info/``
    in place, both keyed off the build's working directory -- two
    concurrent builds sharing ``REPO_ROOT`` as their cwd can still race
    on those transient paths. Building from an isolated copy of the
    source tree removes the shared working directory entirely.
    """
    source_copy = tmp_path / "source"
    (source_copy / "src").mkdir(parents=True)
    for name in _BUILD_INPUT_FILES:
        shutil.copy2(REPO_ROOT / name, source_copy / name)
    shutil.copytree(
        REPO_ROOT / "src" / "maops_pydevops",
        source_copy / "src" / "maops_pydevops",
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
    return source_copy


def _run_build(tmp_path: Path) -> Path:
    """Build into an isolated, tmp_path-scoped output directory, from an
    isolated, tmp_path-scoped copy of the source tree (see
    ``_isolated_source_copy``'s docstring for why both are necessary).
    """
    source_copy = _isolated_source_copy(tmp_path)
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir), str(source_copy)],
        cwd=source_copy,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    normalize_result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "normalize_archive_permissions.py"),
            str(dist_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert normalize_result.returncode == 0, normalize_result.stderr
    return dist_dir


def test_wheel_has_no_world_writable_entries_and_py_files_are_0644(tmp_path: Path) -> None:
    dist_dir = _run_build(tmp_path)
    (wheel,) = sorted(dist_dir.glob("*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            mode = (info.external_attr >> 16) & 0o777
            assert mode & WORLD_WRITABLE == 0, f"{info.filename} is world-writable ({oct(mode)})"
            if info.filename.endswith(".py"):
                assert mode == EXPECTED_PY_MODE, (
                    f"{info.filename} has mode {oct(mode)}, expected {oct(EXPECTED_PY_MODE)}"
                )


def test_sdist_has_no_world_writable_entries_and_py_files_are_0644(tmp_path: Path) -> None:
    dist_dir = _run_build(tmp_path)
    (sdist,) = sorted(dist_dir.glob("*.tar.gz"))

    with tarfile.open(sdist, "r:gz") as archive:
        for member in archive.getmembers():
            assert member.mode & WORLD_WRITABLE == 0, (
                f"{member.name} is world-writable ({oct(member.mode)})"
            )
            if member.isfile() and member.name.endswith(".py"):
                assert member.mode == EXPECTED_PY_MODE, (
                    f"{member.name} has mode {oct(member.mode)}, expected {oct(EXPECTED_PY_MODE)}"
                )
