# Day 7 v0.7.0 Final Test Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Role:** Independent final test engineer. Test-quality audit only — no
source, test, or documentation file was modified during this review, and
no commit/push/merge/tag/publish was performed.
**Date:** 2026-08-11
**Branch:** `feature/day-7-final-hardening`
**Target release:** v0.7.0

This review does not take `docs/engineering-reviews/day-07-security-review.md`
(also on this branch, dated the same day) at face value. That review reached
a "zero findings" verdict; this review reads the same diff independently, at
the level of individual assertions rather than pattern sweeps, and reaches a
materially different (though still release-viable) conclusion: the test
suite is well-engineered and the security boundaries genuinely hold, but
several of the specific "CLOSED" claims about *test completeness* are
narrower than advertised. Every finding below was reproduced with evidence
— either by tracing exact test/implementation line numbers, or by running
adversarial instrumentation written from scratch in `/tmp` outside the repo.

---

## 1. What was reviewed

Line-by-line read of every Day 7 test diff, against the actual
implementation each test exercises:

- `tests/unit/test_cli_report_aggregate.py` (bidi/control sanitization matrix)
- `tests/unit/test_cli_workflow.py` (bidi/control sanitization matrix, step id)
- `tests/unit/test_report_aggregate.py` (real `MAX_REPORT_COUNT` boundary)
- `tests/unit/test_report_reader.py` (real `MAX_REPORT_FILE_BYTES` boundary)
- `tests/unit/test_version.py` (doc-version-drift allowlist)
- `tests/unit/test_workflow_no_network_no_subprocess.py` (dynamic real-step
  no-subprocess proof, scan-scope expansion)
- `tests/unit/test_workflow_shell_metacharacter_inertness.py` (new file)
- `tests/integration/test_workflow_health_loopback.py` (workflow-layer
  query-privacy loopback test)
- `src/maops_pydevops/core/output.py` (the only production-code diff — a
  4-line comment, confirmed no logic change)

Plus the modules these tests exercise (`core/output.py`, `core/report_reader.py`,
`core/report_aggregate.py`, `core/workflow_runner.py`, `core/workflow_parser.py`)
and the adjacent Day 1–6 regression suites that establish the patterns Day 7
either follows or (in two cases below) departs from.

---

## 2. Required commands — independently reproduced

```
python -m pytest tests/unit tests/integration -q \
    --cov=maops_pydevops --cov-report=term-missing
```
**1323 passed, 0 failed, 0 skipped. Total coverage: 98.49%.** Matches the
prior review's claim exactly, re-run fresh in this session (280s wall time).

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

No discrepancy with the security review's numbers on any of these four
commands.

---

## 3. Findings

### Medium — Bidi/zero-width parametrized matrix omits 6 of the 15 codepoints the implementation actually escapes

**Evidence.** `core/output.py:62-80`'s `_FORMATTING_CHAR_TRANSLATION` table
lists 15 codepoints (ZWSP, ZWNJ, ZWJ, LRM, RLM, LRE, RLE, PDF, LRO, RLO, LRI,
RLI, FSI, PDI, BOM). The Day 7 `_SANITIZATION_CASES` matrices in
`tests/unit/test_cli_report_aggregate.py:227-239` and
`tests/unit/test_cli_workflow.py:306-318` — each 13 entries, run against text
*and* markdown, plus a JSON-untouched test — cover only 9 of those 15:
RLO (`u202e`), LRO (`u202d`), ZWSP, ZWNJ, ZWJ, and the four isolates
(LRI/RLI/FSI/PDI). **LRM (`U+200E`), RLM (`U+200F`), LRE (`U+202A`),
RLE (`U+202B`), PDF (`U+202C`), and BOM (`U+FEFF`) appear in zero test file
in the repository** — confirmed by grepping the full test tree for
`200e|200f|202a|202b|202c|feff` (case-insensitive), which returns no matches.

The carry-forward closure brief this session's implementation was checked
against (`day-07-security-review.md` §2 item 1) describes this matrix as
covering "RTL/LTR override, ZWSP/ZWNJ/ZWJ, four directional isolates" — an
accurate description of what the matrix contains, but the security review
then characterizes the overall item as testing "all representative
bidi/zero-width/control characters," which overstates it: 6 of the 15
codepoints the implementation itself treats as security-relevant enough to
escape are absent from every parametrized case list in the suite.

