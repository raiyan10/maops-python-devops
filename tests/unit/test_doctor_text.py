"""doctor default output and explicit --format text produce the same shape."""

import pytest

from maops_pydevops.cli import main


@pytest.mark.parametrize("args", [["doctor"], ["doctor", "--format", "text"]])
def test_doctor_text_output(capsys: pytest.CaptureFixture[str], args: list[str]) -> None:
    main(args)
    out = capsys.readouterr().out
    assert "Doctor Report" in out
    assert "Version:" in out
    assert "Python version:" in out
    assert "Python executable:" in out
    assert "Operating system:" in out
    assert "Architecture:" in out
    assert "Filesystem encoding:" in out
    assert "Required checks:" in out
    assert "Optional tools:" in out
    assert "Overall status:" in out
