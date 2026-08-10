# Day 6 v0.6.0 Report Aggregation and Workflow Architecture and Security Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Reviewer:** Independent engineering review, direct hands-on verification.
Every command, test run, and adversarial input in this document was
executed by the reviewing session itself against the real source on this
branch (Python 3.12.3, package built and installed into an isolated
scratch virtualenv via `make smoke-install`), including live loopback-only
network exercises against real, ephemeral `127.0.0.1` servers spun up for
this review, real subprocess invocations of the installed `maops-py`
executable, and monkeypatch-based instrumentation proving `workflow
validate` performs zero network/subprocess/cwd side effects. No public
internet host was ever contacted. No finding here is inferred, estimated,
or taken from the implementing session's own claims or docstrings.
**Date:** 2026-08-10
**Branch reviewed:** `feature/day-6-reports-workflows`
**Target release:** v0.6.0
**Scope:** The Day 6 delta only — `commands/report.py`, `commands/workflow.py`,
`core/report_models.py`, `core/report_reader.py`, `core/report_aggregate.py`,
`core/workflow_models.py`, `core/workflow_parser.py`, `core/workflow_runner.py`,
the `report`/`workflow` CLI surface in `cli.py`, the `render_report_aggregate_*`/
`render_workflow_*` additions to `core/output.py` (including the new
Unicode bidi/zero-width formatting-character and Markdown-escaping
sanitizers), `docs/aggregated-reports.md`, `docs/workflows.md`,
`docs/workflow-security.md`, and `scripts/smoke/workflow_smoke_check.py`.
Day 1–5 functionality is treated as regression-protected (full suite
re-run below confirms no regression) and was not re-audited from scratch,
except where Day 6 code newly reuses a Day 1–5 API
(`validate_http_target()`, `validate_tcp_target()`, `TOOL_ALLOWLIST`, the
five `build_*_report()` orchestration functions, and `commands/report.py`'s
atomic `write_report_output()`, which mirrors `core/config.py`'s
`init_config_file()` pattern established in v0.2.0).
**Review only. No implementation file or test was modified.** No commit,
push, merge, tag, or publish was performed as part of this review.

---

## Commands and live checks run

```
python -m pytest tests/unit tests/integration -q \
    --cov=maops_pydevops --cov-report=term-missing
python -m mypy src/maops_pydevops --strict
ruff check src tests
ruff format --check src tests
make smoke-install
```

Result: **1245 passed**, **98.49% overall coverage** (`commands/report.py`
93%, `commands/workflow.py` 100%, `core/report_aggregate.py` 99%,
`core/report_models.py` 100%, `core/report_reader.py` 96%,
`core/workflow_models.py` 100%, `core/workflow_parser.py` 95%,
`core/workflow_runner.py` 95%, `cli.py` 99% — the uncovered lines are
almost entirely narrow race-window branches in `report_reader.py`
(`FileNotFoundError`/oversized-on-reread after the initial `fstat()`) and
individual per-field success/failure return statements in
`workflow_parser.py`'s small validator helpers that are structurally
identical to, and exercised via, sibling call sites — every one of the
corresponding *behaviors* was independently reproduced by hand below).
**mypy --strict: no issues in 38 source files. ruff check: all checks
passed. ruff format --check: 175 files already formatted.**
`make smoke-install` (full wheel build → isolated venv install → CLI
smoke pass, including the new `report aggregate`/`workflow validate`/
`workflow run` steps and `scripts/smoke/workflow_smoke_check.py`'s real
loopback HTTP server + raw TCP listener exercise) **passed end to end,
exit 0.**

