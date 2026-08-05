"""The authoritative build step leaves exactly one, correctly named wheel and a
clean sdist.
"""

import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from maops_pydevops.version import get_version

REPO_ROOT = Path(__file__).resolve().parents[2]
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
    return dist_dir


def test_make_build_produces_exactly_one_expected_wheel(tmp_path: Path) -> None:
    dist_dir = _run_build(tmp_path)
    wheels = sorted(dist_dir.glob("*.whl"))
    expected_name = f"maops_pydevops-{get_version()}-py3-none-any.whl"
    assert [wheel.name for wheel in wheels] == [expected_name]


def test_sdist_excludes_prunable_egg_info_metadata(tmp_path: Path) -> None:
    """MANIFEST.in's ``prune src/*.egg-info`` removes the five prunable
    egg-info files (Day 2 finding G). ``SOURCES.txt`` is unconditionally
    force-included by setuptools' own sdist/egg_info integration --
    verified empirically to survive even an explicit MANIFEST.in
    ``exclude`` directive targeting it directly -- so it and its
    containing directory entry are the only ``.egg-info`` members a
    standards-compliant sdist can ever have; see
    docs/engineering-reviews/day-02-release-readiness.md finding #2 and
    docs/architecture.md for the full evidence trail.
    """
    dist_dir = _run_build(tmp_path)
    (sdist,) = sorted(dist_dir.glob("*.tar.gz"))

    with tarfile.open(sdist, "r:gz") as archive:
        egg_info_members = sorted(name for name in archive.getnames() if ".egg-info" in name)

    prefix = f"maops_pydevops-{get_version()}/src/maops_pydevops.egg-info"
    assert egg_info_members == [prefix, f"{prefix}/SOURCES.txt"]
