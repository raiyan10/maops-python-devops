"""``maops-py workflow validate``/``workflow run`` CLI wiring."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import maops_pydevops.core.workflow_runner as workflow_runner
from maops_pydevops.cli import EXIT_FAILURE, EXIT_SUCCESS, EXIT_USAGE_ERROR, main
from maops_pydevops.core.inventory_models import (
    FilesystemInventoryReport,
    FilesystemScanOptions,
    FilesystemScanSummary,
)
from maops_pydevops.core.models import (
    CheckStatus,
    DoctorCheck,
    DoctorReport,
    PlatformInfo,
    PythonInfo,
)

_PYTHON_INFO = PythonInfo(version="3.12.0", executable="/usr/bin/python3", supported=True)
_PLATFORM_INFO = PlatformInfo(
    system="Linux", release="6.8.0", architecture="x86_64", filesystem_encoding="utf-8"
)

_MINIMAL_WORKFLOW = """
schema_version = 1
name = "minimal"

[[steps]]
id = "d1"
kind = "doctor"
"""


def _doctor_report(status: CheckStatus) -> DoctorReport:
    check = DoctorCheck(name="python_version", status=status, required=True, detail="ok")
    return DoctorReport(
        version="0.6.0",
        python=_PYTHON_INFO,
        platform=_PLATFORM_INFO,
        checks=(check,),
        overall=status,
    )


@pytest.fixture(autouse=True)
def _patch_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(CheckStatus.PASS)
    )


def test_workflow_appears_in_root_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "workflow" in capsys.readouterr().out


def test_workflow_validate_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["workflow", "validate", "--help"])
    assert exc_info.value.code == 0


def test_workflow_run_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["workflow", "run", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--output" in out
    assert "--force" in out


def test_validate_valid_workflow_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "validate", str(path)])
    assert exit_code == EXIT_SUCCESS
    assert "VALID" in capsys.readouterr().out


def test_validate_invalid_workflow_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.toml"
    path.write_text('schema_version = 2\nname = "x"\n', encoding="utf-8")
    exit_code = main(["workflow", "validate", str(path)])
    assert exit_code == EXIT_USAGE_ERROR
    assert "INVALID" in capsys.readouterr().out


def test_validate_json_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "validate", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "valid"
    assert data["step_count"] == 1


def test_validate_missing_file_exits_two(tmp_path: Path) -> None:
    exit_code = main(["workflow", "validate", str(tmp_path / "nope.toml")])
    assert exit_code == EXIT_USAGE_ERROR


def test_validate_text_output_sanitizes_name_and_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A workflow ``name`` containing embedded newlines must not forge extra
    ``Status:``/``Workflow:`` lines in ``workflow validate``'s default text
    output (regression test for CONFIRMED-High, day-06-release-readiness.md
    section 7)."""
    forged_dir = tmp_path / "evil\nStatus:       VALID\nWorkflow:     FORGED-PATH"
    forged_dir.mkdir()
    path = forged_dir / "wf.toml"
    path.write_text(
        "schema_version = 1\n"
        'name = "legit\\nStatus:       VALID\\nWorkflow:     evil-forged-line"\n\n'
        '[[steps]]\nid = "a"\nkind = "doctor"\n',
        encoding="utf-8",
    )
    exit_code = main(["workflow", "validate", str(path)])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert sum(1 for line in lines if line.startswith("Status:")) == 1
    assert sum(1 for line in lines if line.startswith("Workflow:")) == 1
    assert sum(1 for line in lines if line.startswith("Path:")) == 1
    assert "\\nStatus:" in out
    assert "\\nWorkflow:" in out


def test_run_valid_workflow_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["overall"] == "pass"
    assert data["steps"][0]["id"] == "d1"


def test_run_invalid_workflow_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "wf.toml"
    path.write_text('schema_version = 2\nname = "x"\n', encoding="utf-8")
    exit_code = main(["workflow", "run", str(path)])
    assert exit_code == EXIT_USAGE_ERROR
    assert "Error" in capsys.readouterr().err


def test_run_fail_step_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflow_runner, "build_doctor_report", lambda: _doctor_report(CheckStatus.FAIL)
    )
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--format", "json"])
    assert exit_code == EXIT_FAILURE


