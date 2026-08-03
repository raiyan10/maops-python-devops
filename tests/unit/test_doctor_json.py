"""doctor --format json produces one valid, schema-conformant JSON document."""

import json

import pytest

from maops_pydevops.cli import main


def test_doctor_json_is_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    main(["doctor", "--format", "json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert isinstance(data, dict)


def test_doctor_json_schema_field_types(capsys: pytest.CaptureFixture[str]) -> None:
    main(["doctor", "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert isinstance(data["version"], str)
    assert isinstance(data["python"], dict)
    assert isinstance(data["python"]["version"], str)
    assert isinstance(data["python"]["executable"], str)
    assert isinstance(data["python"]["supported"], bool)
    assert isinstance(data["platform"], dict)
    for key in ("system", "release", "architecture", "filesystem_encoding"):
        assert isinstance(data["platform"][key], str)
    assert isinstance(data["checks"], list)
    for check in data["checks"]:
        assert isinstance(check["name"], str)
        assert check["status"] in ("pass", "warn", "fail")
        assert isinstance(check["required"], bool)
        assert isinstance(check["detail"], str)
    assert data["overall"] in ("pass", "fail")


def test_doctor_json_no_ansi_escapes(capsys: pytest.CaptureFixture[str]) -> None:
    main(["doctor", "--format", "json"])
    out = capsys.readouterr().out
    assert "\x1b" not in out
