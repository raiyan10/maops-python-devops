# Day 4 v0.4.0 Release Readiness — Follow-up (Critical/High Fixes)

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Date:** 2026-08-06
**Branch:** `feature/day-4-log-analysis`
**Scope:** Fixes for every Critical and High finding confirmed in
[`day-04-release-readiness.md`](day-04-release-readiness.md) (C1, C2,
H1). Medium/Low findings (M1–M4, L1–L5, N1) are unchanged and remain
open — out of scope for this pass, which was explicitly Critical/High
only.
**This pass modified implementation files, tests, docs, and the
Makefile.** No commit, push, tag, or publish was performed. No `sudo`,
no public network access, no real system log was read, no real `HOME`
was written.

---

## 1. What was fixed

### C1 — Uncaught `RecursionError`/`OverflowError`/`ValueError` in `core/log_parsers.py`

Three call sites, three narrow fixes, all converting a previously-fatal
exception into the module's existing structured `LogParseIssue` pattern:

1. **`parse_jsonl_line`'s `json.loads(text)` call.** Broadened
   `except json.JSONDecodeError` to `except (json.JSONDecodeError,
   RecursionError, ValueError)`. `JSONDecodeError` is already a
   `ValueError` subclass, so this is a pure widening, not a behavior
   change for the existing malformed-JSON path — it additionally catches
   deep-nesting `RecursionError` and CPython 3.11+'s integer-string-
   conversion `ValueError` (which `json.loads` itself raises while
   tokenizing *any* oversized numeric literal in the document, including
   fields this package never reads). Both now report the same
   `malformed_json` issue, no event.
2. **`_normalize_timestamp`'s `parsed.astimezone(UTC)` call.** Added a
   dedicated `try/except OverflowError`, since a syntactically valid but
   calendar-extreme RFC3339 timestamp (e.g. year 9999 with a large
   negative offset) overflows `datetime`'s representable range on UTC
   conversion — a separate failure mode from the `ValueError` the
   existing `try/except` around `fromisoformat()` already caught. Now
   reports `invalid_timestamp`, matching the existing invalid-timestamp
   contract; the event is still emitted (JSONL) or the line is still
   accepted with `timestamp=None` (syslog), per the module's established
   degrade-not-reject convention.
3. **`parse_syslog_line`'s `int(pid_str)` call.** The `[pid]` capture
   group is an unbounded `\d+`, so a digit run past the interpreter's
   digit limit previously crashed here directly. Now wrapped in
   `try/except ValueError`, degrading `pid` to `None` plus a new
   `invalid_field_type` issue — mirroring exactly how the JSONL parser
   already handles an invalid `pid` field, rather than rejecting the
   whole line as `malformed_line` (the line is otherwise well-formed;
   only the digit run is pathological).

All four original PoCs re-run directly against the fixed functions and
end-to-end through the real `maops-py logs parse` CLI: no exception
propagates in any case; each now yields a clean, valid JSON report.

### C2 — `make quality`/`make release-check` failing at `format-check`

Both remediations the release review offered were applied, not just one:

1. **Immediate:** `ruff format docs/engineering-reviews/day-04-test-review.md`
   — the one under-formatted embedded code fence is now clean.
2. **Structural:** `Makefile`'s `format`, `format-check`, and `lint`
   targets are now scoped to `src tests` (`ruff format src tests`,
   `ruff format --check src tests`, `ruff check src tests`), matching
   `type-check` (`mypy src`) and `coverage`
   (`--cov=maops_pydevops`)'s existing scoping. This closes the release
   review's stated recurrence risk: any future Markdown/docs edit with
   an embedded code fence, or a future `ruff` minor-version bump that
   changes what it sweeps into an unscoped `.` target, can no longer
   fail the release gate over content outside `src`/`tests`.

### H1 — `top_signatures` text rendering bypassed control-character sanitization

`render_logs_analyze_text()`'s `top_signatures` loop now wraps
`signature.signature` in the same `_sanitize_for_text()` call already
applied to `event.message`, `event.source`, and `source.source`
elsewhere in the same renderer (`core/output.py`). A crafted message
containing a raw ESC byte (`\x1b`) — which survives
`compute_signature()`'s whitespace-only collapse — now renders as the
literal escape sequence `\x1b[` in text output instead of reaching the
terminal unescaped. JSON output was never affected (`json.dumps` already
escapes control characters unconditionally).

## 2. Regression tests added

| File | New test(s) | Proves |
|---|---|---|
| `tests/unit/test_log_parsers_jsonl.py` | `test_deeply_nested_json_does_not_raise_recursion_error`, `test_oversized_integer_literal_does_not_raise_value_error`, `test_oversized_pid_integer_literal_does_not_raise_value_error`, `test_rfc3339_timestamp_overflowing_utc_conversion_does_not_raise` | All 4 original JSONL-side crash PoCs now degrade to a structured issue instead of raising |
| `tests/unit/test_log_parsers_syslog.py` | `test_oversized_pid_digit_run_does_not_raise_value_error`, `test_rfc3339_timestamp_overflowing_utc_conversion_does_not_raise` | The syslog-side `pid` crash PoC and the shared `_normalize_timestamp` overflow path both degrade correctly |
| `tests/unit/test_logs_text_output_control_chars.py` | `test_ansi_escape_in_message_cannot_reach_top_signatures_unsanitized` | A non-whitespace control character (ESC) in a repeated message's signature can no longer reach text output unescaped — the existing `\n`-based tests in this file structurally could not have caught this, since whitespace collapse already strips `\n` before the unsanitized call site would have been reached |

