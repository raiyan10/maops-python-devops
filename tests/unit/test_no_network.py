"""The doctor command never touches the network."""

import socket

import pytest

from maops_pydevops.commands.doctor import build_report


def test_build_report_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)

    build_report()
