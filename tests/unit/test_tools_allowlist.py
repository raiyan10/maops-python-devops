"""build_inspect_report() uses fixed argv per tool and deduplicates repeats deterministically."""

from maops_pydevops.commands.tools import TOOL_ALLOWLIST, build_inspect_report
from maops_pydevops.core.models import CheckStatus
from maops_pydevops.core.runner import CommandResult, CommandSpec


def _fake_which(name: str) -> str | None:
    return f"/usr/bin/{name}"


def _fake_run(spec: CommandSpec) -> CommandResult:
    return CommandResult(
        argv=spec.argv,
        exit_code=0,
        stdout=f"{spec.argv[0]} version 1.0",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_ms=1,
        timed_out=False,
        failure_reason=None,
    )


def test_fixed_argv_used_per_tool() -> None:
    captured: list[tuple[str, ...]] = []

    def _capturing_run(spec: CommandSpec) -> CommandResult:
        captured.append(spec.argv)
        return _fake_run(spec)

    build_inspect_report(
        tool_names=["git"],
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=_fake_which,
        run=_capturing_run,
    )
    assert captured == [("/usr/bin/git", "--version")]


def test_kubectl_uses_client_flag() -> None:
    captured: list[tuple[str, ...]] = []

    def _capturing_run(spec: CommandSpec) -> CommandResult:
        captured.append(spec.argv)
        return _fake_run(spec)

    build_inspect_report(
        tool_names=["kubectl"],
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=_fake_which,
        run=_capturing_run,
    )
    assert captured == [("/usr/bin/kubectl", "version", "--client=true")]


def test_no_args_inspects_all_tools_in_allowlist_order() -> None:
    report = build_inspect_report(
        tool_names=None,
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=_fake_which,
        run=_fake_run,
    )
    assert [tool.name for tool in report.tools] == [name for name, _ in TOOL_ALLOWLIST]


def test_repeated_tool_names_are_deduplicated_in_canonical_order() -> None:
    report = build_inspect_report(
        tool_names=["docker", "git", "docker", "git"],
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=_fake_which,
        run=_fake_run,
    )
    assert [tool.name for tool in report.tools] == ["git", "docker"]


def test_input_order_does_not_affect_output_order() -> None:
    report = build_inspect_report(
        tool_names=["ansible", "git"],
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=_fake_which,
        run=_fake_run,
    )
    assert [tool.name for tool in report.tools] == ["git", "ansible"]


def test_missing_executable_never_calls_run() -> None:
    calls = []

    def _run_should_not_be_called(spec: CommandSpec) -> CommandResult:
        calls.append(spec)
        raise AssertionError("run() must not be called when the executable is missing")

    report = build_inspect_report(
        tool_names=["git"],
        version="0.2.0",
        timeout_seconds=10.0,
        max_output_bytes=65536,
        config_path="/tmp/config.toml",
        which=lambda name: None,
        run=_run_should_not_be_called,
    )
    assert calls == []
    assert report.tools[0].status is CheckStatus.WARN
    assert report.tools[0].executable is None