**Reproduction (independent, outside the repo).** Verified the
implementation currently escapes all 6 untested codepoints correctly (this
is a *test* gap, not a live bug), then simulated the regression a
missing-codepoint bug would look like: removing `0x200E` (LRM) from
`_CONTROL_CHAR_TRANSLATION` and re-running `_sanitize_for_text()`.

```
Confirming the implementation DOES correctly escape these (i.e. this is a coverage gap, not a live bug):
  U+200E LEFT-TO-RIGHT MARK                  OK -> escaped correctly
  U+200F RIGHT-TO-LEFT MARK                  OK -> escaped correctly
  U+202A LEFT-TO-RIGHT EMBEDDING             OK -> escaped correctly
  U+202B RIGHT-TO-LEFT EMBEDDING             OK -> escaped correctly
  U+202C POP DIRECTIONAL FORMATTING          OK -> escaped correctly
  U+FEFF ZERO WIDTH NO-BREAK SPACE / BOM     OK -> escaped correctly

Simulating a regression: dropping 0x200E (LRM) from the translation table.
  With LRM dropped from the table, sanitize output = 'AAA‎ZZZ'
  Raw LRM character present in output: True
  -> This regression would NOT be caught by any test in test_cli_report_aggregate.py
     or test_cli_workflow.py's _SANITIZATION_CASES matrix, since U+200E is not
     one of the 13 tested codepoints.
```

**Why current tests failed to catch it.** The matrix was built by hand-listing
representative categories (RTL override, ZWSP, isolates) rather than by
iterating `_FORMATTING_CHAR_TRANSLATION`'s actual key set, so it drifted from
the implementation's real scope without either side noticing — the exact
"tests mirror an assumed spec, not the real implementation" failure mode.
A future one-line regression removing any of the 6 untested codepoints from
the translation table (e.g. during a refactor that "simplifies" the embedding
codepoints down to just the override/isolate ones) would pass the entire
suite, including every bidi-specific test that currently exists.

**Recommended regression test.** Replace the hand-authored `_SANITIZATION_CASES`
list's codepoint set with one derived from
`maops_pydevops.core.output._FORMATTING_CHAR_TRANSLATION.keys()` (plus the
fixed control-character set), so the matrix can never silently drift from the
implementation again — the same self-updating principle the Day 7 session
already applied correctly to `MAX_REPORT_COUNT`/`MAX_REPORT_FILE_BYTES`
(§4 below shows that pattern done right).

---

### Medium — `report_reader.py`'s final TOCTOU size recheck (lines 146-147) has zero test coverage, and the new "real boundary" tests don't reach it

