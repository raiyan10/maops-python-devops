"""Unknown commands, invalid format values, and no arguments are usage errors (exit 2)."""

import pytest

from maops_pydevops.cli import main


def test_unknown_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["bogus-command"])
    assert exc_info.value.code == 2


def test_invalid_format_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["doctor", "--format", "xml"])
    assert exc_info.value.code == 2


def test_no_arguments_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 2
    assert "usage" in capsys.readouterr().err.lower()
