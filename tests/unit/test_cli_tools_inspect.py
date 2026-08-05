"""``maops-py tools inspect`` status mapping, overall priority, and exit codes."""

import json
from pathlib import Path

import pytest

import maops_pydevops.commands.tools as tools_module
from maops_pydevops.cli import main
from maops_pydevops.core.runner import CommandResult, CommandSpec


@pytest.fixture(autouse=True)
def _isolated_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # tools inspect reads effective configuration via the real os.environ
    # by default; every test here must be isolated from the real invoking
    # user's HOME/XDG_CONFIG_HOME/MAOPS_PY_CONFIG_FILE so results never
    # depend on whatever configuration file happens to exist on the host.
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("MAOPS_PY_CONFIG_FILE", raising=False)


def _stub_run(exit_code: int) -> object:
    def _run(spec: CommandSpec) -> CommandResult:
        return CommandResult(
            argv=spec.argv,
            exit_code=exit_code,
            stdout=f"{spec.argv[0]} version 1.0",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=1,
            timed_out=False,
            failure_reason=None,
        )

    return _run


def test_all_pass_gives_overall_pass_and_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"
    assert data["tools"][0]["status"] == "pass"


def test_all_missing_gives_overall_warn_and_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: None)
    exit_code = main(["tools", "inspect", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "warn"
    assert all(tool["status"] == "warn" for tool in data["tools"])


def test_nonzero_exit_gives_overall_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(1))
    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "fail"
    assert data["tools"][0]["status"] == "fail"


def test_mixed_pass_and_missing_gives_overall_warn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _which(name: str) -> str | None:
        return "/usr/bin/git" if name == "git" else None

    monkeypatch.setattr(tools_module.shutil, "which", _which)
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    exit_code = main(["tools", "inspect", "git", "docker", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "warn"


def test_mixed_fail_and_missing_gives_overall_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _which(name: str) -> str | None:
        return "/usr/bin/git" if name == "git" else None

    monkeypatch.setattr(tools_module.shutil, "which", _which)
    monkeypatch.setattr(tools_module, "run_command", _stub_run(2))
    exit_code = main(["tools", "inspect", "git", "docker", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "fail"


def test_report_continues_after_one_tool_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _which(name: str) -> str | None:
        return f"/usr/bin/{name}"

    def _run(spec: CommandSpec) -> CommandResult:
        exit_code = 1 if "git" in spec.argv[0] else 0
        return CommandResult(
            argv=spec.argv,
            exit_code=exit_code,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=1,
            timed_out=False,
            failure_reason=None,
        )

    monkeypatch.setattr(tools_module.shutil, "which", _which)
    monkeypatch.setattr(tools_module, "run_command", _run)
    exit_code = main(["tools", "inspect", "git", "docker", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert len(data["tools"]) == 2
    assert data["tools"][0]["name"] == "git"
    assert data["tools"][0]["status"] == "fail"
    assert data["tools"][1]["name"] == "docker"
    assert data["tools"][1]["status"] == "pass"


def test_unsupported_tool_name_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["tools", "inspect", "helm"])
    assert exit_code == 2
    assert "helm" in capsys.readouterr().err


def test_unsupported_tool_name_never_calls_which_or_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail_which(name: str) -> str | None:
        raise AssertionError("must not resolve any tool when an unsupported name is present")

    monkeypatch.setattr(tools_module.shutil, "which", _fail_which)
    exit_code = main(["tools", "inspect", "git", "helm"])
    assert exit_code == 2


def test_no_args_after_removing_argparse_choices_still_inspects_all(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Regression test for a Python-version-dependent argparse interaction:
    # `nargs="*"` combined with `choices=` on this positional produced an
    # `ArgumentError: invalid choice: []` on Python 3.11 when no tool names
    # were supplied, even though the identical invocation worked on 3.12.
    # Tool-name validation is now performed in run_tools_inspect() instead,
    # so this must keep working regardless of argparse's own version-specific
    # empty-nargs-with-choices behavior.
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    exit_code = main(["tools", "inspect", "--format", "json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["tools"]) == 5


def test_explicit_format_overrides_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MAOPS_PY_OUTPUT_FORMAT", "text")
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    json.loads(out)  # must parse as JSON despite MAOPS_PY_OUTPUT_FORMAT=text


def test_explicit_timeout_overrides_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured_timeouts: list[float] = []

    def _run(spec: CommandSpec) -> CommandResult:
        captured_timeouts.append(spec.timeout_seconds)
        return CommandResult(
            argv=spec.argv,
            exit_code=0,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=1,
            timed_out=False,
            failure_reason=None,
        )

    monkeypatch.setenv("MAOPS_PY_COMMAND_TIMEOUT_SECONDS", "99")
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _run)
    main(["tools", "inspect", "git", "--timeout", "3", "--format", "json"])
    assert captured_timeouts == [3.0]


def test_config_derived_timeout_used_when_no_cli_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured_timeouts: list[float] = []

    def _run(spec: CommandSpec) -> CommandResult:
        captured_timeouts.append(spec.timeout_seconds)
        return CommandResult(
            argv=spec.argv,
            exit_code=0,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=1,
            timed_out=False,
            failure_reason=None,
        )

    monkeypatch.setenv("MAOPS_PY_COMMAND_TIMEOUT_SECONDS", "42")
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _run)
    main(["tools", "inspect", "git", "--format", "json"])
    assert captured_timeouts == [42.0]


def test_invalid_timeout_syntax_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools", "inspect", "git", "--timeout", "not-a-number"])
    assert exc_info.value.code == 2


def test_timeout_out_of_range_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools", "inspect", "git", "--timeout", "301"])
    assert exc_info.value.code == 2


def test_json_field_types(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    main(["tools", "inspect", "git", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data["version"], str)
    assert isinstance(data["configuration"]["path"], str)
    assert isinstance(data["configuration"]["command_timeout_seconds"], float)
    assert isinstance(data["configuration"]["max_output_bytes"], int)
    assert data["overall"] in ("pass", "warn", "fail")
    tool = data["tools"][0]
    assert isinstance(tool["name"], str)
    assert isinstance(tool["executable"], str)
    assert tool["status"] in ("pass", "warn", "fail")
    assert isinstance(tool["exit_code"], int)
    assert isinstance(tool["timed_out"], bool)
    assert isinstance(tool["duration_ms"], int)
    assert isinstance(tool["stdout"], str)
    assert isinstance(tool["stderr"], str)
    assert isinstance(tool["stdout_truncated"], bool)
    assert isinstance(tool["stderr_truncated"], bool)
    assert isinstance(tool["detail"], str)


def test_json_null_fields_for_missing_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: None)
    main(["tools", "inspect", "git", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    tool = data["tools"][0]
    assert tool["executable"] is None
    assert tool["exit_code"] is None
    assert tool["duration_ms"] is None
    assert tool["stdout"] is None
    assert tool["stderr"] is None
    assert tool["stdout_truncated"] is None
    assert tool["stderr_truncated"] is None
    assert tool["timed_out"] is False


def test_no_ansi_in_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    main(["tools", "inspect", "git", "--format", "json"])
    assert "\x1b" not in capsys.readouterr().out


def test_text_output_contains_overall_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    main(["tools", "inspect", "git", "--format", "text"])
    out = capsys.readouterr().out
    assert "Overall status: PASS" in out


def test_invalid_environment_value_fails_before_inspecting_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail_which(name: str) -> str | None:
        raise AssertionError("must not resolve any tool when configuration is invalid")

    monkeypatch.setenv("MAOPS_PY_COMMAND_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.setattr(tools_module.shutil, "which", _fail_which)
    exit_code = main(["tools", "inspect", "git"])
    assert exit_code == 1
    assert "Error" in capsys.readouterr().err


def test_timed_out_tool_reported_as_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import maops_pydevops.core.runner as runner_module

    def _run(spec: CommandSpec) -> CommandResult:
        return CommandResult(
            argv=spec.argv,
            exit_code=None,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=5000,
            timed_out=True,
            failure_reason=runner_module.RunFailureReason.TIMEOUT,
        )

    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _run)
    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["tools"][0]["status"] == "fail"
    assert data["tools"][0]["timed_out"] is True
    assert data["overall"] == "fail"


def test_permission_denied_tool_reported_as_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import maops_pydevops.core.runner as runner_module

    def _run(spec: CommandSpec) -> CommandResult:
        return CommandResult(
            argv=spec.argv,
            exit_code=None,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_ms=1,
            timed_out=False,
            failure_reason=runner_module.RunFailureReason.PERMISSION_DENIED,
        )

    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _run)
    exit_code = main(["tools", "inspect", "git", "--format", "json"])
    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["tools"][0]["status"] == "fail"
    assert data["overall"] == "fail"


def test_no_explicit_format_falls_back_to_effective_output_format(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MAOPS_PY_OUTPUT_FORMAT", "json")
    monkeypatch.setattr(tools_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools_module, "run_command", _stub_run(0))
    exit_code = main(["tools", "inspect", "git"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_invalid_format_choice_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["tools", "inspect", "git", "--format", "yaml"])
    assert exc_info.value.code == 2
