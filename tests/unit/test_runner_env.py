"""run_command() sets a fixed noninteractive child env and never leaks it in the result."""

import sys

import pytest

from maops_pydevops.core.runner import CommandSpec, run_command


def test_fixed_env_overrides_present_in_child() -> None:
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import os; print(os.environ.get('LC_ALL'), os.environ.get('LANG'), "
            "os.environ.get('NO_COLOR'), os.environ.get('PAGER'), "
            "os.environ.get('GIT_PAGER'), os.environ.get('TERM'), "
            "os.environ.get('CHECKPOINT_DISABLE'))",
        ),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.stdout.strip() == "C C 1 cat cat dumb 1"


def test_checkpoint_disable_stops_terraforms_network_checkpoint_call() -> None:
    # Terraform's CLI performs an outbound "checkpoint" call on `version`
    # unless CHECKPOINT_DISABLE is set -- this locks in the specific env
    # var, independent of the combined-output assertion above.
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import os; print(os.environ.get('CHECKPOINT_DISABLE'))"),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.stdout.strip() == "1"


def test_rest_of_environment_is_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAOPS_PY_TEST_SENTINEL", "sentinel-value")
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import os; print(os.environ.get('MAOPS_PY_TEST_SENTINEL', ''))",
        ),
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )
    result = run_command(spec)
    assert result.stdout.strip() == "sentinel-value"


def test_command_result_has_no_environment_field() -> None:
    spec = CommandSpec(
        argv=(sys.executable, "-c", "pass"), timeout_seconds=5.0, max_output_bytes=65536
    )
    result = run_command(spec)
    assert not hasattr(result, "env")
    assert not hasattr(result, "environment")