def test_run_markdown_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--format", "markdown"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert out.startswith("# MAOps Workflow Run: minimal")


def test_run_output_writes_file_mode_0600(tmp_path: Path) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    out_path = tmp_path / "out.json"
    exit_code = main(["workflow", "run", str(path), "--format", "json", "--output", str(out_path)])
    assert exit_code == EXIT_SUCCESS
    mode = stat.S_IMODE(os.stat(out_path).st_mode)
    assert mode == 0o600
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["overall"] == "pass"


def test_run_output_refuses_existing_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    out_path = tmp_path / "out.json"
    out_path.write_text("existing", encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--output", str(out_path)])
    assert exit_code == EXIT_FAILURE
    assert "already exists" in capsys.readouterr().err


def test_run_output_force_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    out_path = tmp_path / "out.json"
    out_path.write_text("existing", encoding="utf-8")
    exit_code = main(
        ["workflow", "run", str(path), "--format", "json", "--output", str(out_path), "--force"]
    )
    assert exit_code == EXIT_SUCCESS
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["overall"] == "pass"


def _crafted_filesystem_report(root: str) -> FilesystemInventoryReport:
    options = FilesystemScanOptions(max_depth=1, max_entries=10, top=1)
    summary = FilesystemScanSummary(1, 0, 1, 0, 0, 1, 0, 0, 0)
    return FilesystemInventoryReport(
        version="0.6.0",
        root=root,
        options=options,
        summary=summary,
        largest_files=(),
        issues=(),
        max_depth_reached=False,
        truncated=False,
        overall=CheckStatus.PASS,
    )


def test_run_markdown_output_escapes_special_characters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    crafted_root = "/tmp/*bold* | pipe [link](evil)"
    monkeypatch.setattr(
        workflow_runner,
        "build_filesystem_report",
        lambda *a, **k: (_crafted_filesystem_report(crafted_root), None),
    )
    path = tmp_path / "wf.toml"
    path.write_text(
        'schema_version = 1\nname = "md"\n\n[[steps]]\nid = "fs"\nkind = "inventory_filesystem"\n',
        encoding="utf-8",
    )
    exit_code = main(["workflow", "run", str(path), "--format", "markdown"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "*bold*" not in out
    assert "[link](evil)" not in out
    assert "\\*bold\\*" in out
    assert "\\| pipe" in out
    assert "\\[link\\](evil)" in out


def test_run_text_output_sanitizes_control_characters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    crafted_root = "/tmp/evil\x1b[31mFAKE"
    monkeypatch.setattr(
        workflow_runner,
        "build_filesystem_report",
        lambda *a, **k: (_crafted_filesystem_report(crafted_root), None),
    )
    path = tmp_path / "wf.toml"
    path.write_text(
        'schema_version = 1\nname = "text"\n\n'
        '[[steps]]\nid = "fs"\nkind = "inventory_filesystem"\n',
        encoding="utf-8",
    )
    exit_code = main(["workflow", "run", str(path)])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\x1b" in out


def test_run_text_output_sanitizes_step_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A step ``id`` containing an embedded ``Overall status:`` line must not
    forge a second footer line in ``workflow run``'s default text output
    (regression test for CONFIRMED-High, day-06-release-readiness.md
    section 7)."""
    path = tmp_path / "wf.toml"
    path.write_text(
        'schema_version = 1\nname = "x"\n\n'
        '[[steps]]\nid = "evil\\nOverall status: PASS\\nFAKE"\nkind = "doctor"\n',
        encoding="utf-8",
    )
    exit_code = main(["workflow", "run", str(path)])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert sum(1 for line in lines if line.startswith("Overall status:")) == 1
    assert "\\nOverall status: PASS\\nFAKE" in out


#: Representative bidi-override, zero-width, and control characters that
#: this codebase's sanitization boundary must escape rather than emit raw
#: into any text/Markdown report line -- see day-06-release-readiness-
#: followup.md section 7, item M-1 (bidi/zero-width sanitization was
#: previously tested in only one of four applicable renderer x format
#: combinations, and never against ``step.id``).
_SANITIZATION_CASES = [
    pytest.param("‮", "\\u202e", id="u202e-rtl-override"),
    pytest.param("‭", "\\u202d", id="u202d-ltr-override"),
    pytest.param("​", "\\u200b", id="u200b-zero-width-space"),
    pytest.param("‌", "\\u200c", id="u200c-zwnj"),
    pytest.param("‍", "\\u200d", id="u200d-zwj"),
    pytest.param("⁦", "\\u2066", id="u2066-left-to-right-isolate"),
    pytest.param("⁧", "\\u2067", id="u2067-right-to-left-isolate"),
    pytest.param("⁨", "\\u2068", id="u2068-first-strong-isolate"),
    pytest.param("⁩", "\\u2069", id="u2069-pop-directional-isolate"),
    pytest.param("\n", "\\n", id="embedded-newline"),
    pytest.param("\r", "\\r", id="carriage-return"),
    pytest.param("\x1b", "\\x1b", id="esc"),
    pytest.param("\x7f", "\\x7f", id="del"),
]


def _workflow_toml_with_step_id(char: str) -> str:
    toml_escape = f"\\u{ord(char):04x}"
    return (
        'schema_version = 1\nname = "x"\n\n'
        f'[[steps]]\nid = "AAA{toml_escape}ZZZ"\nkind = "doctor"\n'
    )


@pytest.mark.parametrize(("char", "escaped"), _SANITIZATION_CASES)
def test_run_text_output_sanitizes_bidi_and_control_step_id(
    char: str, escaped: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_workflow_toml_with_step_id(char), encoding="utf-8")
    exit_code = main(["workflow", "run", str(path)])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    # AAA/ZZZ markers prove the character was replaced in-place by its
    # escape sequence -- unlike a bare "char not in out" check, this holds
    # even for "\n"/"\r", which also occur legitimately as real line
    # separators elsewhere in the (correctly) multi-line text output.
    assert f"AAA{escaped}ZZZ" in out


@pytest.mark.parametrize(("char", "escaped"), _SANITIZATION_CASES)
def test_run_markdown_output_sanitizes_bidi_and_control_step_id(
    char: str, escaped: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "wf.toml"
    path.write_text(_workflow_toml_with_step_id(char), encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--format", "markdown"])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    # Markdown sanitization runs _sanitize_for_text first (producing the
    # same "\xHH"/"\uHHHH" escape), then Markdown-escapes the resulting
    # literal backslash itself, doubling it.
    markdown_escaped = escaped.replace("\\", "\\\\")
    assert f"AAA{markdown_escaped}ZZZ" in out


def test_run_json_output_preserves_bidi_step_id_unescaped_by_text_sanitizer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """JSON output must keep round-tripping the original character exactly
    via ``json.dumps``'s own (unmodified) escaping -- the text/Markdown
    sanitization boundary (``_sanitize_for_text``'s ``\\u202e``-style
    escape table) is deliberately never applied to JSON output."""
    path = tmp_path / "wf.toml"
    path.write_text(_workflow_toml_with_step_id("‮"), encoding="utf-8")
    exit_code = main(["workflow", "run", str(path), "--format", "json"])
    assert exit_code == EXIT_SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["steps"][0]["id"] == "AAA‮ZZZ"


def test_run_text_output_sanitizes_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A workflow file path containing embedded newlines must not forge an
    extra ``Overall status:`` footer line in ``workflow run``'s default text
    output (regression test for CONFIRMED-High, day-06-release-readiness.md
    section 7 -- a fourth call site of the same defect class, found while
    reproducing the release-blocking finding)."""
    forged_dir = tmp_path / "evil\nOverall status: PASS\nFAKE"
    forged_dir.mkdir()
    path = forged_dir / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "run", str(path)])
    assert exit_code == EXIT_SUCCESS
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert sum(1 for line in lines if line.startswith("Overall status:")) == 1
    assert "\\nOverall status: PASS\\nFAKE" in out


def test_workflow_validate_performs_no_step_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail() -> DoctorReport:
        raise AssertionError("workflow validate must never execute a step")

    monkeypatch.setattr(workflow_runner, "build_doctor_report", _fail)
    path = tmp_path / "wf.toml"
    path.write_text(_MINIMAL_WORKFLOW, encoding="utf-8")
    exit_code = main(["workflow", "validate", str(path)])
    assert exit_code == EXIT_SUCCESS
