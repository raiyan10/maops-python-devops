# Day 4 v0.4.0 Release Readiness — Final Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Reviewer:** Final release-readiness synthesis, direct hands-on
verification. Every command, source read, and adversarial input in this
document was independently executed or independently re-derived against
the real source, real build artifacts, and real CI workflow on this
branch (Python 3.12.3, ruff 0.16.1) — the three specialist reports below
were read and cross-checked, not copied on faith.
**Date:** 2026-08-06
**Branch reviewed:** `feature/day-4-log-analysis`
**Inputs synthesized:**
[`day-04-python-review.md`](day-04-python-review.md) (architecture/security),
[`day-04-test-review.md`](day-04-test-review.md) (test-suite quality),
[`day-04-release-review.md`](day-04-release-review.md) (packaging/release).
**No implementation file was modified. No commit, push, tag, or publish
was performed.** No `sudo`, no public network access, no real system log
was read, no real `HOME` was written.

---

## 1. Specialist-review summary

| Report | Verdict | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Python architecture/security review | Not release-ready | 1 | 1 | 2 | 3 |
| Test-suite quality review | Not release-ready | 1 | 1 | 4 | 3 |
| Release/packaging review | Not release-ready (same-day fixable) | 1 | 0 | 2 | 1 |

All three reports agree the **shipped package itself** (wheel/sdist
contents, permissions, offline install, dependency surface, CI matrix,
architecture, immutability, fd-safety) is unusually solid for this
project stage. All three also converge on the **same root defect**
from two independent angles: `core/log_parsers.py`'s docstring promise
that "no function ever raises on malformed input" is false for three
distinct, realistic inputs (deep JSON nesting, a far-future RFC3339
timestamp, an oversized numeric literal), and no test in the 17-file Day
4 test suite exercises any of them despite 100% line/branch coverage on
that exact module. The release review separately found the literal
release gate (`make quality`/`make release-check`) fails today for an
unrelated reason (an unformatted Markdown code fence caught by an
unscoped `ruff format --check .`).

## 2. Direct verification performed

This review did not take any of the above on faith. Every headline claim
was independently reproduced against the real, unmodified source in this
session:

- Re-ran all 4 crash PoCs (`RecursionError`, `OverflowError`, 2×
  `ValueError`) directly against `parse_jsonl_line`/`parse_syslog_line`
  — all 4 reproduced exactly as described, and re-run end-to-end through
  the real `maops-py logs parse` CLI, confirming an unhandled Python
  traceback reaches the terminal (not a structured `overall: "fail"`
  report).
- Re-ran the `top_signatures` ANSI-escape-injection PoC — confirmed
  `\x1b` reaches `render_logs_analyze_text()`'s output unsanitized.
- Re-ran the lowercase-`z` RFC3339 rejection — confirmed.
- Independently re-ran `make quality`, `make build`, `make smoke-install`,
  `make release-check` in that order in a fresh shell; `make quality`/
  `make release-check` both fail today at `format-check` with the
  identical root cause the release review describes; `lint`/
  `type-check`/`coverage` all pass cleanly when run standalone;
  `build`/`smoke-install` both pass cleanly.
- Independently verified the installed wheel's default redaction removes
  the smoke fixture's embedded secret from both text and JSON output
  (`grep -c` of the raw secret value against JSON output returns `0`).
- Independently rebuilt a wheel from the extracted sdist in an isolated
  directory — succeeded.
- Independently inspected wheel/sdist archive permissions
  (`0644`/`0755`, uid/gid zeroed) — clean.
- Independently confirmed both `uses:` lines in
  `.github/workflows/python-validation.yml` are pinned to full 40-
  character commit SHAs with version comments, and that no
  action-pin enforcement (e.g. an actionlint/zizmor step) exists in this
  repo — pinning is currently a manual convention, not machine-enforced.
