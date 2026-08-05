"""--help and -h both exit 0 and print usage."""

import pytest

from maops_pydevops.cli import main


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_exits_zero(capsys: pytest.CaptureFixture[str], flag: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([flag])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_help_lists_all_top_level_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in ("doctor", "config", "tools", "inventory", "version"):
        assert command in out


def test_inventory_group_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "--help"])
    assert exc_info.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_inventory_system_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "system", "--help"])
    assert exc_info.value.code == 0


def test_inventory_filesystem_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["inventory", "filesystem", "--help"])
    assert exc_info.value.code == 0
