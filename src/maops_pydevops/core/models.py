"""Typed data models for doctor checks and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum


class CheckStatus(StrEnum):
    """Result of a single doctor check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class OutputFormat(StrEnum):
    """Supported rendering formats for the doctor command."""

    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class PythonInfo:
    """Interpreter facts reported by the doctor command."""

    version: str
    executable: str
    supported: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "executable": self.executable,
            "supported": self.supported,
        }


@dataclass(frozen=True)
class PlatformInfo:
    """Operating-system facts reported by the doctor command."""

    system: str
    release: str
    architecture: str
    filesystem_encoding: str

    def to_dict(self) -> dict[str, object]:
        return {
            "system": self.system,
            "release": self.release,
            "architecture": self.architecture,
            "filesystem_encoding": self.filesystem_encoding,
        }


@dataclass(frozen=True)
class DoctorCheck:
    """A single required or optional doctor check result."""

    name: str
    status: CheckStatus
    required: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "required": self.required,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DoctorReport:
    """The full doctor report: version, environment facts, and checks."""

    version: str
    python: PythonInfo
    platform: PlatformInfo
    checks: tuple[DoctorCheck, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "python": self.python.to_dict(),
            "platform": self.platform.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)


@dataclass(frozen=True)
class ToolInspectionResult:
    """The outcome of inspecting a single allowlisted tool."""

    name: str
    executable: str | None
    status: CheckStatus
    exit_code: int | None
    timed_out: bool
    duration_ms: int | None
    stdout: str | None
    stderr: str | None
    stdout_truncated: bool | None
    stderr_truncated: bool | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "executable": self.executable,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ToolsRunConfiguration:
    """The configuration values in effect for a ``tools inspect`` run."""

    path: str
    command_timeout_seconds: float
    max_output_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "command_timeout_seconds": self.command_timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
        }


@dataclass(frozen=True)
class ToolsInspectReport:
    """The full report rendered by ``maops-py tools inspect``."""

    version: str
    configuration: ToolsRunConfiguration
    tools: tuple[ToolInspectionResult, ...]
    overall: CheckStatus

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "configuration": self.configuration.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "overall": self.overall.value,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