- **One new finding not present in any of the three specialist reports**
  (§6, N1): direct adversarial testing of the redaction engine's
  key/value rule found that a quoted secret value **containing a space**
  is only partially redacted — the value up to the first space is
  replaced, but the remainder of the quoted string (including the
  closing quote) is left in plaintext. This is a real gap inside the
  *documented* pattern set itself, not one of the documented
  out-of-scope limitations.

## 3. Commands run

```
make quality          # FAILS, exit 2, at format-check (unscoped ruff format --check .)
make build             # PASSES
make smoke-install      # PASSES
make release-check       # FAILS, exit 2, same root cause as make quality
```

Standalone (to isolate `quality`'s failing sub-target from the three that
pass):

```
ruff check .                                   # All checks passed! (0)
ruff format --check src tests                  # 127 files already formatted (0)
mypy src                                        # Success: no issues in 25 source files (0)
pytest --cov=maops_pydevops --cov-fail-under=90 # 733 passed, 99.96% coverage (0)
```

## 4. Total tests / coverage

- **733 passed**, 0 failed, 0 skipped-unexpectedly (console-script parity
  tests actually ran, not skipped — `maops-py` resolves on `PATH` in this
  environment).
- **99.96% aggregate coverage**, 100% line/branch on every Day 4 module
  (`log_reader.py`, `log_parsers.py`, `log_redaction.py`,
  `log_analysis.py`, `log_models.py`, `commands/logs.py`) and on
  `cli.py`/`core/output.py`. `--cov-fail-under=90` gate cleared with
  large margin.
- **Coverage-quality caveat (confirmed by direct testing, not just
  cited):** 100%-covered lines in `core/log_parsers.py` still crash the
  process on the four PoC inputs above — coverage measures line
  execution, not input-shape diversity, and this is the exact place that
  matters here.
- Log-subsystem-only run: 300 passed in ~15s across the 17 Day 4 test
  files.
- mypy `--strict`: no issues in 25 source files.

## 5. Package artifacts

- `dist/maops_pydevops-0.4.0.tar.gz`, `dist/maops_pydevops-0.4.0-py3-none-any.whl`.
- Wheel contains exactly the 25 real package modules plus standard
  `dist-info` metadata — no `.pyc`, `__pycache__`, tests, or docs
  leakage (independently listed via `zipfile`).
- Sdist contains `pyproject.toml`, full `src/`, `README.md`, `LICENSE`,
  `MANIFEST.in` — sufficient to rebuild; no `.git`/`.venv`/secrets.
  `src/maops_pydevops.egg-info/SOURCES.txt` is a documented, unavoidable
  setuptools artifact, not an oversight.
- Every wheel entry `0644`; every sdist entry `0644`/`0755`, uid/gid/
  uname/gname zeroed — independently re-verified via `zipfile`/`tarfile`
  inspection in this session.
- `pip show` on an offline (`--no-index`) install of the wheel: `Requires:`
  blank — zero runtime dependencies, confirmed at metadata and
  installed-artifact level, matching `pyproject.toml`'s `dependencies = []`.
- Wheel successfully rebuilt from an isolated extraction of the produced
  sdist (independently reproduced in this review).
- `scripts/verify_wheel.py`'s exact-one-wheel selection independently
  confirmed to abort loudly when a second stale wheel is injected into
  `dist/` (per the release review; re-verified logic by direct code
  read, not re-run destructively against the real `dist/` in this pass).

## 6. Findings carried forward (all independently re-verified)

### Critical

**C1 — Uncaught `RecursionError`/`OverflowError`/`ValueError` crash `logs
parse`/`logs analyze` outright on realistic, non-exotic log content.**
`core/log_parsers.py`'s own docstring ("no function ever raises on
malformed input") is false. Reproduced independently in this session,
both at the function level and end-to-end through the real CLI:

- 60,000-byte deeply nested JSON array (`'[' * 60000`) → `RecursionError`
  in `json.loads()`, only guarded by `except json.JSONDecodeError`.
