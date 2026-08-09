"""``maops-py health tcp`` CLI wiring: flags, bounds, exit codes, format precedence."""

from __future__ import annotations

import json
import socket

import pytest

import maops_pydevops.core.health_tcp as health_tcp
from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from maops_pydevops.core.health_tcp import _AttemptOutcome as TcpOutcome


def _ok(*args: object, **kwargs: object) -> TcpOutcome:
    return TcpOutcome(
        success=True,
        peer_ip="127.0.0.1",
        failure_reason=None,
        detail=None,
        duration_ms=1,
        retryable=False,
    )


def _fail(*args: object, **kwargs: object) -> TcpOutcome:
    return TcpOutcome(
        success=False,
        peer_ip=None,
        failure_reason=health_tcp.TcpFailureReason.CONNECTION_REFUSED,
        detail="connection refused",
        duration_ms=1,
        retryable=False,
    )


def test_health_tcp_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "tcp", "--help"])
    assert exc_info.value.code == 0
    assert "--timeout" in capsys.readouterr().out


def test_default_format_is_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _ok)
    exit_code = main(["health", "tcp", "127.0.0.1:3306"])
    assert exit_code == EXIT_SUCCESS
    assert "TCP Health Check" in capsys.readouterr().out


def test_json_format(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _ok)
    exit_code = main(["health", "tcp", "127.0.0.1:3306", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"
    assert data["protocol"] == "tcp"


def test_overall_fail_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _fail)
    exit_code = main(["health", "tcp", "127.0.0.1:3306", "--retries", "0", "--format", "json"])
    assert exit_code == EXIT_FAILURE


def test_invalid_format_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "tcp", "127.0.0.1:3306", "--format", "xml"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_missing_target_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "tcp"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


@pytest.mark.parametrize(
    ("flag", "bad_value"),
    [
        ("--timeout", "abc"),
        ("--timeout", "0"),
        ("--timeout", "60.1"),
        ("--retries", "-1"),
        ("--retries", "6"),
        ("--retry-delay", "-0.1"),
        ("--retry-delay", "30.1"),
        ("--workers", "0"),
        ("--workers", "33"),
    ],
)
def test_bounded_flags_invalid_syntax_and_range(flag: str, bad_value: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "tcp", "127.0.0.1:3306", flag, bad_value])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_invalid_target_syntax_exits_two() -> None:
    exit_code = main(["health", "tcp", "not-a-valid-target"])
    assert exit_code == EXIT_USAGE_ERROR


def test_port_range_rejected_exits_two() -> None:
    exit_code = main(["health", "tcp", "example.com:80-90"])
    assert exit_code == EXIT_USAGE_ERROR


def test_cidr_rejected_exits_two() -> None:
    exit_code = main(["health", "tcp", "10.0.0.0/24"])
    assert exit_code == EXIT_USAGE_ERROR


def test_101_targets_rejected_before_any_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("no connection may be attempted for an invalid invocation")

    monkeypatch.setattr(socket, "create_connection", _forbidden)
    targets = [f"127.0.0.1:{1000 + i}" for i in range(101)]
    exit_code = main(["health", "tcp", *targets])
    assert exit_code == EXIT_USAGE_ERROR


def test_100_targets_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _ok)
    targets = [f"127.0.0.1:{1000 + i}" for i in range(100)]
    exit_code = main(["health", "tcp", *targets, "--format", "json"])
    assert exit_code == EXIT_SUCCESS


def test_multiple_targets_ordered_in_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(health_tcp, "_perform_tcp_attempt", _ok)
    exit_code = main(
        ["health", "tcp", "a.example:1", "b.example:2", "c.example:3", "--format", "json"]
    )
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    targets = [result["target"] for result in data["results"]]
    assert targets == ["a.example:1", "b.example:2", "c.example:3"]


def test_root_version_precedence_still_works_with_complete_health_tcp_path() -> None:
    # "health tcp TARGET" is a *complete* subcommand path (unlike "health"
    # alone), so parser.parse_args() succeeds and --version short-circuits
    # before dispatch ever runs -- no network access is attempted.
    assert main(["--version", "health", "tcp", "127.0.0.1:1"]) == EXIT_SUCCESS
