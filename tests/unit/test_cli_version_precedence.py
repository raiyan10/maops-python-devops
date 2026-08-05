"""``--version`` always short-circuits, even when a subcommand is also supplied."""

import pytest

from maops_pydevops.cli import main
from maops_pydevops.version import get_version


def test_version_before_subcommand_prints_only_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--version", "doctor"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()


def test_version_with_subcommand_never_runs_the_subcommand(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import maops_pydevops.cli as cli_module

    def _fail() -> int:
        raise AssertionError("doctor must not run when --version is present")

    monkeypatch.setattr(cli_module, "run_doctor", lambda output_format: _fail())
    exit_code = main(["--version", "doctor"])
    assert exit_code == 0


def test_version_after_subcommand_name_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--version"])
    assert exc_info.value.code == 2


def test_version_before_incomplete_tools_group_is_a_usage_error() -> None:
    """An incomplete two-level group (no leaf subcommand) fails argparse's own
    required-subparser validation before ``--version`` is ever inspected --
    the documented exception to the short-circuit rule (Day 2 finding D).
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["--version", "tools"])
    assert exc_info.value.code == 2


def test_version_before_incomplete_inventory_group_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version", "inventory"])
    assert exc_info.value.code == 2


def test_version_before_complete_inventory_subcommand_short_circuits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["--version", "inventory", "system"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()


def test_bare_version_flag_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()


def test_version_subcommand_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()
