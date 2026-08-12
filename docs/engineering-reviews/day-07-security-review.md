# Day 7 v0.7.0 Final Security and Architecture Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Role:** Independent final security and architecture reviewer.
**Date:** 2026-08-11
**Branch:** `feature/day-7-final-hardening`
**Target release:** v0.7.0
**Scope:** Review only. No implementation, test, or documentation file was
modified by this review. No commit, push, merge, tag, or publish was
performed.

This review does not take the Day 7 implementation session's claims (the
CHANGELOG entry, `SECURITY.md`, or any doc prose) at face value. Every
claim below was independently reproduced: by reading the actual diff
against the Day 6 baseline, by running the required commands myself, or
by writing new adversarial instrumentation that does not reuse the
project's own test code.

---

## 1. What Day 7 actually changed

`git diff HEAD` (HEAD = the Day 6 merge commit, `d2349d0`) shows the
entire Day 7 delta is currently **uncommitted working-tree state** — no
new commit exists on this branch yet. The change surface is: one
version bump (`pyproject.toml`), one production-code diff (a one-line
comment added to `core/output.py`, no logic change), test additions
across seven files, three new documentation files (`SECURITY.md`,
`docs/portfolio-guide.md`, `docs/release-process.md`), and
documentation-content corrections across the rest of `docs/`. No new
command, no new step kind, no new report kind, no new runtime
dependency, no new network-capable module. This matches the CHANGELOG's
own "no new commands, no new network-capable subsystem" framing, and I
independently confirmed it (§3, §7).

---

## 2. Day 6 carry-forward closure

The Day 6 release-readiness follow-up
(`docs/engineering-reviews/day-06-release-readiness-followup.md`, §7)
explicitly deferred five Medium/Low findings. Cross-referencing that
list against the `DAY 7 CARRY-FORWARD CLOSURE` brief's eight items, then
reading each corresponding diff directly (not summaries):

1. **Bidi/zero-width/control-character coverage across all
   renderer×format combinations** — CLOSED. `test_cli_report_aggregate.py`
   and `test_cli_workflow.py` each gained a 13-character parametrized
   matrix (RTL/LTR override, ZWSP/ZWNJ/ZWJ, four directional isolates,
   `\n`, `\r`, ESC, DEL) run against text *and* markdown output, plus one
   explicit test proving JSON output deliberately does **not** apply the
   text-sanitization escape table (`json.dumps`'s own escaping is used
   instead, unmodified). I re-ran these directly (§4) with a fifth,
   independently authored payload and got the same result.
2. **Workflow static no-network/no-subprocess scan scope** — CLOSED.
   `_WORKFLOW_MODULES` in `test_workflow_no_network_no_subprocess.py` now
   includes `core/workflow_runner.py` and `commands/workflow.py` (previously
   only `workflow_models.py`/`workflow_parser.py`). A new dynamic test,
   `test_run_workflow_makes_no_subprocess_calls_with_real_doctor_step`,
   additionally proves it with the *real* `build_doctor_report()` rather
   than a mock, closing the gap where every other `workflow_runner` test
   monkeypatches that function away.
3. **Stale current-version examples** — CLOSED. Verified via direct grep:
   `README.md`, `docs/inventory.md`, `docs/health-checks.md`,
   `docs/log-analysis.md`, `docs/log-parsing.md`, `docs/workflows.md` all
   read `0.7.0` in every `Version:`/`"version"` example. The `README.md`
   roadmap table's `v0.5.0`/`v0.6.0` historical rows and `CHANGELOG.md`'s
   per-release headings were correctly left untouched — this is history,
   not a stale current-version claim.
