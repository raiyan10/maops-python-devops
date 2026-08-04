"""tools inspect never touches the network, even with a real-looking subprocess call."""

import json
import socket
import stat
from pathlib import Path

import pytest

import maops_pydevops.commands.tools as tools_module
from maops_pydevops.cli import main


@pytest.fixture(autouse=True)
def _isolated_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)


def test_tools_inspect_makes_no_network_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: None)

    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 1


def test_terraform_checkpoint_is_disabled_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exercises the real run_command() path (not mocked) with a stub
    # "terraform" that fails unless CHECKPOINT_DISABLE=1 reaches the child
    # environment -- this is the case a which()-only mock cannot catch,
    # and the case that would have caught the missing-CHECKPOINT_DISABLE bug.
    stub = tmp_path / "terraform"
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$CHECKPOINT_DISABLE" != "1" ]; then\n'
        '  echo "would have made a network checkpoint call" >&2\n'
        "  exit 1\n"
        "fi\n"
        'echo "Terraform v1.9.0"\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    monkeypatch.setattr(tools_module.shutil, "which", lambda name: str(stub))

    exit_code = main(["tools", "inspect", "terraform", "--format", "json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tools"][0]["status"] == "pass"
