"""Secret redaction: every documented pattern, case sensitivity, and bounds."""

from __future__ import annotations

import time

from maops_pydevops.core.log_redaction import redact_message


def test_bearer_token_redacted() -> None:
    text, changed = redact_message("bearer abc123.def-456")
    assert changed is True
    assert "abc123" not in text
    assert "[REDACTED]" in text


def test_authorization_bearer_redacted() -> None:
    text, changed = redact_message("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secretpart")
    assert changed is True
    assert "eyJhbGciOiJIUzI1NiJ9" not in text
    assert "Authorization:" in text
    assert "Bearer" in text


def test_password_redacted() -> None:
    text, changed = redact_message("password=hunter2")
    assert changed is True
    assert "hunter2" not in text
    assert text == "password=[REDACTED]"


def test_passwd_redacted() -> None:
    text, changed = redact_message("passwd: s3cr3t")
    assert changed is True
    assert "s3cr3t" not in text


def test_pwd_redacted() -> None:
    text, changed = redact_message("pwd=abc123")
    assert changed is True
    assert "abc123" not in text


def test_token_redacted() -> None:
    text, changed = redact_message("token: tok_abcdef123456")
    assert changed is True
    assert "tok_abcdef123456" not in text


def test_api_key_aliases_redacted() -> None:
    for text_in in ("api_key=sk-123456", "api-key: sk-123456", "apikey=sk-123456"):
        text, changed = redact_message(text_in)
        assert changed is True, text_in
        assert "sk-123456" not in text, text_in


def test_secret_redacted() -> None:
    text, changed = redact_message("secret=topsecretvalue")
    assert changed is True
    assert "topsecretvalue" not in text


def test_access_key_aliases_redacted() -> None:
    for text_in in ("access_key=AKIA1234567890", "access-key: AKIA0987654321"):
        text, changed = redact_message(text_in)
        assert changed is True, text_in
        assert "AKIA" not in text, text_in


def test_uri_userinfo_password_redacted() -> None:
    text, changed = redact_message("connecting to postgres://user:hunter2@dbhost:5432/mydb")
    assert changed is True
    assert "hunter2" not in text
    assert text == "connecting to postgres://user:[REDACTED]@dbhost:5432/mydb"


def test_multiple_secrets_in_one_message() -> None:
    text, changed = redact_message("password=first token=second secret=third")
    assert changed is True
    assert "first" not in text
    assert "second" not in text
    assert "third" not in text
    assert text.count("[REDACTED]") == 3


def test_case_insensitive_key_matching() -> None:
    text, changed = redact_message("PASSWORD=CaseSensitiveValue")
    assert changed is True
    assert "CaseSensitiveValue" not in text


def test_non_secret_text_unchanged() -> None:
    original = "this is a normal log message with no secrets at all"
    text, changed = redact_message(original)
    assert changed is False
    assert text == original


def test_bounded_behavior_on_long_line_completes_quickly() -> None:
    # Regression guard against catastrophic backtracking: a long,
    # adversarial-shaped line must redact in well under a second.
    long_line = ("password=" + "a" * 10000) * 5
    start = time.monotonic()
    text, changed = redact_message(long_line)
    elapsed = time.monotonic() - start
    assert changed is True
    assert elapsed < 2.0


def test_bounded_behavior_on_long_uri_without_at_sign() -> None:
    # Rule 2 (URI userinfo password) is the one pattern with a trailing
    # lookahead (?=@) -- specifically probe a long userinfo-shaped tail
    # with no "@" at all, so the lookahead never matches, confirming
    # this doesn't degrade to worse-than-linear time on that pattern.
    long_line = "connect to postgres://user:" + "x" * 100000
    start = time.monotonic()
    text, changed = redact_message(long_line)
    elapsed = time.monotonic() - start
    assert changed is False
    assert text == long_line
    assert elapsed < 2.0


def test_quotes_around_value_preserved() -> None:
    text, changed = redact_message('token: "tok_abcdef"')
    assert changed is True
    assert text == 'token: "[REDACTED]"'