**Evidence.** `core/report_reader.py:112-114` rejects a file whose *pre-open*
`lstat()` size exceeds `max_bytes`. `core/report_reader.py:132-134` rejects a
file whose *post-open* `fstat()` size exceeds `max_bytes`. `core/report_reader.py:139,145-147`
is a **third, independent** check: it reads `max_bytes + 1` bytes and, if
the actual read returned more than `max_bytes`, rejects it — explicitly
because (per the code's own comment) "a file that grew between the `fstat()`
above and this read is still caught as `TOO_LARGE` rather than silently
parsed from a truncated read."

`branch=True` coverage confirms lines 146-147 are never executed by the full
suite (`python -m pytest tests/unit -q --cov=maops_pydevops.core.report_reader
--cov-report=term-missing --cov-branch`, filtered to just this file, still
reports `146-147` as missing). The two new Day 7 "real constant" tests
(`test_real_default_file_size_boundary_one_byte_over_rejected`,
`test_report_reader.py:127-137`) write a file that is genuinely
`MAX_REPORT_FILE_BYTES + 1` bytes on disk — which is caught by the *first*,
cheapest check (line 112) before the file is ever opened, never reaching the
`fstat`-based or post-read checks at all. The existing Day 6
`test_report_reader_error_paths.py` does simulate the `fstat`-based race
(`test_fstat_detects_growth_past_max_bytes`, line 148), correctly
monkeypatching `os.fstat` — but nothing in the suite monkeypatches `os.read`
(or otherwise causes the actual bytes read to exceed what `fstat` reported),
so the third and final guard is exercised by nothing.

**Reproduction (independent, outside the repo).** Wrote a file that is
exactly `max_bytes` on disk (passes both the `lstat` and `fstat` checks),
then monkeypatched `os.read` to return `max_bytes + 1` bytes — simulating the
exact race the code comment names. Confirmed the guard fires as designed;
then mechanically removed the `if len(raw) > max_bytes:` block from a copy
of the function and re-ran the identical scenario:

```
On-disk size: 20 == max_bytes: 20
Unpatched module, simulated post-fstat growth race: too_large document accepted: False

Now removing lines 146-147 (the final `if len(raw) > max_bytes` recheck)
Patched module (guard removed), same race scenario -> reason: None document accepted: {'k': 'aaaaaaaaaaaa'}
PROVEN: without lines 146-147, a race-grown file silently bypasses the documented
5MB-class size bound and gets parsed as if it were within bound.
```

**Why current tests failed to catch it.** The Day 7 session's brief
specifically asked for "actual MAX_REPORT_FILE_BYTES boundary" / "actual +1
byte rejection" tests, and the two new tests satisfy that literally — but
they exercise only the cheapest of report_reader.py's three redundant size
guards. The other two guards exist precisely *because* the first one is
insufficient under a TOCTOU race, yet only one of the other two
(`fstat`-based) has any test, and it was written in Day 6, not Day 7. Day 7
added a "real constant, not injected" variant of the *first* check without
noticing the third check was already the only genuinely untested one.

**Why this is Medium, not High.** The failure direction is fail-open only
under a narrow, timing-dependent local-filesystem race (another process
appending to the report file in the exact window between this process's
`fstat()` and `read()` calls) — not attacker-reachable over any documented
network or CLI-argument surface, and `report aggregate` inputs are
local files the invoking user already controls. But it is a real,
demonstrated bypass of a documented, deliberately-designed defense-in-depth
control, with an explicit code comment describing the exact scenario nothing
in the suite tests.

**Recommended regression test.** Add
`test_read_report_file_rejects_growth_between_fstat_and_read` to
`tests/unit/test_report_reader_error_paths.py`, sibling to
`test_fstat_detects_growth_past_max_bytes`: monkeypatch `os.read` (not
`os.fstat`) to return more than `max_bytes` bytes while `os.lstat`/`os.fstat`
report a size within bound, and assert `ReportReadFailureReason.TOO_LARGE`.

---

### Low — `report_reader.py`'s open()-time `FileNotFoundError` TOCTOU branch is untested, unlike the identical race in `log_reader.py`

**Evidence.** `core/report_reader.py:61-67`'s `_open_regular_file()` catches
`FileNotFoundError` from `os.open()` itself (the file existed at `lstat()`
time but was deleted before the open — a real TOCTOU window) and maps it to
`ReportReadFailureReason.NOT_FOUND`. Coverage confirms lines 66-67 are never
executed by the suite. The *only* `NOT_FOUND` test in the project
(`test_report_reader.py:26`, `test_missing_file_is_not_found`) exercises the
earlier `os.lstat()`-raises-`FileNotFoundError` branch (line 94-96) — a file
that was never there — not the open()-time race.

`CLAUDE.md` explicitly states `report_reader.py`'s fd-safety pattern
"mirrors `core/log_reader.py`'s established fd-safety pattern," and
`log_reader.py`'s own test suite (`tests/unit/test_log_reader_error_paths.py:230`,
`test_open_not_found_via_toctou_race`) does test this exact race for the
sibling module. The pattern exists elsewhere in the codebase; it just wasn't
carried over here.

**Why lower severity than the previous finding.** If this branch were broken
or removed, the effect is a *loud* failure (an unhandled `FileNotFoundError`
propagating instead of a clean `ReportReadFailureReason.NOT_FOUND`), not a
silent bypass of a security boundary — closer to a UX/robustness gap than a
security one.

**Recommended regression test.** Port `log_reader.py`'s
`test_open_not_found_via_toctou_race` pattern: monkeypatch `os.open` to raise
`FileNotFoundError` after a real file passes the `lstat()` pre-check, assert
`ReportReadFailureReason.NOT_FOUND`.

---

### Low — misleading test documentation: `inventory_system` workflow step is not covered where the suite says it is

**Evidence.** `tests/unit/test_workflow_runner_step_kinds.py:1-4`'s module
docstring states: *"Every `_run_step` branch in `core/workflow_runner.py`:
one test per step kind (tools_inspect, logs_analyze, health_http,
health_tcp — doctor and inventory_system/inventory_filesystem are already
covered by `test_workflow_runner.py`)."*

