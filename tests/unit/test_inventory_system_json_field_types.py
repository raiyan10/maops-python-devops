"""Exhaustive JSON field-type coverage for ``inventory system`` (Day 2
finding C's completeness bar, applied from day one to new report types).
"""

import json

import pytest

from maops_pydevops.cli import main


def test_json_field_types_complete(capsys: pytest.CaptureFixture[str]) -> None:
    main(["inventory", "system", "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert isinstance(data["version"], str)

    host = data["host"]
    assert host["hostname"] is None or isinstance(host["hostname"], str)
    assert isinstance(host["os_family"], str)
    assert isinstance(host["os_release"], str)
    assert host["os_version"] is None or isinstance(host["os_version"], str)
    assert isinstance(host["machine"], str)

    distribution = data["distribution"]
    assert distribution["id"] is None or isinstance(distribution["id"], str)
    assert distribution["name"] is None or isinstance(distribution["name"], str)
    assert distribution["version_id"] is None or isinstance(distribution["version_id"], str)
    assert isinstance(distribution["available"], bool)

    python = data["python"]
    assert isinstance(python["version"], str)
    assert isinstance(python["implementation"], str)
    assert isinstance(python["executable"], str)

    cpu = data["cpu"]
    assert cpu["logical_count"] is None or isinstance(cpu["logical_count"], int)
    for key in ("load_average_1m", "load_average_5m", "load_average_15m"):
        assert cpu[key] is None or isinstance(cpu[key], float)

    memory = data["memory"]
    assert isinstance(memory["available"], bool)
    for key in ("total_bytes", "available_bytes", "used_bytes"):
        assert memory[key] is None or isinstance(memory[key], int)
    assert memory["used_percent"] is None or isinstance(memory["used_percent"], float)

    uptime = data["uptime"]
    assert isinstance(uptime["available"], bool)
    assert uptime["seconds"] is None or isinstance(uptime["seconds"], (int, float))

    assert isinstance(data["issues"], list)
    for issue in data["issues"]:
        assert isinstance(issue["component"], str)
        assert issue["status"] in ("pass", "warn", "fail")
        assert isinstance(issue["detail"], str)

    assert data["overall"] in ("pass", "warn", "fail")


def test_json_explicit_nulls_for_unavailable_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unavailable optional fields are explicit JSON null, never omitted keys."""
    import maops_pydevops.cli as cli_module

    def _fake_build_report() -> object:
        from maops_pydevops.core.system_inventory import build_system_report

        return build_system_report(memory_os_family="Windows", uptime_os_family="Windows")

    monkeypatch.setattr(cli_module, "build_system_report", _fake_build_report)
    main(["inventory", "system", "--format", "json"])
    data = json.loads(capsys.readouterr().out)

    assert "total_bytes" in data["memory"]
    assert data["memory"]["total_bytes"] is None
    assert "seconds" in data["uptime"]
    assert data["uptime"]["seconds"] is None
    assert data["overall"] == "warn"