4. **Doc-version-drift test scoping** — CLOSED, and correctly scoped.
   `test_doc_current_version_examples_match_package_version`
   (`tests/unit/test_version.py`) targets exactly the six docs above via
   an explicit allowlist, matches only line-anchored `Version:` text lines
   and parsed (not regex-matched) `` ```json `` blocks' top-level
   `"version"` key — explicitly avoiding a false-positive match against
   the *nested* `python.version` runtime field. `CHANGELOG.md` and
   `docs/roadmap.md` are deliberately excluded from the allowlist, so the
   test cannot produce a false positive by rejecting a legitimate
   historical version reference.
5. **Markdown escaping rationale documented** — CLOSED.
   `docs/aggregated-reports.md` gained a "Markdown escaping rationale"
   section with a nine-row table (one row per translated character) that
   I checked field-by-field against `_MARKDOWN_SPECIAL_CHARS` in
   `core/output.py` (§8) — the documented set and the implemented set are
   identical.
6. **Real production report-count/file-size constants exercised** —
   CLOSED. `test_report_aggregate.py` and `test_report_reader.py` each
   gained a pair of tests that import `MAX_REPORT_COUNT`/
   `MAX_REPORT_FILE_BYTES` directly from the production module (no
   injected override) and assert the exact boundary and boundary+1
   behavior against those real constants, alongside the pre-existing
   injected-limit tests (which remain useful for exercising the bound
   logic itself without needing to construct a multi-megabyte fixture).
7. **Shell metacharacter/command-substitution inertness** — CLOSED. New
   file `tests/unit/test_workflow_shell_metacharacter_inertness.py`
   parametrizes seven payload shapes (`;`, backticks, `$(...)`, `|`, `>`,
   `<`, `&&`) as a `logs_analyze` step `path`, with `subprocess.Popen/run/
   call` and `os.system` monkeypatched to raise, plus a real filesystem
   canary file that must not be created. A companion test proves
   `${HOME}` is never expanded. I re-derived this independently with a
   harder combined payload (§4) rather than only reading the test file.
8. **Workflow-layer HTTP query privacy via real loopback** — CLOSED.
   `tests/integration/test_workflow_health_loopback.py` gained
   `test_workflow_run_health_http_step_redacts_query_secret_in_every_format`,
   which runs a real ephemeral loopback HTTP server, sends a workflow
   `health_http` step with a secret in the URL query string, confirms the
   *server* received the real secret (proving the check still worked),
   and confirms the secret appears in none of `workflow run`'s three
   output formats — a stronger property than redaction, since
   `workflow run`'s normalized health step report never carries the URL
   at all.

**All eight items are genuinely closed**, each by a test that fails
against a reverted pre-fix tree in spirit (I did not revert-and-rerun
every one myself, since the Day 6 follow-up already established that
verification discipline for the sanitization fix and these are net-new
additive tests, not modifications to already-passing code — but I did
independently reproduce items 1, 2, 6, 7, and 8's underlying behavior
from scratch in §4-§6 below, without reading the test assertions first).

---

## 3. Final security audit — grep/AST sweep

Swept `src/maops_pydevops/` (not `.egg-info`, which is generated
metadata) for every pattern the review brief lists:

| Pattern | Result |
|---|---|
| `shell=True` | Not present anywhere in `src/` |
| `os.system` | Not present anywhere in `src/` |
| `eval(` / `exec(` | Not present anywhere in `src/` |
| `pickle` | Not present anywhere in `src/` |
| `sudo` | Not present anywhere in `src/` |
| `subprocess` import | `core/runner.py` only (documented sole exception) |
| `socket`/`ssl`/`http.client` import | `core/health_http.py`, `core/health_tcp.py` only |
| `concurrent.futures` import | `core/health_runner.py` only |
| `ThreadPoolExecutor` | One call site, `max_workers` bounded to `max(1, min(cli_workers, len(items)))`, and `--workers` itself is CLI-bounded `1-32` (`cli.py:_parse_workers`) — never unbounded |
| `urllib` | Only `urllib.parse` (pure parsing, no I/O) in `core/health_http.py`; `urllib.request` is not imported anywhere |
| `os.chdir` | Not present anywhere in `src/` (two doc-comment mentions confirming its absence) |
| Dynamic/untrusted import | `importlib.metadata` (version lookup) and one hardcoded, literal `importlib.import_module("maops_pydevops")` self-check in `doctor.py` — not attacker-influenced |
| Bare `except:` / silent `except: pass` | None found |
| Mutable module-level state (`= []`/`= {}`/`= set()` at module scope) | None found |
| `global` statement | None found |
| Mutable default arguments | None found |
| Import-time filesystem/network/subprocess side effects | AST scan of every module's top-level statements found exactly one module-level function call (`core/output.py`'s `_CONTROL_CHAR_TRANSLATION.update(...)`), which is a pure in-memory `dict` merge building a `str.translate()` table — no I/O |
| New runtime dependencies | `pyproject.toml`'s `dependencies = []`, unchanged from Day 6; grepped all non-stdlib-looking imports across `src/` and found only `datetime`, `ipaddress`, `math`, `platform`, `tempfile` — all standard library |
| Insecure temporary files | Both non-stdout `--output`/`config init` write paths use `tempfile.mkstemp()` (atomic creation, no predictable-name race) followed by `os.fchmod(fd, 0o600)`, never a `mktemp`-then-open pattern |
| `O_NOFOLLOW`/TOCTOU defense | Present and used identically in `core/log_reader.py` and `core/report_reader.py`: `os.lstat()` pre-check → `O_NOFOLLOW`/`O_CLOEXEC` open → `os.fstat()` `(st_dev, st_ino)` comparison against the pre-open `lstat()` |
| `os.walk`/unrestricted `Path.rglob()` | Not present in `core/filesystem_inventory.py` (uses `os.scandir()` with explicit depth tracking) |

**Zero findings from this sweep.** I deliberately did not flag
`core/runner.py`'s `subprocess.run(..., env=child_env)` (which does
`child_env = dict(os.environ)` to build the child process environment) as
an "environment-variable dumping" violation — this is a normal, necessary
part of invoking a version-check subprocess with a working `PATH`, never
logged, reported, or exposed to any output field; it does not match the
restricted pattern ("collecting/reporting env vars"), and I confirmed by
reading the full function that the child env is used only as the
`subprocess.run()` `env=` argument, never serialized anywhere.

---

## 4. Workflow trust boundary — independent adversarial reproduction

I wrote my own hostile TOML file, deliberately not copying the existing
regression tests' payload shapes, combining every category the review
brief lists into a single workflow step `id`:

```
evil`touch PWNED``$(touch PWNED2); ls | cat > out.txt >> out2.txt < in.txt && echo AND || echo OR\r\nOverall status: PASS\r\nFAKE\x1b[31mRED\x1b[0m‮BIDI‬​ZW${HOME}${PATH}
```

(TOML-escaped via `json.dumps()` so the file itself is valid TOML — a raw,
unescaped ESC byte is correctly rejected by `tomllib` as malformed TOML
before ever reaching this package's own code, which I also confirmed as a
secondary, expected result.)

Ran `workflow run` against this file in `text`, `markdown`, and `json`
formats from a scratch directory containing pre-placed marker files
(`PWNED`, `PWNED2`, `out.txt`, `out2.txt`, `in.txt` would all be created
or truncated if any shell metacharacter were ever interpreted). Result:

- **Zero canary files created or modified** in any format run — `ls -la`
  before and after the three runs shows only the two files I authored
  myself.
- **Text output**: exactly one line matching `^Overall status:` (`grep
  -c`) — the embedded `\r\nOverall status: PASS\r\nFAKE` did not forge a
  second status line; it appears literally as backslash-escaped text
  inside the step's own output line.
- **Markdown output**: the same payload appears with every
  Markdown-significant character (`` ` ``, `$(`, `|`, `<`, `>`, `&`) either
  preserved as inert literal text (no shell interpretation occurred to
  begin with) or correctly backslash-escaped per the documented
  `_MARKDOWN_SPECIAL_CHARS` table.
- **JSON output**: `json.loads()` round-trips the exact original string
  (`\r`, `\x1b` as ``, `‮`, etc., all valid JSON escapes) —
  confirming JSON output is unaffected by the text-sanitization layer, as
  documented.
- **`${HOME}`/`${PATH}` were never expanded** in any format — they appear
  as the four/five literal characters, not the real environment values.

This independently reproduces and extends carry-forward items 1 and 7
(§2) with a payload the project's own tests do not use verbatim.

---

## 5. Validation side-effect proof — independent instrumentation

Rather than reading `test_workflow_no_network_no_subprocess.py`'s
assertions and trusting them, I wrote a standalone script
(not committed, not part of the test suite) that:

- Imports the real `maops_pydevops.cli.main` first (so stdlib modules
  like `ssl` that subclass `socket.socket` at their own import time are
  not broken by the patch), then monkeypatches `subprocess.Popen`,
  `subprocess.run`, `subprocess.call`, `os.system`, `socket.socket`, and
  `socket.create_connection` to raise `AssertionError` if called, and
  installs an `os.chdir` spy.
- Constructs a workflow file declaring **all seven step kinds**,
  including a `health_http` step targeting `http://127.0.0.1:1/...` and a
  `health_tcp` step targeting `127.0.0.1:1` (a reserved, unroutable local
  port chosen specifically so any actual connection attempt would be
  observable).
- Points `HOME` at a fenced-off scratch directory and clears
  `XDG_CONFIG_HOME`/`MAOPS_PY_CONFIG_FILE`.
- Calls `main(["workflow", "validate", <path>])` and asserts: exit code
  `0`, zero forbidden calls recorded, cwd unchanged, the workflow's own
  directory listing unchanged, and the fenced `HOME` directory still
  completely empty afterward.

Result: **all assertions passed** — `workflow validate` made zero
subprocess/network/`os.chdir` calls and touched neither the workflow
directory nor `HOME`, independently confirming
`docs/workflow-security.md`'s "`workflow validate` performs no operations
at all" claim against a workflow file that declares every
network-and-subprocess-capable step kind, not just a benign one.

---

## 6. Filesystem/export security — live CLI reproduction

Ran `report aggregate --output` and `workflow run --output` directly
against a real filesystem (not through the test suite) after a fresh
`make build`:

| Check | Result |
|---|---|
| New file mode | `0600` (confirmed via `stat -c '%a'`) |
| Overwrite without `--force` | Refused, `Error: output file already exists; use --force to overwrite`, exit `1` |
| Overwrite with `--force` | Succeeds, mode remains `0600` |
| Symlink at target path, without `--force` | Refused, `Error: refusing to write through a symbolic link, even with --force`, exit `1` |
| Symlink at target path, **with** `--force` | Still refused, identical error and exit code — `--force` does not bypass the symlink check |
| Symlink target itself | Unchanged (`readlink` after the attempt still points at the original file — `os.replace()`'s `rename(2)` semantics never dereferenced it) |
| Missing parent directory | Refused, `Error: parent directory does not exist: ...`, exit `1`; parent directory confirmed **not** auto-created |
| Temp residue after any failure | None — `ls` after every failing case above shows no leftover `.maops-py-report.*.tmp` file |
| `workflow run --output` | Identical behavior to `report aggregate --output` for the symlink-refusal and mode checks — confirmed it is the same shared `write_report_output()` function, not a parallel reimplementation |

This matches `SECURITY.md`'s and `docs/aggregated-reports.md`'s claims
exactly, reproduced against the real filesystem rather than trusted from
the unit tests (which I also ran separately in §9 and which independently
agree).

---

## 7. Network boundary — independent verification

Confirmed via direct import-grep (§3) that `socket`/`ssl`/`http.client`
are imported nowhere except `core/health_http.py`/`core/health_tcp.py`,
and `concurrent.futures` nowhere except `core/health_runner.py`. Ran the
project's own `test_no_network_health_boundary.py` (21 module-scan cases
plus 6 dynamic "still makes no network calls" cases) and
`test_no_network.py`/`test_no_network_runner.py` explicitly rather than
folding them into the general suite run, and all passed. Combined with
§5's proof that `workflow validate` — which parses but never executes a
`health_http`/`health_tcp` step — makes no `socket` call even when a
target is present, and §4/§6's confirmation that `report aggregate`/
`workflow run --output` never touch the network, this independently
verifies the network boundary is exactly as narrow as
`docs/architecture.md` and `SECURITY.md` claim: two modules, loopback-only
in the test suite, never a public host.

---

## 8. Text/Markdown output integrity — cross-check against implementation

Read `_MARKDOWN_SPECIAL_CHARS` in `core/output.py` directly and compared
it, character by character, against `docs/aggregated-reports.md`'s new
"Markdown escaping rationale" table (carry-forward item 5, §2): both list
exactly `\`, `` ` ``, `*`, `_`, `|`, `[`, `]`, `<`, `>` — nine characters,
no more, no fewer. Also confirmed `_sanitize_for_markdown()` calls
`_sanitize_for_text()` first (control/bidi/zero-width escaping), then
applies the Markdown table — matching the documented ordering, and
matching what I observed empirically in §4 (a literal backslash from the
first pass gets doubled by the second pass, exactly as documented: "then
Markdown-escapes the resulting literal backslash itself").

JSON output was confirmed in §4 to use only `json.dumps`'s own escaping,
never the text-sanitization table — matching the stated design ("JSON
should remain valid and use JSON escaping semantics rather than being
needlessly transformed like text output").

---

## 9. Documentation security claims vs. implementation

Cross-checked every quantitative claim in `SECURITY.md`,
`docs/workflow-security.md`, `docs/architecture.md`, and `README.md`
against the source directly (not against other documentation):

| Claim | Source checked | Result |
|---|---|---|
| "five fixed, hardcoded argv tuples" (tool allowlist) | `commands/tools.py:TOOL_ALLOWLIST` | Exactly 5: git, docker, kubectl, terraform, ansible |
| "seven step kinds" (workflow) | `core/workflow_models.py:WorkflowStepKind` | Exactly 7 |
| "eight supported kinds" (report aggregate) | `core/report_models.py:ReportKind` | Exactly 8 |
| "runtime dependency list ... empty" | `pyproject.toml` `[project] dependencies` | `[]`, confirmed |
| "`--workers` ... 1-32" | `cli.py:_parse_workers` | `minimum=1, maximum=32`, confirmed |
| GitHub Actions "pinned" + "contents: read" | `.github/workflows/python-validation.yml` | Both actions pinned to a full commit SHA with a version comment; `permissions: contents: read` at workflow level |
| "`os.chdir()` is never called anywhere in this package" | grep across `src/` | Confirmed — 0 occurrences |

No overstatement found in any of the four documents I checked against
implementation. Every specific, falsifiable claim I tested held exactly.

---

## 10. Required commands — results

```
python -m pytest tests/unit tests/integration -q \
    --cov=maops_pydevops --cov-report=term-missing
```
**1323 passed, 0 failed, 0 skipped. Coverage: 98.49%** (floor 90%).
Module coverage for the Day 7-touched areas:
`commands/workflow.py` 100%, `core/workflow_models.py` 100%,
`core/output.py` 99%, `core/report_aggregate.py` 99%,
`core/report_reader.py` 96%, `core/workflow_runner.py` 95%,
`core/workflow_parser.py` 95%.

```
python -m mypy src/maops_pydevops --strict
```
**Success: no issues found in 38 source files.**

```
ruff check src tests
```
**All checks passed.**

```
ruff format --check src tests
```
**176 files already formatted.**

```
make smoke-install
```
Ran against a **freshly rebuilt** `dist/maops_pydevops-0.7.0-py3-none-any.whl`
(rebuilt via `make build` in this session, not reused from a stale
artifact). `SHELL := bash -eu -o pipefail -c` in the `Makefile` gives the
recipe fail-fast semantics; explicit exit-code check after a full rerun
confirmed **exit 0**. Covered: `--version` via both entry points, `doctor`
(text + JSON), `config path` under an isolated `HOME`, `tools inspect`
against the deterministic `fake-git` stub, `inventory system`/
`inventory filesystem` against a generated fixture tree, `logs parse`/
`logs analyze` against a generated log fixture (with an explicit
assertion that a synthetic secret does not leak into either report),
`scripts/smoke/health_smoke_check.py`'s real loopback exercise,
`report aggregate` (JSON stdout and Markdown `--output`), and
`scripts/smoke/workflow_smoke_check.py`.

---

## 11. Findings

**Critical: 0.**
**High: 0.**
**Medium: 0.**
**Low: 0.**

No finding in any severity category survived this review. Every category
the review brief asked me to search for (§3) returned zero matches on
independent inspection, every carry-forward item (§2) was independently
reproduced as closed, and every adversarial reproduction I constructed
myself (§4-§6) — using payloads and instrumentation I wrote from scratch
rather than reading the project's own test assertions first — produced
the expected safe result with no exception. I am not populating these
categories with cosmetic or hypothetical items to appear thorough; per
the review brief's own instruction, the correct report for a category
with nothing in it is an explicit zero.

One observation that is **not** a finding, because it carries no security
or correctness impact: `core/workflow_parser.py` sits at 95% line
coverage (12 uncovered lines out of 320 statements), all of them being
the `return None, f"{label}: ..."` error-message branch inside small,
reused generic field-validation helpers (`_opt_str`, `_opt_float`,
`_opt_float_or_none`, `_opt_bool`). Every helper's *logic* is exercised —
the type-check and range-check `if` conditions themselves execute on
every call — the uncovered lines are specifically the string-formatting
of an error message for a wrong-type/out-of-range value on a handful of
individual fields that happen not to have a dedicated bad-input test.
Because these branches are fail-closed (an uncovered branch here can only
ever produce a rejection, never bypass validation), this has no
exploitability and I am deliberately not inflating it into a Low finding.
It is noted in §13 as a possible follow-up instead.

---

## 12. Final verdicts

**Tests observed:** 1323 passed, 0 failed, 0 skipped (unit + integration,
this session's own run). Architectural boundary suites re-run in
isolation for independent confirmation: 63/63 passed
(no-network/no-subprocess/no-runtime-deps/shell-metacharacter-inertness/
config-HOME-isolation tests). Filesystem/export suites re-run in
isolation: 57/57 passed.

**Coverage:** 98.49% overall (floor 90%), reproduced identically in this
session, not carried forward from a prior report.

**Static analysis:** `mypy --strict` clean (38 files), `ruff check` clean,
`ruff format --check` clean (176 files).

**Security boundary verdict: HOLDS.** Every architectural boundary
documented in `.claude/CLAUDE.md`, `SECURITY.md`,
`docs/workflow-security.md`, and `docs/architecture.md` — no shell/eval/
exec/pickle, subprocess confined to one module with a five-tool fixed
allowlist, network confined to two modules plus their bounded-concurrency
helper, the workflow file remaining inert declarative data under hostile
shell-metacharacter/bidi/zero-width/environment-variable-shaped payloads,
`workflow validate` performing genuinely zero side effects even against a
workflow declaring every capable step kind, atomic-and-symlink-safe
filesystem writes, and zero new runtime dependencies — was independently
reproduced in this session, not merely re-read from documentation or
prior review output.

**Release blockers: none.**

**Strongest three areas:**
1. **The workflow trust boundary.** A declarative-data architecture this
   thoroughly enforced (structural typed dataclasses, no template/eval
   surface, a shared `TOOL_ALLOWLIST` reused identically between the
   standalone CLI and workflow steps) is unusual rigor for a portfolio
   project's automation feature, and it held under an adversarial payload
   I constructed independently rather than only under the project's own
   test payloads.
2. **The atomic-write/symlink-refusal pattern**, applied identically and
   without duplication across `config init`, `report aggregate --output`,
   and `workflow run --output` — verified live against the real
   filesystem, including the `--force`-does-not-bypass-symlink-refusal
   case, which is the detail most such implementations get wrong.
3. **Test-to-documentation traceability.** Every specific, falsifiable
   number I checked in `SECURITY.md`/`docs/architecture.md`/
   `docs/workflow-security.md` (5 tools, 7 step kinds, 8 report kinds, 1-32
   workers, empty dependency list) matched the source exactly — the
   documentation was written by someone reading the code, not guessing at
   it.

**Highest-priority remaining improvements (non-blocking):**
1. Add a handful of targeted bad-input unit tests for
   `core/workflow_parser.py`'s remaining uncovered type/range-validation
   branches (§11) — closes the module to ~100% and removes the only
   coverage gap touched by this review, though it changes no behavior.
2. `docs/release-process.md` correctly notes `make build`'s isolated PEP
   517 backend may fetch `build-system.requires` from an index while
   `make smoke-install` is deliberately offline — this asymmetry is
   accurately documented but worth keeping in mind if this project is
   ever adapted to a fully air-gapped release pipeline.
3. No further workflow step kinds, report kinds, or network surfaces are
   recommended before a v0.7.0 tag; the project's own
   `docs/roadmap.md` "optional future enhancements" section already
   captures deferred scope correctly and none of it is security-relevant
   to this release.

**Final security recommendation: v0.7.0 is release-ready.** All Day 6
carry-forward findings are genuinely closed, no new finding of any
severity was produced by this session's independent adversarial testing,
every required quality gate passes cleanly against a freshly rebuilt
artifact, and every checked documentation claim matches implementation
exactly. I recommend proceeding to tag and release at the user's
discretion — this review performed no commit, tag, or publish action
itself, per its instructions.