Grepping `tests/unit/test_workflow_runner.py` for `inventory_system` or
`build_system_report` returns **zero matches**. That file thoroughly covers
`doctor` (`test_sequential_execution_order`, `test_pass_aggregate`, etc.) and
`inventory_filesystem` (`test_relative_path_resolved_against_workflow_dir_not_cwd`,
`test_inventory_filesystem_default_path_is_workflow_dir`), but never
constructs an `INVENTORY_SYSTEM`-kind `WorkflowStep` or monkeypatches
`build_system_report`. The `_run_step` branch at
`core/workflow_runner.py:101-103` (`raw = build_system_report().to_dict();
kind = ReportKind.INVENTORY_SYSTEM`) is exercised, with the real
(non-mocked) `build_system_report()`, by exactly one test in the entire
suite: `tests/integration/test_workflow_cli_integration.py:48`'s
`test_workflow_validate_and_run_end_to_end`, which runs the full CLI as a
subprocess.

This isn't just a documentation nit: subprocess-boundary integration tests
run outside the parent process's `--cov` measurement (no `COVERAGE_PROCESS_START`
is configured), and — more importantly — no test in the codebase verifies
`_run_step`'s `INVENTORY_SYSTEM` branch *in isolation*, the way every other
step kind gets a dedicated, monkeypatched unit test in
`test_workflow_runner_step_kinds.py`. A regression specific to that branch
(e.g. the wrong `ReportKind` assigned, or a `KeyError` in a dict-shape
mismatch) would only be caught by the one end-to-end integration test,
which is slower to run and harder to debug from a failure than a focused
unit test would be — and a contributor reading the docstring's "already
covered by `test_workflow_runner.py`" claim has no reason to add one.

**Recommended regression test.** Add an `inventory_system` case to
`test_workflow_runner_step_kinds.py` following the existing pattern (e.g.
`test_health_http_step_success`): monkeypatch
`workflow_runner.build_system_report`, assert the resulting step's `kind`,
`status`, and that the built report's fields flow into the step result. Also
correct the module docstring's false claim.

---

### Low — doc-version-drift test's current-version allowlist is a static, unenforced list

**Evidence.** `tests/unit/test_version.py:47-54`'s
`_CURRENT_VERSION_EXAMPLE_DOCS` is a hardcoded 6-item tuple (`README.md`,
`docs/inventory.md`, `docs/health-checks.md`, `docs/log-analysis.md`,
`docs/log-parsing.md`, `docs/workflows.md`). Independently verified (by
grepping every file under `docs/` and `README.md` for `^Version:` lines and
`"version":` JSON keys) that this list is currently exhaustive — no doc
outside the allowlist currently contains a current-version example that
would go unchecked, and no doc inside the allowlist contains a
false-positive-prone historical reference. So the test correctly closes the
Day 6 carry-forward item as far as the *current* doc set goes.

But the allowlist has no self-check: nothing asserts that every doc under
`docs/` containing a `Version:`/`"version"` current-style example (outside
the explicitly-historical `docs/engineering-reviews/` and `CHANGELOG.md`) is
present in the tuple. A future doc added with a stale current-version
example — e.g. a new `docs/foo.md` copy-pasted from an old doc and never
updated — would silently escape detection unless a contributor remembers to
add the new path to `_CURRENT_VERSION_EXAMPLE_DOCS` by hand.

