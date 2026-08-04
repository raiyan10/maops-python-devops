"""validate_config_schema() rejects unknown keys, bool-as-numeric, and out-of-range values."""

from maops_pydevops.core.config import validate_config_schema


def test_unknown_key_is_rejected() -> None:
    result = validate_config_schema({"secret_token": "abc123"})
    assert result.valid is False
    assert result.values is None
    assert result.error is not None
    assert "secret_token" in result.error


def test_valid_document_accepts_all_known_keys() -> None:
    result = validate_config_schema(
        {"output_format": "json", "command_timeout_seconds": 30.0, "max_output_bytes": 4096}
    )
    assert result.valid is True
    assert result.values is not None
    assert result.values.output_format == "json"
    assert result.values.command_timeout_seconds == 30.0
    assert result.values.max_output_bytes == 4096


def test_partial_document_leaves_absent_keys_as_none() -> None:
    result = validate_config_schema({"output_format": "text"})
    assert result.valid is True
    assert result.values is not None
    assert result.values.output_format == "text"
    assert result.values.command_timeout_seconds is None
    assert result.values.max_output_bytes is None


def test_empty_document_is_valid() -> None:
    result = validate_config_schema({})
    assert result.valid is True
    assert result.values is not None
    assert result.values.output_format is None


def test_bad_output_format_string_is_rejected() -> None:
    result = validate_config_schema({"output_format": "yaml"})
    assert result.valid is False


def test_output_format_must_be_a_string() -> None:
    result = validate_config_schema({"output_format": 1})
    assert result.valid is False


def test_bool_rejected_as_command_timeout_seconds() -> None:
    result = validate_config_schema({"command_timeout_seconds": True})
    assert result.valid is False
    assert result.error is not None
    assert "boolean" in result.error


def test_bool_rejected_as_max_output_bytes() -> None:
    result = validate_config_schema({"max_output_bytes": False})
    assert result.valid is False
    assert result.error is not None
    assert "boolean" in result.error


def test_command_timeout_seconds_accepts_int() -> None:
    result = validate_config_schema({"command_timeout_seconds": 5})
    assert result.valid is True
    assert result.values is not None
    assert result.values.command_timeout_seconds == 5.0


def test_command_timeout_seconds_zero_is_rejected() -> None:
    result = validate_config_schema({"command_timeout_seconds": 0.0})
    assert result.valid is False


def test_command_timeout_seconds_negative_is_rejected() -> None:
    result = validate_config_schema({"command_timeout_seconds": -1.0})
    assert result.valid is False


def test_command_timeout_seconds_at_max_boundary_is_valid() -> None:
    result = validate_config_schema({"command_timeout_seconds": 300.0})
    assert result.valid is True


def test_command_timeout_seconds_over_max_is_rejected() -> None:
    result = validate_config_schema({"command_timeout_seconds": 300.1})
    assert result.valid is False


def test_max_output_bytes_below_minimum_is_rejected() -> None:
    result = validate_config_schema({"max_output_bytes": 1023})
    assert result.valid is False


def test_max_output_bytes_at_minimum_boundary_is_valid() -> None:
    result = validate_config_schema({"max_output_bytes": 1024})
    assert result.valid is True


def test_max_output_bytes_at_maximum_boundary_is_valid() -> None:
    result = validate_config_schema({"max_output_bytes": 1048576})
    assert result.valid is True


def test_max_output_bytes_above_maximum_is_rejected() -> None:
    result = validate_config_schema({"max_output_bytes": 1048577})
    assert result.valid is False


def test_max_output_bytes_must_be_an_integer_not_float() -> None:
    result = validate_config_schema({"max_output_bytes": 2048.5})
    assert result.valid is False