Plus a from-scratch, hand-written adversarial exercise (not a re-run of
the existing test suite) covering every item in the review brief:
malformed/empty/oversized/non-UTF-8 JSON, directory/symlink/FIFO report
inputs, arbitrary-JSON impersonation, report-count bounds (0, 1, 50, 51),
short-circuiting/order-preserving multi-file aggregation, PASS/WARN/FAIL
→ exit 0/0/1 derivation, `--output` atomicity/mode/`--force`/symlink-
refusal/missing-parent-directory/no-leftover-temp-file-on-failure/
deterministic-bytes behavior, shell metacharacters (`;`, `|`, `` ` ``,
`$(...)`, `${VAR}`, redirects) and path traversal in workflow step
fields proven to remain inert data (including a literal canary-file
creation attempt via a workflow step path, which never fired),
`schema_version` mismatch, 0/32/33-step boundary, duplicate step IDs,
unknown step kinds, wrong field types, unknown top-level/per-step keys,
huge integers, `nan`/`inf`/`-inf` float rejection, malformed TOML, deeply
nested TOML rejection, control characters in a workflow `name`, an
unsupported/arbitrary `tools_inspect` tool name, empty/whitespace-only
`name`/`id`, a monkeypatch-instrumented proof that `workflow validate`
never touches `socket.socket`/`socket.create_connection`/
`subprocess.Popen`/`subprocess.run`/`subprocess.call`/`os.system`/
`shutil.which`/`os.chdir` and creates no files, a real-subprocess proof
of sequential step ordering and that a `FAIL` step never discards a
later step's `PASS` result, a real-loopback-listener proof that
`inventory_filesystem`/`logs_analyze` relative paths resolve against the
workflow file's own directory (not the process cwd) when run from an
unrelated directory, and a symlinked-workflow-file proof that path
resolution uses the lexical parent of the CLI argument, never a
`realpath`-resolved target directory.

**Headline result: one real, reproducible finding — `workflow validate
--format text` forges extra report lines when a workflow's `name` field
contains control characters or a raw newline, because
`render_workflow_validate_text()` is missing the same
`_sanitize_for_text()` call every sibling renderer in this file
(including `render_workflow_run_text()`, which handles the equivalent
`name` field correctly) already applies.** No other Critical, High,
Medium, or Low finding survived hands-on verification — see below.

---

## Findings

### High

#### H-1: `workflow validate --format text` forges extra report lines via an unsanitized `name`/`path` field

- **File/function:** `src/maops_pydevops/core/output.py:575-586`,
  `render_workflow_validate_text()`.
- **Defect:** Every other Day 6 (and Day 4/5) text renderer in this file
  passes untrusted, externally sourced strings through
  `_sanitize_for_text()` before interpolating them into a line-oriented
  report — this is the documented, tested boundary that stops a crafted
  input from injecting literal newlines/control characters to forge
  additional report lines. `render_workflow_validate_text()` is the one
  renderer in the Day 6 delta that skips it for two fields:
  `report.workflow_name` (line 582, interpolated raw) and `report.path`
  (line 580, interpolated raw). Only `report.error` (line 584) is
  correctly sanitized in this function. By contrast, the sibling
  `render_workflow_run_text()` (`output.py:596-627`) sanitizes the
  equivalent `report.name` field correctly, and
  `tests/unit/test_cli_workflow.py::test_run_text_output_sanitizes_control_characters`
  exists specifically to pin that behavior for `workflow run` — there is
  no equivalent test for `workflow validate`, and this review's own
  hands-on check confirms none was needed to catch it: the gap is
  directly visible by inspection and directly reproducible at the CLI.
- **Reproduction:**
  ```bash
  printf 'schema_version = 1\nname = "legit\\nStatus:       VALID\\nWorkflow:     evil-forged-line\\n"\n[[steps]]\nid = "a"\nkind = "doctor"\n' > forge_name.toml
  maops-py workflow validate forge_name.toml --format text
  ```
- **Actual result:**
  ```
  MAOps Python DevOps Toolkit - Workflow Validation
  Version:      0.6.0
  Path:         forge_name.toml
  Status:       VALID
  Workflow:     legit
  Status:       VALID
  Workflow:     evil-forged-line

  Step count:   1
  Error:        (none)
  ```
  Two extra, attacker-authored lines (`Status:       VALID` and
  `Workflow:     evil-forged-line`) are injected into the report,
  indistinguishable in formatting from genuine output. `--format json`
  against the identical file is unaffected — `json.dumps` correctly
  escapes the embedded `\n` into the literal two-character sequence
  `\n` inside the JSON string, exactly as the `_sanitize_for_text`
  docstring already notes is true of JSON generally.
- **Expected result:** Matching every other renderer's contract, both
  fields should render as their control/formatting-character-escaped
  form, e.g. `Workflow: legit\nStatus:       VALID\nWorkflow: ...` on one
  line — visibly a single field's value, never additional structured
  lines.
- **Operational/security impact:** A workflow TOML file is exactly the
  kind of artifact this project's own threat model already treats as
  untrusted external input at this trust boundary (shared/downloaded
  workflow templates, a file from a PR under review, a file received
  from another team) — `docs/workflow-security.md` opens by calling
  workflow files "the package's first feature that reads a user-authored
  file." `workflow validate` is also the specific subcommand whose
  entire purpose is to be run against such a file *before* trusting it
  for anything else, and `--format text` is the CLI's default output
  format. The practical impact is display/parsing integrity, not code
  execution or privilege escalation: exit codes are unaffected (still
  correctly `0`/`2` from `report.status`, computed before rendering),
  and JSON consumers are unaffected. But a human operator skimming
  terminal output, or a naive script doing line-oriented text scraping
  of `workflow validate`'s default-format stdout (a first-glance-natural
  thing to do with a small CLI tool's default output), can be shown
  forged status/field lines that did not come from the tool itself. This
  is precisely the failure class `_sanitize_for_text()` exists to
  prevent everywhere else in this codebase.
- **Recommended fix:** Wrap both interpolations in
  `render_workflow_validate_text()` with `_sanitize_for_text()`, matching
  `render_workflow_run_text()`'s existing pattern for the equivalent
  field:
  ```python
  f"Path:         {_sanitize_for_text(report.path)}",
  ...
  f"Workflow:     {_sanitize_for_text(report.workflow_name) if report.workflow_name else '(none)'}",
  ```
  Add a `workflow validate --format text` regression test mirroring
  `test_run_text_output_sanitizes_control_characters`, so this renderer
  carries the same pinned coverage its sibling already has.

**No other High finding.**

### Critical

**None.** No arbitrary-code-execution, authentication-bypass, privilege-
escalation, or remote-network-exposure finding survived hands-on testing.
Every shell-metacharacter, command-substitution, path-traversal, and
TOCTOU/symlink attack attempted against `report aggregate --output`,
`workflow validate`, and `workflow run` (see the adversarial checklist
above) was independently reproduced to fail safely — either rejected as
a controlled validation error, or executed as inert literal data with no
observable side effect (the canary-file creation attempt via a crafted
`logs_analyze` `path` never fired).

### Medium

**None.** No finding met the bar of "operationally significant but not
severe" after verification — see "What holds up well" below for several
candidate concerns that were investigated and ruled out.

### Low

**None.** The minor uncovered lines noted in the coverage table above
were individually exercised by hand during this review (oversized-file
rejection, malformed-JSON rejection, non-dict `checks` entries, unknown
step kinds, wrong-typed fields, `nan`/`inf` rejection, etc.) and in every
case matched their documented/expected behavior; none produced an
observable defect, so none is reported here as a manufactured Low
finding merely to populate the category.

---

## What holds up well

- **Report-kind detection is genuinely structural, not heuristic.**
  `core/report_aggregate.py:_detect_kind()` requires a fixed, per-kind
  key combination (e.g. `protocol`+`results`+`options` for health
  reports, further split on `protocol == "http"`/`"tcp"`) and returns
  `None` — a controlled `unsupported or unrecognized MAOps report type`
  exit-`2` failure — for anything else. Hand-tested: a bare
  `{"overall": "pass", "version": "9.9.9", "fake": true}` document (an
  attempt to impersonate a trusted report by borrowing its two most
  "official-looking" fields) is correctly rejected, as is a
  `{"protocol": "ftp", ...}` document that partially matches the
  health-report shape but not its closed `http`/`tcp` value set.
- **Normalization never blindly embeds a source report.** Every one of
  the eight `_normalize_*` functions in `report_aggregate.py` extracts a
  small, fixed set of typed fields into `ReportMetric`/`NormalizedReport`
  — verified by reading all eight and confirming none does a
  `**raw`-style spread or a full-document copy anywhere.
- **The fd-safety pattern in `report_reader.py` is sound and exercised.**
  `os.lstat()` pre-check → `O_NOFOLLOW`/`O_CLOEXEC` open →
  `os.fstat()`-vs-pre-`lstat()` `(st_dev, st_ino)` comparison → bounded
  `max_bytes + 1` read correctly rejects symlinks (even without root, by
  creating a real symlink and observing `IS_SYMLINK`), FIFOs (via
  `mkfifo`), directories, and a hand-crafted 6 MiB file, all before any
  unbounded read is attempted.
- **`--output`'s atomic-write design defeats the TOCTOU/symlink-race
  scenario the review brief specifically asked about, by construction.**
  `write_report_output()` (`commands/report.py:25-72`) writes to a
  sibling `tempfile.mkstemp()` file and finishes with `os.replace(tmp,
  path)`. POSIX `rename(2)` — which `os.replace()` wraps — never
  dereferences its destination path's final component even if that
  component is a symlink; it atomically replaces the directory entry
  itself. This means the classic "attacker races a symlink into the
  destination path between an existence check and the write" attack is
  structurally inert here regardless of timing, not merely
  discouraged by the initial `os.lstat()` check (which independently
  also refuses an *already-existing* symlink target outright, even with
  `--force`). Confirmed no `.maops-py-report.*.tmp` file survives a
  refused (symlink-target or permission-denied) write.
- **Workflow files are proven data, not code, by direct instrumentation,
  not just by docstring claim.** A monkeypatch script (independent of
  the existing test suite) that makes `socket.socket`,
  `socket.create_connection`, `subprocess.Popen`, `subprocess.run`,
  `subprocess.call`, `os.system`, `shutil.which`, and `os.chdir` all
  raise `AssertionError` if called, then runs
  `build_workflow_validation_report()` against a workflow file declaring
  every one of the seven step kinds (including `health_http`/
  `health_tcp` targets and a `tools_inspect` step), returns a valid
  report with zero forbidden calls and zero cwd mutation. Separately, a
  real-subprocess run of `workflow run` against shell-metacharacter-laden
  `path`/`id` fields (`` $(whoami) ``, `` `id` ``, a literal
  `` app.log`touch /tmp/PWNED_$$` `` canary payload) produced only
  "path not found" `FAIL` results with the metacharacters preserved
  verbatim in the error string — the canary file was never created.
- **Sequential ordering and the "a FAIL step never discards later
  results" contract both hold under a real, live-network reproduction.**
  A four-step workflow (`doctor` → `health_http` against a real loopback
  `ThreadingHTTPServer` → `health_tcp` against a closed loopback port
  (forced `FAIL`) → `inventory_system`) run as a real subprocess
  preserved declared step order in the output and returned a `PASS`
  result for the fourth step despite the third step's `FAIL` — with
  overall correctly `FAIL` and exit code `1`.
- **Relative-path resolution against the workflow file's own directory,
  not the process cwd, is real and correctly scoped even under a
  symlinked workflow path.** Running `workflow run` from an unrelated
  directory correctly resolved a relative `logs_analyze`/
  `inventory_filesystem` path against the *workflow file's* directory
  (confirmed via the resulting report's absolute-path headline), and the
  process's cwd was unchanged after the run. A workflow file reached via
  a symlink resolves relative paths against the lexical parent of the
  CLI-supplied (symlink) path, not the symlink target's real directory —
  exactly the documented "never `Path.resolve()`" behavior — and fails
  safely (`path not found`) rather than silently reading from an
  unexpected location.
- **Network access stays scoped to `health_http`/`health_tcp` exactly as
  documented.** A repository-wide grep confirms zero `subprocess`/
  `socket`/`ssl`/`shell=True`/`eval`/`exec`/`os.chdir` references
  anywhere in the Day 6 module set outside docstring prose describing
  their absence.
- **Bounds are enforced consistently and match documentation exactly**:
  report count `1`-`50` (0 and 51 both correctly rejected, argparse's own
  `nargs="+"` independently enforces the `≥1` floor), workflow steps
  `1`-`32` (0, 32, and 33 all independently confirmed at the exact
  boundary), `health_http`/`health_tcp` targets `1`-`100`, and every
  per-field numeric bound in `workflow_parser.py` (including `nan`/
  `inf`/`-inf` rejection, which falls out correctly from the existing
  `numeric > minimum`/`numeric >= minimum` comparisons since any
  comparison against `NaN` is `False` in Python).
- **Multi-report aggregation is order-preserving and short-circuits
  correctly.** `report aggregate pass.json bad.json warn.json` fails on
  `bad.json` specifically, without ever reaching or mentioning
  `warn.json` — confirmed by direct reproduction, matching the
  documented "checked, and short-circuiting, file by file in the exact
  order given" contract.
- **`ruff`, `ruff format`, and `mypy --strict` are all clean**, and
  `make smoke-install` — a full wheel build, isolated-venv install, and
  CLI smoke pass including the new `report aggregate`/`workflow
  validate`/`workflow run` steps and a real loopback HTTP server + raw
  TCP listener via `workflow_smoke_check.py` — passed end to end on this
  branch as it stands.

---

## Totals and verdict

- **Total tests observed:** 1245 passed, 0 failed, 0 skipped
  (`tests/unit` + `tests/integration`).
- **Coverage observed:** 98.49% overall (project floor: 90%). Every
  Day 6 module individually exceeds the floor by a wide margin
  (93%-100%; see the module table above).
- **Static analysis:** `mypy --strict` clean across 38 source files;
  `ruff check` clean; `ruff format --check` clean (175 files already
  formatted).
- **Architecture/security verdict:** The Day 6 delta is well-architected
  and matches its own documentation closely — report-kind detection is
  structural rather than heuristic, normalization never leaks a raw
  source document, the `--output` atomic-write path structurally defeats
  the symlink-race class of attack rather than merely mitigating it, and
  the workflow engine's "declarative data, never executable code" claim
  held up under direct adversarial and instrumented testing (shell
  metacharacters, command substitution, path traversal, and a live
  canary-file-creation attempt all failed to escape the data boundary).
  One **High** finding (H-1) is a genuine, narrowly scoped regression
  from a security invariant this same codebase enforces everywhere else
  in the same file — it is real, reproducible, and easy to fix, but it
  is a display/text-integrity issue confined to one subcommand's default
  text renderer, not a code-execution, data-exposure, or exit-code-
  integrity issue.
- **Release-blocking findings:** One (**H-1**). This should be fixed —
  and, given how narrow and mechanical the fix is (two `_sanitize_for_text()`
  calls plus one regression test mirroring an existing pattern), fixing
  it before v0.6.0 ships is the recommended path rather than deferring
  it. No Critical finding exists that would independently block release.
- **Strongest three areas:**
  1. The `--output` atomic-write design (`commands/report.py:
     write_report_output()`), which defeats the destination-symlink
     TOCTOU race by construction (`os.replace()`'s POSIX `rename(2)`
     semantics never dereference the destination's final path
     component) rather than merely narrowing the race window.
  2. The workflow engine's genuine "data, not code" property, proven
     here by direct call-interception instrumentation and a live
     canary-payload test, not just asserted by docstring.
  3. Report-kind detection's structural (never heuristic) design, which
     concretely defeats arbitrary-JSON report impersonation attempts.
- **Highest-priority improvements:**
  1. Fix H-1: sanitize `render_workflow_validate_text()`'s
     `workflow_name`/`path` interpolations and add the missing
     regression test.
  2. Consider a small `tests/unit/test_cli_workflow.py` addition
     exercising `workflow validate --format text` end to end with a
     control-character-laden `name`, mirroring the existing `workflow
     run` coverage, so this exact class of gap is structurally harder to
     reintroduce in a future renderer.
  3. No other improvement is high-priority from this review; the
     remaining minor coverage gaps identified above are narrow
     defensive/race-window branches whose behavior was independently
     confirmed correct by hand and do not warrant dedicated new tests
     ahead of other release work.