**Recommended regression test.** A meta-test that walks `docs/`
(excluding `docs/engineering-reviews/`) plus `README.md`, finds every file
containing a `^Version:\s+\d+\.\d+\.\d+` line or a parseable
`` ```json `` block with a top-level `"version"` key, and asserts that set
equals `_CURRENT_VERSION_EXAMPLE_DOCS` exactly — turning "did we remember to
allowlist the new doc" into a test failure instead of a silent gap.

---

### Low — one tautological assertion in an otherwise sound test

**Evidence.** `tests/unit/test_workflow_no_network_no_subprocess.py:100-124`'s
`test_run_workflow_makes_no_subprocess_calls_with_real_doctor_step` ends
with `assert result.steps[0].status in (CheckStatus.PASS, CheckStatus.WARN,
CheckStatus.FAIL)`. `CheckStatus` is a 3-member closed `StrEnum`
(`core/models.py`), so this assertion is true for any value the field could
ever legally hold — it cannot distinguish a correct run from a subtly broken
one and exists only as an "and it didn't crash" smoke check. This does not
weaken the test's actual value: the monkeypatched `subprocess`/`os.system`
raising on any call is the real assertion, and it is a strong one (§ design
note below praises this pattern). This is noted for completeness, not as a
standalone risk — no recommended action beyond tightening the assertion to
something like `status is not None` → `report.summary.steps == 1` (already
implicitly true) if the test is touched again for another reason.

---

## 4. What the Day 7 tests get right (independently confirmed, not just re-read)

- **The AAA/ZZZ marker technique** in both bidi-sanitization matrices
  (`test_cli_report_aggregate.py:275`, `test_cli_workflow.py:...`) is a
  genuinely strong pattern: asserting `f"AAA{escaped}ZZZ" in out` rather than
  a bare `char not in out` proves the character was replaced *in place* by
  its exact escape sequence, and — critically — the same marker technique is
  applied to `\n`/`\r`, which legitimately occur elsewhere in multi-line text
  output, closing exactly the kind of false-negative substring-check gap the
  review brief asked me to look for. I re-derived this independently and
  agree it is not tautological.
- **The shell-metacharacter inertness tests**
  (`tests/unit/test_workflow_shell_metacharacter_inertness.py`) combine three
  independent lines of evidence per payload — a real filesystem canary that
  must not exist, a monkeypatch that raises `AssertionError` on any
  subprocess/`os.system` call, and an assertion that the literal payload
  string appears in the step's `FAIL` error — rather than relying on any one
  of them alone. This is the right shape for proving "data, not code":
  removing any single one of the three checks would still leave the other
  two catching a real regression.
- **The workflow-layer HTTP query-privacy loopback test**
  (`tests/integration/test_workflow_health_loopback.py`, new test) proves
  something stronger than redaction: it confirms the *server* received the
  real, unredacted secret (proving the check still functionally worked) and
  that none of `workflow run`'s three output formats contain it — and does
  so against a real `ThreadingHTTPServer` bound to `127.0.0.1:0` (OS-assigned
  ephemeral port, confirmed via `tests/conftest.py:37-58`), never a fixed
  port.
- **The real-constant boundary tests**
  (`test_report_aggregate.py:450-472`, and the file-size half in
  `test_report_reader.py`) correctly import `MAX_REPORT_COUNT`/
  `MAX_REPORT_FILE_BYTES` from production code rather than hardcoding `50`/
  `5_242_880`, so the tests cannot silently drift from the real constants —
  this is the right pattern, and finding #2 above is about which *branch* of
  the size-check logic they reach, not about the technique itself.
- **`_open_regular_file`/`os.chdir`/no-subprocess boundary**: the generic,
  exhaustive `SRC_ROOT.rglob("*.py")`-based scans in
  `tests/unit/test_runner_no_shell.py` (`test_only_runner_module_imports_subprocess`,
  Day 2) and `tests/unit/test_health_no_forbidden_tokens.py` (Day 5) already
  provide strong, whole-tree structural guarantees that Day 7's
  workflow-specific static scan (`_WORKFLOW_MODULES` in
  `test_workflow_no_network_no_subprocess.py`) supplements rather than
  duplicates. Combined with the one new dynamic real-`doctor`-step proof,
  this is adequate layered coverage of the "workflow file is data, not code"
  claim — I initially suspected a gap here (only 1 of 7 step kinds gets a
  real, unmocked dynamic no-subprocess proof) but the pre-existing generic
  scans make that gap much less material than it first appeared, since no
  module other than `core/runner.py` can import `subprocess` at all,
  regardless of which workflow step kind calls it.
- **JSON-unaffected tests** in both CLI files use `json.loads()` and assert
  against parsed structure (`data["reports"][0]["headline"]`,
  `data["steps"][0]["id"]`), not a substring check on raw stdout — this
  correctly cannot pass by accident the way a naive `"‮" in out` check could.

---

## 5. Regression protection (Day 1–6)

- `git diff HEAD -- tests/` contains **zero deleted assertions** other than
  one test rename/supersession (`test_unicode_formatting_character_sanitized_in_text_output`
  → subsumed into the new parametrized matrix, strictly more coverage, not
  less) and the expected `test_get_version_is_0_6_0` → `test_get_version_is_0_7_0`
  version-bump rename. No other `-` lines touch an existing assertion.
- No test file was deleted or renamed (`git diff HEAD --summary -- tests/`
  shows no delete/rename entries); file count (137 `test_*.py` files) and the
  full 1323-test pass count are consistent with Day 6 plus additive Day 7
  tests only.
- Config, safe-runner, tools, inventory, logs, and health regression suites
  (Day 1–5) were not touched in this diff and passed unchanged in the full
  run (§2).
- `pyproject.toml`'s `dependencies = []` is unchanged; no new import outside
  the standard library was introduced (confirmed independently by the same
  grep the security review performed, re-run in this session).

No regression to Day 1–6 behavior found.

---

## 6. Final verdicts

**Test count:** 1323 passed, 0 failed, 0 skipped (unit + integration, this
session's own run, ~280s wall time).

**Coverage:** 98.49% overall (floor 90%). Changed-module coverage:
`commands/workflow.py` 100%, `core/workflow_models.py` 100%, `core/output.py`
99% (the 2 uncovered branch-partials are pre-existing formatting edge cases,
not part of this diff), `core/report_aggregate.py` 99% (1 uncovered line is
a fail-closed `except ValueError: return None` branch), `core/report_reader.py`
96% (4 uncovered lines are the two TOCTOU gaps in §3 above),
`core/workflow_runner.py` 95% (3 uncovered lines: the absolute-path early
return in `_resolve_relative` — untested but trivial — and the
`inventory_system` branch discussed in §3), `core/workflow_parser.py` 95%
(12 uncovered lines, independently confirmed to be exactly the fail-closed
error-message-formatting branches the security review characterized them
as — I re-derived this from the source myself rather than accepting the
characterization, and it holds).

**Flakiness/reliability:** No fixed ports (`http_loopback_server`/
`tcp_loopback_listener` both bind `("127.0.0.1", 0)`), no wall-clock sleeps
used as correctness gates in the Day 7 diff, no test ordering dependency
observed, no real-`HOME` mutation in the Day 7 diff (isolation patterns from
Day 2 config tests are unaffected). Full suite re-run was deterministic.

**Release blockers: none.** Every finding above is either Medium-but-fail-open-only-under-a-narrow-local-race
(§3 finding 2) or Low (test-hygiene/documentation gaps). None represents a
currently-exploitable defect in shipped behavior — every gap identified is a
gap in the *test suite's* ability to catch a *future* regression, not a
present one. The implementation itself was independently verified correct
for every codepoint/boundary this review checked.

**Strongest test areas:**
1. The shell-metacharacter/canary-file inertness tests — genuinely
   adversarial, triple-redundant, and independently reproducible.
2. The bidi/control-character AAA/ZZZ marker technique — a real fix for the
   "weak substring assertion" failure mode, even though its codepoint
   coverage itself has a gap (§3).
3. The workflow-layer HTTP query-privacy loopback test's server-side
   confirmation — proves the check still functions, not just that output
   is clean, which is the harder and more valuable property to test.

**Highest-value missing tests** (in priority order):
1. `report_reader.py`'s post-read TOCTOU recheck (§3, Medium) — a
   `monkeypatch`d `os.read` test analogous to the existing
   `test_fstat_detects_growth_past_max_bytes`.
2. Deriving the bidi/zero-width parametrized matrix's codepoint set from
   `_FORMATTING_CHAR_TRANSLATION.keys()` directly (§3, Medium) instead of a
   hand-curated subset, so it cannot drift from the implementation again.
3. A dedicated `inventory_system` unit test in
   `test_workflow_runner_step_kinds.py` (§3, Low), plus correcting that
   file's docstring.

**Final test-quality verdict:** The Day 7 test additions are well-designed
and mostly close the real gaps they claim to close — the AAA/ZZZ marker
technique, the real-constant boundary tests, and the triple-redundant
shell-metacharacter proofs are all genuinely strong engineering, not
cosmetic additions. However, two of the eight "CLOSED" carry-forward claims
in the companion security review are narrower than stated: the bidi/control
matrix tests 9 of 15 actually-escaped codepoints while being described as
covering "all representative" ones, and the "actual MAX_REPORT_FILE_BYTES
boundary"/"actual +1 byte rejection" claim is satisfied against the cheapest
of three redundant size guards while the guard specifically designed for a
TOCTOU race — with a code comment naming that exact race — remains
completely untested and was shown, by this review's own adversarial
reproduction, to be a real (if narrow, non-network, same-user-race-only)
bypass if it regressed. I recommend treating this report's two Medium
findings as pre-merge follow-ups rather than release blockers, given the
non-network, same-privilege-level, present-implementation-is-correct nature
of both — but they should not be left open indefinitely, since they are
exactly the kind of narrow-window defense-in-depth gap that erodes silently
under future refactoring pressure ("this recheck looks redundant with the
one above it") without a test to stop it.
