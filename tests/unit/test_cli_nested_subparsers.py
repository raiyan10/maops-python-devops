"""Nested ``config``/``tools`` subparser groups require a leaf subcommand."""

import pytest

from maops_pydevops.cli import main


def test_bare_config_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["config"])
    assert exc_info.value.code == 2


def test_bare_tools_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools"])
    assert exc_info.value.code == 2


def test_bare_inventory_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory"])
    assert exc_info.value.code == 2


def test_top_level_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_config_group_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "--help"])
    assert exc_info.value.code == 0


def test_config_show_leaf_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "show", "--help"])
    assert exc_info.value.code == 0


def test_tools_group_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools", "--help"])
    assert exc_info.value.code == 0


def test_tools_inspect_leaf_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools", "inspect", "--help"])
    assert exc_info.value.code == 0


def test_inventory_group_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "--help"])
    assert exc_info.value.code == 0


def test_inventory_system_leaf_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "system", "--help"])
    assert exc_info.value.code == 0


def test_inventory_filesystem_leaf_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", "--help"])
    assert exc_info.value.code == 0


def test_unknown_top_level_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["bogus-command"])
    assert exc_info.value.code == 2
