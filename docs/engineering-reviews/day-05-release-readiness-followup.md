# Day 5 v0.5.0 Release Readiness — Follow-up (Critical/High Fixes)

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Date:** 2026-08-09
**Branch:** `feature/day-5-health-checks`
**Scope:** Fixes for every Critical and High finding confirmed in
[`day-05-release-readiness.md`](day-05-release-readiness.md) (C1, H1).
Medium/Low findings (the network/test/release reviews' M1-M4/L1-L2 items)
are unchanged and remain open — out of scope for this pass, which was
explicitly Critical/High only.
**This pass modified implementation files (`core/health_models.py`,
`core/health_http.py`, `core/health_tcp.py`), tests, `CHANGELOG.md`, and
two docs (`docs/http-health-safety.md`, `docs/health-checks.md`).** No
commit, push, tag, or publish was performed. No `sudo`, no public network
access, no real system state written outside build/test temp directories.

---

## 1. What was fixed

### C1 — Uncaught `UnicodeError`/`UnicodeEncodeError` crashes the entire multi-target `health http`/`health tcp` run

**Root cause:** `socket.getaddrinfo()` runs every `str` hostname through
the `idna` codec unconditionally — even purely-ASCII input — so a
malformed DNS label (an empty segment from a stray double dot, an
over-length label) raises `UnicodeError` from `conn.connect()`
(`core/health_http.py`) or `socket.create_connection()`
(`core/health_tcp.py`). Separately, `http.client`'s request-line encoding
is ASCII-only, so a literal non-ASCII character anywhere in a URL
path/query raises `UnicodeEncodeError` (a `UnicodeError` subclass) from
`conn.request(...)`, independent of DNS/hostname handling entirely.
Neither exception is an `OSError` subclass, so neither was covered by
`_perform_http_attempt`/`_perform_tcp_attempt`'s existing catch list —
both propagated uncaught, crashing the whole `run_bounded_parallel` call
(and therefore the whole CLI invocation) and discarding every other
target's already-obtained result along with the offending one's.

**Fix — three files, following the module's existing structured-failure
pattern exactly:**

1. **`core/health_models.py`** — added `INVALID_TARGET_ENCODING =
   "invalid_target_encoding"` to both `HttpFailureReason` and
   `TcpFailureReason`, extending the existing closed enum rather than
   overloading an existing reason (`dns_error` would have been
   misleading for the non-ASCII-path case, which never involves DNS at
   all — the failure happens in `conn.request()`, after `connect()` has
   already succeeded and `peer_ip` may already be populated).
2. **`core/health_http.py`** — added `except UnicodeError:` in
   `_perform_http_attempt`, mapped to `_outcome(HttpFailureReason.INVALID_TARGET_ENCODING,
   "target hostname or path could not be encoded", clock, start)` —
   retryable, matching every other transport-layer failure in this
   module (the module's own docstring: "every exception this module
   catches... is a transport-layer failure and is always retryable").
   Docstring updated to document why `UnicodeError` is treated as
   ordinary operator-input handling, not "a programming error" the way
   an unlisted exception is.
3. **`core/health_tcp.py`** — identical `except UnicodeError:` addition
   in `_perform_tcp_attempt`, mapped to `TcpFailureReason.INVALID_TARGET_ENCODING`
   with detail `"target hostname could not be encoded"` (no path/query
   concept exists for a TCP target, so only the DNS/IDNA case applies
   here).
4. **`docs/http-health-safety.md`** — the "Failure classification" table
   gained a row for `UnicodeError`/`UnicodeEncodeError` →
   `invalid_target_encoding`, and the surrounding prose now explains why
   this specific exception class is not treated as "a programming error"
   the way the rest of that section's framing implies for anything
   uncaught.
5. **`docs/health-checks.md`** — both the HTTP and TCP "failure reasons"
   lists gained `invalid_target_encoding`.
6. **`CHANGELOG.md`** — the `[0.5.0]` "Added" bullet describing the
   closed failure taxonomy was corrected in place (this version had not
   yet been tagged/released) to list the new reason and note the fix,
   rather than adding a separate "Fixed" entry for a bug that never
   shipped.

All three of the network review's live PoCs re-run directly against the
fixed source:

```
$ maops-py health http "http://example..com/" --retries 0 --format json
...
"failure_reason": "invalid_target_encoding",
"detail": "target hostname or path could not be encoded"
...
"overall": "fail"
EXIT=1   # clean structured report, no traceback

$ maops-py health tcp "example..com:80" --retries 0 --format json
...
"failure_reason": "invalid_target_encoding",
"detail": "target hostname could not be encoded"
...
EXIT=1   # clean structured report, no traceback

# Two-target invocation: one real, already-listening loopback server
# plus one malformed-label target
$ maops-py health http "http://127.0.0.1:<port>/" "http://example..com/" --retries 0 --format json
returncode: 1
overall: fail
  1 http://127.0.0.1:<port>/  pass   <- previously silently discarded
  2 http://example..com/      fail

# Non-ASCII path character (independent of DNS/IDNA entirely)
$ maops-py health http "http://127.0.0.1:<port>/‮abc" --retries 0 --format json
returncode: 1
results[0].status: fail
results[0].attempts[0].failure_reason: invalid_target_encoding
```

The healthy target's result is now correctly preserved alongside the
malformed target's structured failure, instead of the whole report being
silently discarded.

### H1 — The documented `--retries 5` maximum boundary was never exercised at the unit level

**No source change required** — the retry loop
(`max_attempts = options.retries + 1`, `range(1, max_attempts + 1)`) has
no special-casing tied to any specific `retries` value, and was
independently confirmed correct by direct code reading before writing the
new tests. This was purely a test-coverage gap: every prior test in
`test_health_retry_state_machine.py` scripted at most 4 retries, and the
one CLI-level test at `retries=5` used an always-succeeds mock that never
reached exhaustion.

**Fix:** added `test_retries_5_is_true_maximum_six_attempts_never_succeeds`
(HTTP) and `test_tcp_retries_5_is_true_maximum_six_attempts_never_succeeds`
(TCP) to `test_health_retry_state_machine.py`, each scripting 6
consecutive retryable failures at `retries=5` and asserting
`len(calls) == 6`, `attempts_used == 6`, `status is CheckStatus.FAIL`, and
exactly 5 sleep calls at the configured delay — closing exactly the gap
the test review identified.

## 2. Regression tests added

| File | New test(s) | Proves |
|---|---|---|
| `tests/unit/test_health_http_attempt.py` | `test_malformed_label_hostname_encoding_mapped`, `test_non_ascii_path_encoding_mapped` | Both HTTP-side C1 crash PoCs now degrade to a structured `invalid_target_encoding` failure instead of raising |
| `tests/unit/test_health_tcp_attempt.py` | `test_malformed_label_hostname_encoding_mapped` | The TCP-side C1 crash PoC degrades correctly |
| `tests/integration/test_health_http_loopback.py` | `test_malformed_target_does_not_discard_other_targets_results` | A real two-target CLI invocation (one healthy loopback server, one malformed-label target) no longer crashes — both targets' results appear in the report |
| `tests/integration/test_health_tcp_loopback.py` | `test_malformed_target_does_not_discard_other_targets_results` | Same proof for the TCP CLI path |
| `tests/unit/test_health_retry_state_machine.py` | `test_retries_5_is_true_maximum_six_attempts_never_succeeds`, `test_tcp_retries_5_is_true_maximum_six_attempts_never_succeeds` | The documented `--retries 5`/6-attempts/never-succeeds boundary is now exercised for both protocols |

All new tests were run and pass; none existed before this pass. The two
loopback integration tests are genuine regression tests for the exact
discard-everything behavior the network review demonstrated live — they
would have failed against the pre-fix source (confirmed by running them
against a `git stash` of the source fix before writing this document,
mirroring the Day 4 followup's verification discipline).

## 3. Verification

### Targeted PoC re-run (direct function calls + end-to-end CLI)

```
malformed-label (HTTP)     : OK, status=fail, failure_reason=invalid_target_encoding
malformed-label (TCP)      : OK, status=fail, failure_reason=invalid_target_encoding
non-ascii path (HTTP)      : OK, status=fail, failure_reason=invalid_target_encoding
two-target discard scenario: OK, both targets present, healthy target still "pass"
retries=5 exhaustion (HTTP): OK, attempts_used=6, status=FAIL, 5 sleeps
retries=5 exhaustion (TCP) : OK, attempts_used=6, status=FAIL, 5 sleeps
```

### Full gate re-run, in order

```
python -m pytest tests/unit tests/integration -q \
    --cov=src/maops_pydevops --cov-report=term-missing
  -> 1005 passed, TOTAL coverage 99.05%
     (was 998 passed / 99.05% pre-fix; +7 new tests, coverage held)
     core/health_http.py   94% (crash lines now covered by non-crashing
                                 AND crashing-turned-graceful inputs)
     core/health_tcp.py    97%
     core/health_models.py 100%
EXIT_CODE=0

python -m mypy src/maops_pydevops --strict
  -> Success: no issues found in 30 source files            EXIT=0

ruff check src tests        -> All checks passed!            EXIT=0
ruff format --check src tests -> 150 files already formatted EXIT=0

make build           -> Successfully built sdist + wheel, permissions normalized   EXIT=0
make smoke-install    -> doctor/tools/inventory/logs/health steps all pass,
                          JSON valid, health_smoke_check.py exits 0 silently        EXIT=0
```

`make quality`/`make release-check` were not independently re-run a
second time end-to-end in this pass beyond the equivalent standalone
commands above (already confirmed passing against the pre-fix source in
the synthesis review, and the fix touches only `core/health_*.py`
exception handling plus tests/docs — no change to the packaging,
CI, or Makefile surface those targets exercise beyond what `make build`/
`make smoke-install` above already re-confirm).

## 4. Test count and coverage delta

| | Before this pass | After this pass |
|---|---|---|
| Total tests | 998 | 1005 (+7) |
| Aggregate coverage | 99.05% | 99.05% |
| `core/health_http.py` coverage | 94% (crash lines covered, crash itself untested) | 94% (crash lines now genuinely exercise the new `except UnicodeError` branch) |
| `core/health_tcp.py` coverage | 97% (same pattern) | 97% (same fix) |
| C1 (crash on malformed/non-ASCII target) | Present, live-reproduced | Fixed, regression-tested at both unit and CLI/integration level |
| H1 (untested `retries=5` boundary) | Present | Fixed — both protocols now tested at the true maximum |

## 5. What was deliberately not touched

Per the task scope ("Fix all verified Critical and High findings"), the
following confirmed-but-lower-severity findings from the synthesis review
remain open and unmodified in this pass:

- **Network review M1** — Unicode bidi-override/zero-width characters
  still bypass `_sanitize_for_text()`'s ASCII-only control-character
  escaping.
- **Network review L1-L2** — fixed non-jittered retry delay at scale
  (documented, deliberate); a handful of defensive branches remain
  untested (but confirmed correct by code reading).
- **Test review M1-M4** — `commands/health.py:172` (TCP-only `overall:
  warn`) still 0%-covered; JSON field-type checks still skip several
  `Options`/`Summary` primitives; the real outbound query value is still
  proven only at the unit level, not via the loopback integration suite;
  TCP loopback integration still lacks an HTTP-equivalent
  reversed-completion-order test.
- **Test review L1-L2** — `MIN_TARGETS` still untested in isolation at
  the `build_health_*_report` level; concurrency tests still use real
  (generously-margined) thread scheduling rather than fully synthetic
  timing.
- **Release review M1-M2** — no regression test protects the health smoke
  script's `Makefile` wiring itself; `CHANGELOG.md` still doesn't mention
  that `smoke-install` now exercises real network I/O against the
  installed wheel (beyond the C1-specific note added to the existing
  `[0.5.0]` "Added" bullet in this pass).
- **Release review L1** — `docs/log-parsing.md`/`docs/log-analysis.md`
  still show a stale `0.4.0` example version.

None of these block a release on their own; they were intentionally left
for a separate pass since this task was explicitly scoped to
Critical/High only.

## 6. Updated readiness status

Both findings confirmed in the synthesis review are now fixed, tested,
and independently re-verified:

- **C1 (crash on malformed-label/non-ASCII targets)** — fixed,
  regression-tested at both the unit level (both protocols, both crash
  shapes) and the CLI/integration level (the exact
  discard-everything-in-the-batch scenario), re-run clean end to end
  through the real CLI.
- **H1 (untested `retries=5` maximum boundary)** — fixed via new tests
  for both protocols; no source defect existed.

**This branch is no longer blocked by any Critical or High finding.** The
release/packaging chain was already independently confirmed clean in the
synthesis review and is unaffected by this pass's changes (re-confirmed
via `make build`/`make smoke-install` above). The remaining open items
(§5) are Medium/Low and do not, on their own, block a v0.5.0 tag per the
synthesis review's stated bar — but they should still be triaged before
release, consistent with that review's five highest-priority-improvements
list (items 3-5 of that list, covering the Unicode-sanitization gap and
the two release-review Medium findings, remain the most consequential of
what's left).
