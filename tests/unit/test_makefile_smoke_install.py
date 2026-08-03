"""The smoke-install and build Makefile recipes stay offline-safe and deterministic."""

import re
from pathlib import Path

MAKEFILE_PATH = Path(__file__).resolve().parents[2] / "Makefile"


def _target_recipe(makefile_text: str, target: str) -> str:
    match = re.search(
        rf"^{re.escape(target)}:.*?\n(.*?)(?=\n\S|\Z)",
        makefile_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"target '{target}' not found in Makefile"
    return match.group(1)


def test_smoke_install_does_not_upgrade_pip() -> None:
    recipe = _target_recipe(MAKEFILE_PATH.read_text(encoding="utf-8"), "smoke-install")
    assert "--upgrade pip" not in recipe


def test_smoke_install_uses_no_network_index() -> None:
    recipe = _target_recipe(MAKEFILE_PATH.read_text(encoding="utf-8"), "smoke-install")
    assert "PIP_NO_INDEX=1" in recipe
    assert "--no-deps" in recipe


def test_smoke_install_does_not_select_wheel_by_glob_and_head() -> None:
    recipe = _target_recipe(MAKEFILE_PATH.read_text(encoding="utf-8"), "smoke-install")
    assert "ls dist" not in recipe
    assert "head -n1" not in recipe
    assert "scripts/verify_wheel.py" in recipe


def test_build_removes_stale_artifacts_before_building() -> None:
    recipe = _target_recipe(MAKEFILE_PATH.read_text(encoding="utf-8"), "build")
    lines = [line.strip() for line in recipe.splitlines() if line.strip()]
    clean_index = next(i for i, line in enumerate(lines) if line.startswith("rm -rf"))
    build_index = next(i for i, line in enumerate(lines) if "-m build" in line)
    assert clean_index < build_index

    clean_line = lines[clean_index]
    assert "dist" in clean_line
    assert "build" in clean_line
    assert "egg-info" in clean_line
    assert ".venv" not in clean_line
