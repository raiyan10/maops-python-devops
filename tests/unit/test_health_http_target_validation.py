"""HTTP target validation, URL privacy, and target-string sanitization."""

from __future__ import annotations

from maops_pydevops.core.health_http import validate_http_target


def test_valid_http_url_accepted() -> None:
    target, error = validate_http_target("http://example.com/health", index=1)
    assert error is None
    assert target is not None
    assert target.scheme == "http"
    assert target.hostname == "example.com"
    assert target.port is None
    assert target.request_target == "/health"
    assert target.display_url == "http://example.com/health"


def test_valid_https_url_accepted() -> None:
    target, error = validate_http_target("https://example.com/health", index=1)
    assert error is None
    assert target is not None
    assert target.scheme == "https"


def test_unsupported_scheme_rejected() -> None:
    for scheme in ("ftp", "ws", "file", "gopher"):
        target, error = validate_http_target(f"{scheme}://example.com/", index=1)
        assert target is None, scheme
        assert error is not None, scheme


def test_userinfo_rejected() -> None:
    target, error = validate_http_target("http://user:password@example.com/", index=1)
    assert target is None
    assert error is not None
    assert "userinfo" in error


def test_userinfo_without_password_rejected() -> None:
    target, error = validate_http_target("http://user@example.com/", index=1)
    assert target is None
    assert error is not None


def test_missing_host_rejected() -> None:
    target, error = validate_http_target("http:///path", index=1)
    assert target is None
    assert error is not None


def test_control_character_rejected() -> None:
    target, error = validate_http_target("http://example.com/\x01path", index=1)
    assert target is None
    assert error is not None


def test_raw_whitespace_rejected() -> None:
    target, error = validate_http_target("http://example.com/pa th", index=1)
    assert target is None
    assert error is not None


def test_newline_rejected() -> None:
    target, error = validate_http_target("http://example.com/\npath", index=1)
    assert target is None
    assert error is not None


def test_explicit_port_preserved() -> None:
    target, error = validate_http_target("http://example.com:8080/health", index=1)
    assert error is None
    assert target is not None
    assert target.port == 8080
    assert target.display_url == "http://example.com:8080/health"


def test_no_explicit_port_never_synthesized() -> None:
    target, error = validate_http_target("http://example.com/health", index=1)
    assert error is None
    assert target is not None
    assert target.port is None
    assert ":80" not in target.display_url
    assert target.display_url == "http://example.com/health"


def test_port_zero_rejected() -> None:
    target, error = validate_http_target("http://example.com:0/", index=1)
    assert target is None
    assert error is not None


def test_port_out_of_range_rejected() -> None:
    target, error = validate_http_target("http://example.com:70000/", index=1)
    assert target is None
    assert error is not None


def test_ipv6_url_accepted_and_rebracketed_in_display() -> None:
    target, error = validate_http_target("http://[::1]:8080/health", index=1)
    assert error is None
    assert target is not None
    assert target.hostname == "::1"
    assert target.port == 8080
    assert target.display_url == "http://[::1]:8080/health"


def test_query_values_redacted_keys_preserved_in_order() -> None:
    raw = "https://example.com/health?token=abc&region=ap"
    target, error = validate_http_target(raw, index=1)
    assert error is None
    assert target is not None
    assert target.display_url == "https://example.com/health?token=[REDACTED]&region=[REDACTED]"
    # The real query string is preserved, unredacted, for the actual wire request.
    assert target.request_target == "/health?token=abc&region=ap"


def test_query_key_without_value_preserved_as_is() -> None:
    target, error = validate_http_target("http://example.com/health?flag", index=1)
    assert error is None
    assert target is not None
    assert target.display_url == "http://example.com/health?flag"


def test_fragment_never_appears_in_display_url_or_request_target() -> None:
    target, error = validate_http_target("http://example.com/health?x=1#secret-fragment", index=1)
    assert error is None
    assert target is not None
    assert "secret-fragment" not in target.display_url
    assert "secret-fragment" not in target.request_target
    assert "#" not in target.display_url
    assert "#" not in target.request_target


def test_original_raw_url_never_retained_on_target() -> None:
    raw = "https://example.com/health?token=super-secret-value"
    target, error = validate_http_target(raw, index=1)
    assert error is None
    assert target is not None
    # display_url (the only field ever reaching a report) is redacted --
    # request_target legitimately carries the real, unredacted query
    # string, since that's the actual value sent on the wire request; only
    # report/display serialization redacts it.
    assert "super-secret-value" not in target.display_url
    # The dataclass has no field capable of holding the original raw
    # string verbatim (e.g. a "raw" attribute) at all.
    assert not hasattr(target, "raw")


def test_unicode_path_preserved() -> None:
    target, error = validate_http_target("http://example.com/héllo", index=1)
    assert error is None
    assert target is not None
    assert target.request_target == "/héllo"


def test_percent_encoded_space_allowed() -> None:
    target, error = validate_http_target("http://example.com/a%20b", index=1)
    assert error is None
    assert target is not None
    assert target.request_target == "/a%20b"


def test_index_propagated_into_error_message() -> None:
    target, error = validate_http_target("ftp://example.com/", index=7)
    assert target is None
    assert error is not None
    assert "target 7" in error


def test_no_path_defaults_to_slash() -> None:
    target, error = validate_http_target("http://example.com", index=1)
    assert error is None
    assert target is not None
    assert target.request_target == "/"