All new tests were run and pass; none existed before this pass (verified
by `git status` showing these as new hunks in previously-tracked test
files, and confirmed failing against the pre-fix source before the
implementation changes were applied).

## 3. Verification

### Targeted PoC re-run (direct function calls + end-to-end CLI)

```
deep-nesting            : OK, event=no,  issue=malformed_json
ts-overflow              : OK, event=yes, issue=invalid_timestamp
syslog-huge-pid           : OK, event=yes, issue=invalid_field_type
json-huge-int-anywhere     : OK, event=no,  issue=malformed_json
normal-jsonl (sanity)       : OK, event=yes, issue=None
normal-syslog-pid (sanity)   : OK, event=yes, issue=None

$ maops-py logs parse recursion.log --input-format jsonl --format json
{ "version": "0.4.0", ... }   # clean report, exit 0, no traceback

$ maops-py logs parse overflow.log --input-format jsonl --format json
{ "version": "0.4.0", ... }   # clean report, exit 0, no traceback
```

### H1 re-run

```python
forged_message = "alert \x1b[31mFAKE RED TEXT\x1b[0m end"
# -> "\x1b[" in render_logs_analyze_text(report)  ->  False  (was True)
# -> "\\x1b[" in render_logs_analyze_text(report)  ->  True   (escaped form present)
```

### Full gate re-run, in order

```
make quality
  ruff format --check src tests   -> 127 files already formatted   (0)
  ruff check src tests            -> All checks passed!            (0)
  mypy src                        -> Success: no issues in 25 source files (0)
  pytest --cov=maops_pydevops --cov-fail-under=90
    -> 740 passed, TOTAL coverage 99.96%, 100% on every Day 4 module
       including core/log_parsers.py (was 97% immediately after the
       fix, before tests were added; back to 100% now)               (0)
EXIT_CODE=0

make build           -> Successfully built sdist + wheel, permissions normalized   (0)
make smoke-install    -> doctor/tools/inventory/logs steps all pass, JSON valid    (0)
make release-check     -> quality + build + smoke-install, all clean end to end    (0)
```

`make quality` and `make release-check` — the exact release gate that
was failing in the prior review — now both exit `0` on this branch,
independently re-run in a fresh shell after every source/test change in
this pass.

## 4. Test count and coverage delta

| | Before this pass | After this pass |
|---|---|---|
| Total tests | 733 | 740 (+7) |
| Aggregate coverage | 99.96% | 99.96% |
| `core/log_parsers.py` coverage | 100% (but missed the failure branches — see the original review's coverage-quality caveat) | 100%, now genuinely exercising all three new exception-handling branches |
| `make quality` | FAILS (exit 2) | PASSES (exit 0) |
| `make release-check` | FAILS (exit 2) | PASSES (exit 0) |

## 5. What was deliberately not touched

Per the task scope ("Fix all verified Critical and High findings"), the
following confirmed-but-lower-severity findings from the original review
remain open and unmodified in this pass:

- **M1** — lowercase RFC3339 `z`/`t` offset suffix still rejected.
- **M2** — the final `--max-bytes`-truncated line is still silently
  handed to the parser as an ordinary short line, with no distinct
  truncation-fragment signal.
- **M3** — `make smoke-install` still validates JSON syntax only, not
  that default redaction actually removed the fixture's secret.
- **M4** — `CHANGELOG.md`'s `[0.4.0]` entry still omits the
  `smoke-install` logs-fixture behavior change.
- **L1–L5** — signature `<hex>`-vs-`<num>` labeling, unbounded JSONL
  `pid` magnitude, `hostname` omitted from `logs parse` text output,
  `docs/inventory.md`'s stale `0.3.0` example, and the three
  test-quality Low items.
- **N1** — the quoted-value-with-embedded-spaces partial-redaction gap
  found during the original review's own adversarial pass.

None of these block a release on their own; they were intentionally left
for a separate pass since the task instruction scoped this one to
Critical/High only.

## 6. Updated readiness status

Both Critical findings and the one High finding confirmed in the
original review are now fixed, tested, and independently re-verified:

- **C1 (crash-on-malformed-input)** — fixed, regression-tested, PoCs
  re-run clean end-to-end through the real CLI.
- **C2 (release gate failure)** — fixed both immediately (reformatted
  the offending file) and structurally (Makefile scoping), `make
  release-check` now passes clean.
- **H1 (ANSI-injection in `top_signatures`)** — fixed, regression-tested.

**This branch is no longer blocked by any Critical or High finding.**
The remaining open items (§5) are Medium/Low and do not, on their own,
block a v0.4.0 tag per the original review's stated bar — but they
should still be triaged before release, consistent with the original
review's five highest-priority-improvements list (items 4 and 5 of that
list, covering N1 and the smoke-install redaction assertion, remain the
most consequential of what's left).
