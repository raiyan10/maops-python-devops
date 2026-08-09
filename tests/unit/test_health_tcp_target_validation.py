"""TCP target grammar validation: hostname:port, IPv4:port, [IPv6]:port."""

from __future__ import annotations

from maops_pydevops.core.health_tcp import validate_tcp_target


def test_hostname_port_accepted() -> None:
    target, error = validate_tcp_target("example.com:443", index=1)
    assert error is None
    assert target is not None
    assert target.host == "example.com"
    assert target.port == 443
    assert target.display == "example.com:443"


def test_ipv4_port_accepted() -> None:
    target, error = validate_tcp_target("127.0.0.1:3306", index=1)
    assert error is None
    assert target is not None
    assert target.host == "127.0.0.1"
    assert target.port == 3306


def test_bracketed_ipv6_port_accepted() -> None:
    target, error = validate_tcp_target("[::1]:8080", index=1)
    assert error is None
    assert target is not None
    assert target.host == "::1"
    assert target.port == 8080


def test_full_ipv6_bracketed_accepted() -> None:
    target, error = validate_tcp_target("[2001:db8::1]:443", index=1)
    assert error is None
    assert target is not None
    assert target.host == "2001:db8::1"


def test_unbracketed_ipv6_rejected() -> None:
    target, error = validate_tcp_target("::1:8080", index=1)
    assert target is None
    assert error is not None


def test_invalid_bracketed_ipv6_literal_rejected() -> None:
    target, error = validate_tcp_target("[not-an-ipv6]:8080", index=1)
    assert target is None
    assert error is not None


def test_missing_port_rejected() -> None:
    target, error = validate_tcp_target("example.com", index=1)
    assert target is None
    assert error is not None


def test_port_zero_rejected() -> None:
    target, error = validate_tcp_target("example.com:0", index=1)
    assert target is None
    assert error is not None


def test_port_65536_rejected() -> None:
    target, error = validate_tcp_target("example.com:65536", index=1)
    assert target is None
    assert error is not None


def test_port_65535_accepted() -> None:
    target, error = validate_tcp_target("example.com:65535", index=1)
    assert error is None
    assert target is not None
    assert target.port == 65535


def test_port_1_accepted() -> None:
    target, error = validate_tcp_target("example.com:1", index=1)
    assert error is None
    assert target is not None
    assert target.port == 1


def test_nonnumeric_port_rejected() -> None:
    target, error = validate_tcp_target("example.com:abc", index=1)
    assert target is None
    assert error is not None


def test_port_range_rejected() -> None:
    target, error = validate_tcp_target("example.com:80-90", index=1)
    assert target is None
    assert error is not None


def test_comma_separated_ports_rejected() -> None:
    target, error = validate_tcp_target("example.com:80,443", index=1)
    assert target is None
    assert error is not None


def test_cidr_rejected() -> None:
    target, error = validate_tcp_target("10.0.0.0/24:443", index=1)
    assert target is None
    assert error is not None


def test_cidr_without_port_rejected() -> None:
    target, error = validate_tcp_target("10.0.0.0/24", index=1)
    assert target is None
    assert error is not None


def test_control_character_rejected() -> None:
    target, error = validate_tcp_target("example.com:44\x013", index=1)
    assert target is None
    assert error is not None


def test_whitespace_rejected() -> None:
    target, error = validate_tcp_target("example .com:443", index=1)
    assert target is None
    assert error is not None


def test_index_propagated_into_error_message() -> None:
    target, error = validate_tcp_target("example.com", index=3)
    assert target is None
    assert error is not None
    assert "target 3" in error


def test_display_preserves_original_input_exactly() -> None:
    raw = "[::1]:8080"
    target, error = validate_tcp_target(raw, index=1)
    assert error is None
    assert target is not None
    assert target.display == raw