- `{"message":"edge","timestamp":"9999-12-31T23:59:59-14:00"}` →
  `OverflowError` in `_normalize_timestamp()`'s `parsed.astimezone(UTC)`,
  only guarded by `except ValueError` around `fromisoformat()` two lines
  above.
- A syslog `[pid]` with 5,000 digits, or *any* JSON field (read or not)
  with a 5,000-digit integer literal → `ValueError` from CPython 3.11+'s
  integer-string-conversion digit limit, uncaught in both
  `parse_syslog_line`'s `int(pid_str)` and inside `json.loads()` itself.

No exception handling exists at any layer between these calls and the
process exit — `commands/logs.py` has no `try/except` around
`parse_line(...)`, and `cli.py::main()` has no top-level handler. A
single adversarial or merely buggy-upstream-emitter line, well inside
every default size limit, discards an entire multi-thousand-line run
with a raw traceback instead of the documented `overall: "fail"`,
exit-1 report. **Release blocker.**

**C2 — The literal release gate this review was asked to run,
`make quality`/`make release-check`, fails today (exit 2), independently
reproduced.** `ruff format --check .` is unscoped to the whole repo, not
just `src`/`tests`; `docs/engineering-reviews/day-04-test-review.md` has
one under-formatted embedded Python code fence. Scoped to `src tests`,
formatting is clean. `.github/workflows/python-validation.yml` runs
`make release-check` verbatim, so this also blocks CI on this branch.
Fixed by reformatting the one file and/or scoping the Makefile's
`format`/`format-check`/`lint` targets to `src tests` (matching
`type-check`/`coverage`'s existing scoping). Not a defect in the shipped
package — every artifact-level check independently passes. **Release
blocker as currently defined, but a same-day fix.**

### High

**H1 — `render_logs_analyze_text()`'s `top_signatures` loop bypasses the
control-character sanitization (`_sanitize_for_text()`) applied to every
other message-derived field in the same renderer.** Independently
reproduced: a message containing `\x1b[31m...\x1b[0m` survives
`compute_signature()`'s whitespace-only collapse and reaches the text
report unescaped — the same ANSI/terminal-escape-injection class
`_sanitize_for_text()` exists specifically to close, now open in one
remaining place. JSON output is unaffected. No test in
`test_logs_text_output_control_chars.py` reaches this loop (it uses
`\n`-based probes, which `compute_signature()` already strips before the
gap is ever reached).

### Medium

- **M1 (test-review M4 / python-review M1) — Lowercase RFC3339 `z`/`t`
  offset suffix rejected.** Independently reproduced:
  `_normalize_timestamp("...00z")` → `invalid_timestamp`, while
  `"...00Z"` succeeds. Worse for syslog input, where the whole line
  becomes `malformed_line` (no event) rather than a per-field issue.
  Untested either way.
- **M2 (python-review M2) — The final line truncated mid-line by
  `--max-bytes` is silently handed to the parser as an ordinary short
  line.** Independently reproduced at the exact byte boundary: an
  18-byte, 3-line file read with `max_bytes=17` yields 3 apparently
  normal lines with `byte_limit_reached=True` and no distinct signal on
  the affected line that it is a truncation fragment, not genuine
  content.
- **M3 (release-review M1) — `make smoke-install` validates JSON syntax
  only, never that default redaction actually removed the fixture's
  embedded secret.** Independently confirmed redaction *does* work in
  the installed wheel (manual `grep -c` of the raw secret against JSON
  output returns `0`), but the automated gate itself asserts nothing —
  a future regression that silently disabled default redaction would
  pass `make release-check` undetected.
- **M4 (release-review M2) — CHANGELOG's `[0.4.0]` entry omits that
  `make smoke-install` now builds a log fixture and exercises `logs
  parse`/`logs analyze`.** Confirmed: `git diff` shows a real, tested
  Makefile behavior change with no changelog mention.

### Low

- **L1 (python-review L1) — 8+ digit purely-decimal tokens signature-
  normalize to `<hex>`, not `<num>`.** Independently reproduced:
  `compute_signature("order id 12345678 created")` → `<hex>` (8 digits);
  a 7-digit run correctly yields `<num>`. Cosmetic only — grouping still
  works correctly for deduplication purposes.
- **L2 (python-review L2) — No upper bound on JSONL `pid` magnitude**
  before round-tripping into JSON output (IEEE-754 precision loss risk
  for consumers beyond 2^53).
- **L3 (python-review L3) — `hostname` is modeled but never rendered in
  `logs parse`'s text report** (JSON output retains it).
- **L4 (release-review L1) — `docs/inventory.md`'s example output is
  stale at `0.3.0`.** Independently confirmed: lines 115 and 161 still
  read `"version": "0.3.0"` / `Version: 0.3.0`.
- **L5 (test-review L1–L3)** — wall-clock-bound redaction perf assertions
  (generous margin, low risk); FIFO-only live special-file coverage (a
  single shared code path, defensible); duplicated `_isolated_config_env`
  fixture across two test files (maintenance nit only).

### New finding from this review's own adversarial pass

**N1 — A quoted key/value secret containing an embedded space is only
partially redacted; the remainder of the quoted value (and its closing
quote) leaks in plaintext.** Not identified by any of the three
specialist reports. The key/value redaction rule's `value` group
(`[^"\s,;&]+`) stops at the first whitespace, so:

```
redact_message('password="hunter2 with spaces" trailing')
-> ('password="[REDACTED] with spaces" trailing', True)
```

`"hunter2"` is redacted; `" with spaces"` and the closing `"` are not —
`changed=True` is reported (technically accurate, a match did occur),
which could give an operator false confidence that the *entire* quoted
value was removed. This sits inside the documented pattern set itself
(a `password="..."` quoted value is exactly the shape §"Supported
patterns" #3 in `docs/log-redaction.md` claims to cover), not one of the
doc's already-disclosed limitations (different key names, unusual
shapes, non-`message` fields). Real-world quoted passphrases/API secrets
with embedded spaces are plausible (e.g. `password="correct horse
battery"`). **Recommendation:** widen the `value` capture to permit
internal whitespace up to the closing quote when `oq`/`cq` are present
(e.g. match `[^"]+` inside quotes, `[^"\s,;&]+` outside), and add a
regression test with a multi-word quoted secret. Severity: Medium — a
best-effort redaction feature partially defeated by a plausible,
in-scope input shape is more consequential than the cosmetic Low items
above, but it is not a crash/availability issue like C1.

## 7. Adversarial checks — full results

All performed directly against the real, unmodified source in this
session (not re-stated from the specialist reports):

| Check | Result |
|---|---|
| File replaced between inspection and open (TOCTOU) | Detected via `(st_dev, st_ino)` fstat comparison — code-path re-confirmed correct by reading; not independently raced live in this pass (relies on existing `test_log_reader_safety.py` monkeypatch coverage) |
| Symlink input | Rejected, `is_symlink`, live `os.symlink` probe |
| FIFO input | Rejected, `not_regular_file`, live `os.mkfifo` probe |
| Directory input | Rejected, `is_directory` |
| Nonexistent input | Rejected, `not_found` |
| Overlong line | Skipped, `text=""`, `overlong=True`, never buffered |
| Malformed UTF-8 | `errors="replace"` → U+FFFD substitution, no exception |
| Malformed JSON | `malformed_json` issue, no event |
| Non-object JSON (array/string/number/null/bool) | All 5 rejected as `malformed_json`, "not an object" |
| Invalid JSON field types (message/severity/hostname/source/pid/timestamp) | Each degrades to `null`/`unknown` + `invalid_field_type` issue; event still emitted except when `message` itself is invalid |
| Every syslog PRI severity (0–7) | All 8 map correctly per RFC 5424 `PRI % 8` table |
| PRI 191 (facility 23, severity 7) | Maps to `debug`, facility correctly ignored per documented scope |
| PRI 192 (out of range) | `malformed_line`, "PRI value out of range" |
| Malformed syslog (no timestamp) | `malformed_line`, "no recognizable timestamp" |
| Naive timestamp (no offset) | `(None, None)` — null timestamp, no issue, per spec |
| Invalid timestamp string | `(None, INVALID_TIMESTAMP)` |
| BSD timestamp | `timestamp=None`, `timestamp_raw` preserved verbatim, no issue, no year/tz inferred |
| Secret values — Bearer, URI userinfo, and all 6 key-name families (password/passwd/pwd/token/secret/api_key variants), case-insensitive | All redacted correctly to `[REDACTED]`; **except** quoted values containing spaces (see N1) |
| `--max-events 0` | `events: []`/`events_emitted: 0`, `events_parsed` still counts, `overall: pass` if otherwise clean |
| `--max-lines` exact boundary (N vs N−1) | Exact match: no truncation; one under: `line_limit_reached=True` |
| `--max-bytes` exact boundary (N vs N−1) | Exact match: no truncation; one under: `byte_limit_reached=True`, final fragment silently emitted as an ordinary line (M2) |
| `--max-line-bytes` boundary | Line at exactly the limit passes; one byte over is skipped as overlong |
| Signature normalization collisions | UUID/IPv4/hex/int ordering correct; 8+-digit decimal → `<hex>` not `<num>` (L1); Unicode casefold `ß`→`ss` confirmed; 256-char cap confirmed |
| Out-of-order timestamps | `out_of_order_events` increments correctly; first/last timestamp remain input-order, not min/max |
| Bucket-boundary timestamps (`:59` vs `:00` at 60s) | Correctly split into adjacent buckets |
| Peak-bucket tie | Earliest bucket wins, confirmed |
| No timestamped events | `timestamped_events=0`, `peak_bucket_start=None`, `peak_bucket_count=0` |
| Non-empty file, zero valid events | `overall: fail`, exit `1` |
| Import from unrelated working directory (`/tmp`) | Resolves correctly to the installed package, no cwd-relative import bug |
| Wheel built from produced sdist | Rebuilt successfully in an isolated extraction |
| Unpinned GitHub Action regression | No automated pin-enforcement (actionlint/zizmor) exists in this repo; both current `uses:` lines are correctly SHA-pinned today, but nothing would catch a future unpinned addition except manual review |

## 8. Parser field inventory

| Canonical field | JSONL alias precedence | Type contract |
|---|---|---|
| `timestamp` | `timestamp` → `time` → `ts` | string (RFC3339/ISO-8601) or absent; invalid type → `null` + issue |
| `severity` | `severity` → `level` → `log_level` | string, normalized via alias table; invalid type → `unknown` + issue |
| `hostname` | `hostname` → `host` | string or absent; invalid type → `null` + issue |
| `source` | `source` → `service` → `app` → `logger` | string or absent; invalid type → `null` + issue |
| `message` | `message` → `msg` → `event` | **required** string; missing/wrong type → no event |
| `pid` | `pid` → `process_id` | non-negative int, `bool` explicitly excluded; invalid → `null` + issue |

Syslog: optional `<PRI>` prefix, RFC3339/ISO-8601 or BSD
`MMM DD HH:MM:SS` timestamp, hostname, `source[pid]: message` tail. No
multiline/stack-trace continuation.

## 9. Severity inventory

Ten canonical values, fixed declaration order, never sorted by count:
`trace, debug, info, notice, warning, error, critical, alert, emergency,
unknown`. Alias table (case-folded): `warn→warning`, `err→error`,
`crit→critical`, `fatal→critical`, `emerg→emergency`,
`information→info`. `ERROR_VOLUME_SEVERITIES` = `{error, critical,
alert, emergency}`. All 8 PRI-derived severities independently verified
in §7.

## 10. File-limit evidence

| Flag | Default | Min | Max | Boundary behavior verified |
|---|---|---|---|---|
| `--max-lines` | 10000 | 1 | 1,000,000 | Exact N vs N−1, §7 |
| `--max-bytes` | 10,485,760 | 1024 | 104,857,600 | Exact N vs N−1, §7 (see M2) |
| `--max-line-bytes` | 65536 | 256 | 1,048,576 | Exact-boundary overlong detection, §7 |
| `--max-events` | 1000 | 0 | 10,000 | `0` verified end-to-end, §7 |

## 11. Redaction evidence

All three rule families (Bearer tokens, URI userinfo passwords, 6
key-name families × `=`/`:` delimiter × case-insensitivity) independently
exercised in §7 — all correct except N1 (quoted values with embedded
spaces, partial redaction). `--no-redact` correctly disables the pass
and forces `redacted: false`. Installed-wheel end-to-end redaction
independently confirmed via the smoke fixture (§2, §6/M3).

## 12. Signature evidence

UUID → IPv4 → hex → int substitution order confirmed correct (UUID must
precede hex to avoid partial dash-broken matches). Unicode casefold
(`ß`→`ss`) confirmed. 256-character cap confirmed. One labeling quirk
confirmed (L1: 8+-digit decimal → `<hex>`), functionally harmless for
grouping.

## 13. Time-bucket evidence

`bucket_start = (epoch_seconds // bucket_seconds) * bucket_seconds`
confirmed via direct boundary probe (`:59` vs `:00` split into adjacent
60-second buckets). Peak-bucket earliest-wins tie-break confirmed.
Out-of-order counting confirmed independent of first/last-timestamp
tracking (input order, not value order). No-timestamped-events case
confirmed to yield `null`/`0`, not an error.

## 14. Action-pin evidence

Both `uses:` lines in the sole workflow
(`.github/workflows/python-validation.yml`) are pinned to full
40-character commit SHAs with a `# vX.Y.Z` comment — `actions/checkout`
and `actions/setup-python`. `permissions: contents: read` at workflow
level; no `id-token: write`, no publish step. Python matrix
(`3.11`–`3.14`, `fail-fast: false`) matches `pyproject.toml`'s
`requires-python`/classifiers exactly. No automated pin-enforcement tool
is wired in — a future unpinned `uses:` addition would only be caught by
manual review, not CI (§7).

## 15. Unresolved findings

All findings in §6 are unresolved as of this review (this was a
review-only pass; no implementation file was modified). In priority
order: C1, C2, H1, N1, M1–M4, L1–L5.

## 16. Release blockers

1. **C1** — uncaught `RecursionError`/`OverflowError`/`ValueError` in
   `core/log_parsers.py` crash the process on realistic input. This
   contradicts the module's own documented contract and is a genuine
   availability/DoS-relevant defect for any pipeline running `logs
   analyze` against externally-sourced logs.
2. **C2** — `make quality`/`make release-check`, the literal release gate,
   fails today (exit 2). Same-day fixable (reformat one file and/or
   scope the Makefile targets), but as defined right now this branch
   cannot pass its own release gate.

H1 (ANSI injection in one text-report field) is a real security-relevant
gap but not blocking in the same sense — it affects only the text
renderer's `top_signatures` section under a crafted/malicious log file
and has no crash or data-exfiltration consequence. It should still be
fixed before v0.4.0 given the project's stated hardening posture.

## 17. Overall score

**5.5 / 10 — Not release-ready.** The packaging/artifact chain is
excellent (would score 9/10 alone: clean wheel/sdist, zero deps, correct
permissions, correct CI matrix and pinning, working offline install).
The application-layer hardening claim ("no function ever raises on
malformed input") is contradicted by three independently reproducible
crash inputs in the exact module (`core/log_parsers.py`) whose sibling
module (`core/log_reader.py`) was built specifically to survive hostile
input — the asymmetry between the two modules' actual threat-model
coverage is the single biggest reason this isn't a routine "fix a few
Lows and ship" situation. The release gate itself also does not pass
today, for an unrelated but equally blocking reason.

## 18. Strongest three areas

1. **Filesystem-boundary safety (`core/log_reader.py`)** — pre-open
   `lstat()`, `O_NOFOLLOW`/`O_CLOEXEC`/`O_NOATIME` with correct `EPERM`
   fallback, post-open `fstat()` TOCTOU verification, exact-boundary
   line/byte/line-length handling via the one-byte-probe technique,
   never `mmap`, never a whole-file read. Independently re-verified
   against symlink, FIFO, directory, and exact-boundary adversarial
   inputs in this review with zero gaps found.
2. **Packaging and release artifact correctness** — exactly-right wheel/
   sdist contents, normalized archive permissions, genuinely
   self-contained sdist (rebuilds a wheel in isolation), zero runtime
   dependencies confirmed at both metadata and installed-artifact level,
   correct SHA-pinned CI matrix. All independently re-verified in this
   review, not merely cited.
3. **Deterministic streaming analysis design (`core/log_analysis.py`)**
   — genuinely bounded memory (per-distinct-value aggregates, never a
   per-event list), fixed emission ordering for both severities and
   findings (byte-stable reports across repeated runs), and correct
   epoch-arithmetic bucket/tie-break/out-of-order semantics, all
   independently probed at exact boundaries in this review.

## 19. Five highest-priority improvements

1. Catch `RecursionError`/`OverflowError`/the digit-limit `ValueError`
   at their three specific call sites in `core/log_parsers.py`
   (`json.loads()`, `parsed.astimezone(UTC)`, both `int(pid_str)` sites)
   and convert each to the existing `LogParseIssue` pattern — closes C1.
2. Fix or scope the release gate (`ruff format` either narrowed to
   `src tests` in the Makefile, or the one offending file reformatted)
   so `make release-check` — the thing this entire review exists to
   verify — actually passes on this branch. Closes C2.
3. Wrap `signature.signature` in `_sanitize_for_text()` in
   `render_logs_analyze_text()`'s `top_signatures` loop, matching every
   other message-derived field in the same renderer. Closes H1.
4. Widen the key/value redaction rule's quoted-value capture to include
   internal whitespace up to the closing quote, so a multi-word quoted
   secret is fully redacted rather than partially. Closes N1.
5. Add a Hypothesis-style (or at minimum, hand-authored) adversarial test
   module for `parse_jsonl_line`/`parse_syslog_line` covering the four
   crash shapes plus their near neighbors, and add one
   `grep -q '\[REDACTED\]'`-style assertion to the `smoke-install`
   Makefile recipe so the fixture's stated redaction-verification
   purpose is actually enforced by the gate that runs it (closes the
   test-review's C1 test-gap and the release-review's M3/M1 in one
   motion).

## 20. Final v0.4.0 readiness recommendation

**Do not tag v0.4.0 yet.** Merge is blocked by two independently
confirmed, reproducible issues: a real crash-on-malformed-input defect in
the exact module positioned as this release's hardened new
attack-surface (`core/log_parsers.py`), and a release gate
(`make release-check`) that does not currently pass on this branch. Both
are narrow, well-understood, same-day fixes — none of the three
specialist reviews, nor this synthesis, found anything requiring a
design change, a scope cut, or more than a few hours of focused work.
Once C1 is fixed (with a regression test proving it), C2 is fixed (gate
passes clean), and H1 is closed, this branch is very close to genuinely
release-ready — the packaging chain, fd-safety, streaming-analysis
design, and CI hardening are all already at a standard well above what
"release-ready" requires. N1 and the remaining Medium/Low items are
worth fixing before the tag but are not blockers on their own.
