"""``maops-py health http`` CLI wiring: flags, bounds, exit codes, format precedence."""

from __future__ import annotations

import http.client
import json

import pytest

import maops_pydevops.core.health_http as health_http
from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from maops_pydevops.core.health_http import _AttemptOutcome as HttpOutcome


def _ok(*args: object, **kwargs: object) -> HttpOutcome:
    return HttpOutcome(
        success=True,
        http_status=200,
        peer_ip="127.0.0.1",
        failure_reason=None,
        detail=None,
        duration_ms=1,
        retryable=False,
    )


def _fail(*args: object, **kwargs: object) -> HttpOutcome:
    return HttpOutcome(
        success=False,
        http_status=None,
        peer_ip=None,
        failure_reason=health_http.HttpFailureReason.DNS_ERROR,
        detail="DNS resolution failed",
        duration_ms=1,
        retryable=False,
    )


def test_health_appears_in_root_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "health" in capsys.readouterr().out


def test_health_http_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "http", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--method" in out
    assert "--expect-status" in out


def test_default_format_is_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    exit_code = main(["health", "http", "http://example.com/"])
    assert exit_code == EXIT_SUCCESS
    assert "HTTP Health Check" in capsys.readouterr().out


def test_json_format(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    exit_code = main(["health", "http", "http://example.com/", "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"


def test_overall_fail_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _fail)
    exit_code = main(
        ["health", "http", "http://example.com/", "--retries", "0", "--format", "json"]
    )
    assert exit_code == EXIT_FAILURE


def test_invalid_format_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "http", "http://example.com/", "--format", "xml"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_invalid_method_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "http", "http://example.com/", "--method", "POST"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_missing_url_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "http"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


@pytest.mark.parametrize(
    ("flag", "bad_value"),
    [
        ("--timeout", "abc"),
        ("--timeout", "0"),
        ("--timeout", "60.1"),
        ("--timeout", "-1"),
        ("--retries", "abc"),
        ("--retries", "-1"),
        ("--retries", "6"),
        ("--retry-delay", "abc"),
        ("--retry-delay", "-0.1"),
        ("--retry-delay", "30.1"),
        ("--workers", "abc"),
        ("--workers", "0"),
        ("--workers", "33"),
        ("--expect-status", "99"),
        ("--expect-status", "600"),
        ("--expect-status", "abc"),
        ("--expect-status", "300-200"),
        ("--expect-status", "200,300"),
        ("--expect-status", "20-300"),
    ],
)
def test_bounded_flags_invalid_syntax_and_range(flag: str, bad_value: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["health", "http", "http://example.com/", flag, bad_value])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_bounded_flags_boundary_values_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    assert main(["health", "http", "http://example.com/", "--timeout", "60.0"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--timeout", "0.001"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--retries", "0"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--retries", "5"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--retry-delay", "0"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--retry-delay", "30.0"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--workers", "1"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--workers", "32"]) == EXIT_SUCCESS
    assert main(["health", "http", "http://example.com/", "--expect-status", "200"]) == EXIT_SUCCESS
    assert (
        main(["health", "http", "http://example.com/", "--expect-status", "100-599"])
        == EXIT_SUCCESS
    )


def test_userinfo_rejected_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["health", "http", "http://user:pass@example.com/"])
    assert exit_code == EXIT_USAGE_ERROR
    assert "userinfo" in capsys.readouterr().err


def test_unsupported_scheme_exits_two() -> None:
    exit_code = main(["health", "http", "ftp://example.com/"])
    assert exit_code == EXIT_USAGE_ERROR


def test_101_targets_rejected_before_any_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("no connection may be attempted for an invalid invocation")

    monkeypatch.setattr(http.client, "HTTPConnection", _forbidden)
    monkeypatch.setattr(http.client, "HTTPSConnection", _forbidden)
    urls = [f"http://example{i}.com/" for i in range(101)]
    exit_code = main(["health", "http", *urls])
    assert exit_code == EXIT_USAGE_ERROR


def test_100_targets_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    urls = [f"http://example{i}.com/" for i in range(100)]
    exit_code = main(["health", "http", *urls, "--format", "json"])
    assert exit_code == EXIT_SUCCESS


def test_multiple_targets_ordered_in_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    exit_code = main(
        [
            "health",
            "http",
            "http://a.example/",
            "http://b.example/",
            "http://c.example/",
            "--format",
            "json",
        ]
    )
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    targets = [result["target"] for result in data["results"]]
    assert targets == ["http://a.example/", "http://b.example/", "http://c.example/"]
    indexes = [result["index"] for result in data["results"]]
    assert indexes == [1, 2, 3]


def test_root_version_precedence_still_works_with_health_present() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version", "health"])
    assert exc_info.value.code == EXIT_USAGE_ERROR


def test_python_m_and_console_share_same_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # cli.main() is the single shared entry point for both -- this asserts
    # the dispatch table wiring rather than spawning a second process
    # (subprocess-level parity is covered in tests/integration/).
    monkeypatch.setattr(health_http, "_perform_http_attempt", _ok)
    assert main(["health", "http", "http://example.com/", "--format", "json"]) == EXIT_SUCCESS
