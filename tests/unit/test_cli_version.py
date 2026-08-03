"""--version flag and the version subcommand both print the version and exit 0."""

import pytest

from maops_pydevops.cli import main
from maops_pydevops.version import get_version


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()


def test_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == get_version()
