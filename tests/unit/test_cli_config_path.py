"""``maops-py config path`` prints the resolved path and creates nothing."""

from pathlib import Path

import pytest

from maops_pydevops.cli import main


def test_prints_resolved_path_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "config.toml"))
    exit_code = main(["config", "path"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "config.toml")


def test_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "nested" / "config.toml"
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(target))
    main(["config", "path"])
    capsys.readouterr()
    assert not target.exists()
    assert not target.parent.exists()


def test_extra_arguments_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MAOPS_PY_CONFIG_FILE", str(tmp_path / "config.toml"))
    with pytest.raises(SystemExit) as exc_info:
        main(["config", "path", "unexpected"])
    assert exc_info.value.code == 2
