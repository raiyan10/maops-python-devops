# Day 4 v0.4.0 Release and Packaging Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Reviewer:** Independent engineering review, direct hands-on verification.
Every command in this document was actually executed by the reviewing
session against the real source, real build artifacts, and real GitHub
Actions workflow file on this branch (Python 3.12.3, ruff 0.16.1) — no
finding here is inferred, estimated, or taken from doc/comment claims on
faith.
**Date:** 2026-08-06
**Branch reviewed:** `feature/day-4-log-analysis`
**Scope:** Release and packaging readiness for v0.4.0 only — authoritative
version consistency, changelog correctness, wheel/sdist contents and
permissions, build-from-sdist, offline wheel installation, exact-wheel
selection, smoke-fixture isolation and redaction verification, dependency
surface, GitHub Actions matrix/pinning/permissions, and release-check
ordering. This review does **not** re-cover application source correctness
or test-suite quality — those are the subject of the two companion Day 4
reviews (`day-04-python-review.md`, `day-04-test-review.md`), both of which
independently found real Critical/High source-level issues; this review's
findings are scoped strictly to the packaging/release chain and are
otherwise independent of those two.
**Review only. No implementation file under `src/` was modified.** No
commit, push, tag, or publish was performed as part of this review.

---

## Commands run

Per the task brief, the four required commands were run in order:

```
make quality
make build
make smoke-install
make release-check
```

Plus, once `make quality` failed, each of its four sub-targets
(`format-check`, `lint`, `type-check`, `coverage`) standalone to isolate
exactly which check was failing; a real `python -m build` from an isolated
extraction of the produced sdist; a fresh-venv offline install via
`pip install --no-index --find-links dist/`; a wheel/sdist archive
inspection (`python -m zipfile -l`, `tar -tzf`, permission/uid/gid dumps);
an adversarial exact-wheel-selection test (injecting a stale second wheel
into `dist/`); a manual, un-piped re-run of the `smoke-install` recipe's
`logs parse`/`logs analyze` steps to inspect real output instead of
discarding it to `/dev/null`; and `git status` before/after every step to
confirm no repo pollution.

### `make quality` — **FAILS** (exit 2, at `format-check`)

```
$ source .venv/bin/activate && make quality
ruff format --check .
unformatted: File would be reformatted
   --> docs/engineering-reviews/day-04-test-review.md:185:22
    |
184 | dt = datetime.fromisoformat("1969-12-31T23:59:59.500000+00:00")
    - int(dt.timestamp())        # -> 0   (bucket 1970-01-01T00:00:00)
185 + int(dt.timestamp())  # -> 0   (bucket 1970-01-01T00:00:00)
186 | math.floor(dt.timestamp())  # -> -1  (bucket 1969-12-31T23:59:00, with bucket_seconds=60)
    |

1 file would be reformatted, 161 files already formatted
make: *** [Makefile:39: format-check] Error 1
EXIT_CODE=2
```

Because `make` stops at the first failing prerequisite, `lint`/
`type-check`/`coverage` never ran as part of `make quality`. Run standalone
for complete evidence, all three are clean:

```
$ make lint          # ruff check .           -> All checks passed!            EXIT=0
$ make type-check     # mypy src               -> Success: no issues found in 25 source files   EXIT=0
$ make coverage        # pytest --cov          -> 733 passed, TOTAL 99.96% coverage             EXIT=0
```

### `make build` — **PASSES**

```
$ make build
rm -rf build dist src/maops_pydevops.egg-info
python3 -m build
...
Successfully built maops_pydevops-0.4.0.tar.gz and maops_pydevops-0.4.0-py3-none-any.whl
python3 scripts/normalize_archive_permissions.py dist
normalized: dist/maops_pydevops-0.4.0-py3-none-any.whl
normalized: dist/maops_pydevops-0.4.0.tar.gz
EXIT=0
```

### `make smoke-install` — **PASSES**

```
$ make smoke-install
dist/maops_pydevops-0.4.0-py3-none-any.whl
0.4.0
MAOps Python DevOps Toolkit - Doctor Report
Version:              0.4.0
...
Required checks: all [PASS]
Optional tools:  git [PASS], docker [PASS], kubectl [WARN not found],
                  terraform [PASS], ansible [WARN not found]
Overall status: PASS
0.4.0
/tmp/tmp.PISd2DDF9P/home/.config/maops-py/config.toml
EXIT=0
```

(The remaining piped `tools inspect`/`inventory system`/`inventory
filesystem`/`logs parse`/`logs analyze` steps, each validated through
`python -m json.tool >/dev/null`, all completed with no error.)

### `make release-check` — **FAILS** (same root cause as `make quality`)

```
$ make release-check
ruff format --check .
unformatted: File would be reformatted
   --> docs/engineering-reviews/day-04-test-review.md:185:22
    ...
1 file would be reformatted, 161 files already formatted
make: *** [Makefile:39: format-check] Error 1
EXIT=2
```

`build`/`smoke-install` never ran as part of `release-check` because
`quality`'s `format-check` step aborted the chain first — correct fail-fast
behavior (see the Release-check ordering finding below); it is simply
tripped today by a non-`src`/`tests` file.

---

## Critical

### C1 — The exact release gate this review was asked to verify, `make quality` / `make release-check`, fails today, reproducibly (exit 2)

`ruff format --check .` is unscoped — it runs against the whole repository
root, not just `src`/`tests`. ruff 0.16.1 formats embedded Python code
fences inside Markdown files by default, and one file in the working tree,
`docs/engineering-reviews/day-04-test-review.md` (a companion review doc
added alongside this one, not `src/` or `tests/` code), has one
under-formatted code fence:

```
$ ruff format --check .
unformatted: File would be reformatted
   --> docs/engineering-reviews/day-04-test-review.md:185:22
1 file would be reformatted, 161 files already formatted

$ ruff format --check src tests
127 files already formatted
```

Scoping the identical check to `src tests` passes cleanly — confirming the
package and test suite themselves are correctly formatted, and the failure
is entirely attributable to the unscoped `.` target picking up an unrelated
Markdown file. 20 other Markdown files with embedded code fences are
already format-clean; only this one isn't.

**Why this is Critical:** the task driving this review is explicitly to
run `make quality`/`make build`/`make smoke-install`/`make release-check`
and assess release readiness against that gate. As of this review, the
actual named release gate does not pass — `make release-check` exits 2
before `build` or `smoke-install` (both of which independently pass) ever
run. `.github/workflows/python-validation.yml` runs `make release-check`
verbatim, so this will also block CI on this branch the moment this or any
similarly-unformatted Markdown file lands in a PR against `main`. This is
not a defect in the shipped package, wheel, sdist, or artifact chain — all
of those are independently verified clean elsewhere in this report — but
it is a genuine, currently-blocking failure of the release process itself,
and it is fixed by nothing more than reformatting one file or narrowing
the Makefile's scope, so it should not block long.

It is also a latent, recurring risk, not a one-off: `format`/`format-check`
(and `lint`) are unscoped to `.` while `type-check` (`mypy src`) and
`coverage` (`--cov=maops_pydevops`) are correctly scoped to the shipped
package. Any future Markdown/docs edit with an embedded code fence — or any
future `ruff` release within the current `ruff>=0.6,<1.0` pin that changes
what file types/constructs it formats by default — can retrigger this
identical failure mode without any change to `src/` or `tests/` at all.

**Recommendation:**
1. Immediate: `ruff format docs/engineering-reviews/day-04-test-review.md`
   (or `ruff format .`) to unblock this branch's `make quality`/
   `make release-check` before merge.
2. Structural: scope the Makefile's `format`/`format-check`/`lint` targets
   to `src tests` explicitly, matching `type-check`'s and `coverage`'s
   existing scoping, so the release gate is deterministically about the
   shipped package and its tests rather than incidentally about whatever
   prose is in the working tree at build time. If Markdown-embedded-code
   formatting is genuinely wanted, make that an explicit, separately
   documented target rather than folding it unscoped into the release gate.

---

## High

No High-severity findings. Every artifact-level check that could plausibly
have produced a High finding (wheel contents, sdist contents, archive
permissions, sdist self-containment, offline installability, exact-wheel
selection, CI matrix/pinning/permissions) came back clean under direct,
hands-on verification — see "What holds up well" below.

---

## Medium

### M1 — `make smoke-install`'s `logs` steps validate JSON syntax only; they never assert that default redaction actually removed the fixture's embedded secret

`scripts/smoke/make-log-fixture.py`'s own docstring/embedded constant
states its purpose plainly:

```python
SMOKE_SECRET_VALUE = "smoke-test-secret-do-not-use-1234567890"  # Never a real credential.
```

— i.e. the fixture deliberately embeds a secret-shaped value specifically
so the smoke flow can confirm default redaction works against the
*installed* artifact, not just the dev tree. But the Makefile's actual
`smoke-install` recipe only does:

```
"$$tmp_dir/venv/bin/maops-py" logs parse "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null
"$$tmp_dir/venv/bin/maops-py" logs analyze "$$smoke_log" --input-format auto --format json | "$$tmp_dir/venv/bin/python" -m json.tool >/dev/null
```

— i.e. it only checks the output is syntactically valid JSON, never that
the secret is actually redacted. Manually reproducing the same steps and
inspecting output instead of discarding it confirms redaction genuinely
does work correctly in the installed wheel:

```
$ maops-py logs parse "$smoke_log" --input-format auto
  [WARNING  ] line      3 2026-08-06T04:00:10+00:00 smoke-api  password=[REDACTED] login attempt rejected

$ maops-py logs parse "$smoke_log" --input-format auto --format json \
    | grep -c "smoke-test-secret-do-not-use-1234567890" || echo "NOT FOUND (redacted)"
0
NOT FOUND (redacted)
```

So redaction is not broken — but the release gate that is supposed to
verify it at the release-artifact level does not actually check it. A
future regression that silently disabled default redaction would pass
`make smoke-install`/`make release-check` undetected; it would only be
caught by the dev-tree unit/integration suite (`test_log_redaction.py`,
`test_cli_logs_parse.py`), which doesn't run against the installed wheel.

**Recommendation:** add one `grep -q '\[REDACTED\]'` /
`grep -qv 'smoke-test-secret'`-style assertion (or an inline Python check)
on the `logs parse`/`logs analyze` JSON output inside the `smoke-install`
recipe, so the fixture's stated purpose is actually enforced by the gate
that runs it, not just achievable by manual inspection.

### M2 — CHANGELOG.md's `[0.4.0]` entry omits a real, tested Makefile/CI-facing change: `make smoke-install` now builds a log fixture and exercises `logs parse`/`logs analyze`

The `[0.4.0]` entry's `### Changed` section lists only a `docs/
subprocess-safety.md` table update. But `git diff` against the prior
release shows a real, functional `Makefile` change in this diff — the
`smoke-install` target now creates `scripts/smoke/make-log-fixture.py`'s
output and runs `logs parse`/`logs analyze` against it — backed by a real
new test (`tests/unit/test_makefile_smoke_install.py::
test_smoke_install_exercises_logs_parse_and_analyze`) and a new script
(`scripts/smoke/make-log-fixture.py`), neither mentioned in the changelog.
A reader of CHANGELOG.md would not know the release-artifact smoke gate
now covers `logs` at all.

**Recommendation:** add a `### Changed` (or `### Added`) bullet noting that
`make smoke-install` now builds a synthetic log fixture and exercises
`logs parse`/`logs analyze` end-to-end against the installed wheel.

---

## Low

### L1 — `docs/inventory.md`'s example output is stale at `0.3.0`, one release behind

`docs/inventory.md` (added Day 3, untouched by the Day 4 diff) still shows
`"version": "0.3.0"` / `Version: 0.3.0` in its example JSON/text output
blocks, e.g.:

```
$ sed -n '108,165p' docs/inventory.md
  "version": "0.3.0",
  ...
Version:               0.3.0
```

Cosmetic — a doc example's illustrative output, not a functional or
packaging defect, and it predates this diff — but it is a real,
currently-live cross-reference staleness at v0.4.0 that a documentation
accuracy pass should catch.

**Recommendation:** update the example output in `docs/inventory.md` to
`0.4.0` (or genericize it, e.g. `"version": "<current>"`, to avoid this
class of drift on every future release).

---

## Future

- **Narrow or pin the formatting scope more deliberately** so C1's root
  cause can't silently recur: either an explicit `[tool.ruff]`
  `include`/`exclude` in `pyproject.toml` documenting the intended
  formatting surface, or a narrower `ruff` version pin, so a future
  minor-version bump within the current `ruff>=0.6,<1.0` range can't again
  change what file types get swept into the unscoped `.` target without
  anyone noticing until `make release-check` breaks.
- **No PyPI publish workflow exists yet — confirmed deliberate, not a
  gap.** `docs/roadmap.md` explicitly lists a PyPI publish workflow under
  "Post-v0.4.0 possibilities... not committed, scheduled, or designed yet."
  This review found no publish surface, no `id-token: write`, and no
  artifact-upload step anywhere in `.github/workflows/`, which matches that
  stated scope exactly — noted here for completeness, not as a finding.
- **Consider a release-check step that installs offline and re-runs the
  redaction smoke assertion (M1) as a matter of course**, rather than only
  as something an ad hoc reviewer verifies by hand — this would also give
  the exact-wheel-selection and archive-permission checks already done ad
  hoc in this review (verified here by hand, both clean) a permanent,
  automated home in the release chain rather than relying on periodic
  manual review to catch regressions.

---

## What holds up well

Documented for balance, since a findings-only report understates what was
independently verified and passed:

- **Version consistency is enforced by an automated test, not just
  convention**: `tests/unit/test_version.py::
  test_matches_changelog_latest_entry` regex-parses CHANGELOG.md's newest
  `## [x.y.z]` heading and asserts equality with `get_version()`. Both
  agree at `0.4.0` today. `version.py::get_version()` is genuinely lazy
  (`importlib.metadata.version(...)` at call time), no import-time side
  effects, and `grep -rn "0\.4\.0|__version__" src/` finds no duplicated
  literal anywhere in `src/`.
- **Wheel contents are exactly right**: `python -m zipfile -l` on the built
  wheel shows only the 25 real Day 1–4 package modules plus standard
  `dist-info` metadata — no `.pyc`, no `__pycache__`, no test files, no
  `docs/`/`scripts/` leakage.
- **Sdist contents are exactly right**: `tar -tzf` shows `pyproject.toml`,
  full `src/`, `README.md`, `LICENSE`, `MANIFEST.in` — sufficient to
  rebuild, with no `.git`/`.venv`/caches/secrets leaked. The one apparent
  stray file (`src/maops_pydevops.egg-info/SOURCES.txt`) is a documented,
  previously-investigated, unavoidable setuptools force-include (see the
  CHANGELOG's `[0.3.0]` "Fixed" entry), not an oversight — `MANIFEST.in`'s
  `prune src/*.egg-info` is confirmed present and correct.
- **Archive permissions are actively normalized and verified correct**:
  every wheel entry is `0644`; every sdist file/dir is `0644`/`0755` with
  uid/gid/uname/gname zeroed, via `scripts/normalize_archive_permissions.py`
  (run as the second step of `make build`) — a real, necessary fix for a
  genuine WSL/drvfs quirk where the source filesystem reports every file as
  mode `0777`. Confirmed the script rewrites archive metadata only, never
  content, so wheel `RECORD` hashes remain valid.
- **The sdist is genuinely self-contained**: extracted into an isolated
  temp directory with zero access to the git working tree (no `tests/`,
  `scripts/`, `.git/`), and `python -m build` succeeded from inside it
  alone, producing an identical wheel/sdist pair.
- **Offline wheel installation is real, not just claimed**: a fresh venv
  installed via `pip install --no-index --find-links dist/ maops-pydevops`
  runs `maops-py --version`/`doctor` (text and JSON) correctly with zero
  network access, and `pip show` confirms `Requires:` is blank.
- **Exact-wheel selection is deterministic and fails loud — verified
  adversarially, not just by reading the script.** `scripts/
  verify_wheel.py` (invoked as the literal first statement of the
  `smoke-install` recipe, under `bash -eu -o pipefail`) was tested by
  injecting a second, stale wheel into `dist/`; it correctly aborted the
  entire `smoke-install` target with a clear "expected exactly 1 wheel,
  found 2" error rather than silently installing either one. Cleaned up the
  injected file afterward; confirmed via `git status`/directory listing
  that `dist/` was restored to the single correct artifact set.
- **Smoke fixtures are properly isolated and self-cleaning**: `scripts/
  smoke/make-log-fixture.py` only ever writes to its caller-supplied path,
  always inside a `mktemp -d` directory removed by an `EXIT` trap (fires on
  failure too, not just success) — confirmed via `git status` before/after
  every command in this review showing zero repository pollution, and no
  leftover `/tmp/tmp.*` directories.
- **Default redaction genuinely works end-to-end in the installed
  artifact**, not just the dev tree — manually confirmed the fixture's
  embedded `password=smoke-test-secret-...` value is absent from both text
  and JSON `logs parse` output of the offline-installed wheel (M1's gap is
  that `smoke-install` doesn't itself assert this — redaction itself is not
  broken).
- **Zero runtime dependencies, confirmed at both metadata and installed-
  artifact level**: `pyproject.toml`'s `dependencies = []`; the built
  wheel's `METADATA` has no unconditional `Requires-Dist` line (every
  dependency listed is `extra == "dev"`); `pip show` on the offline-
  installed wheel shows `Requires:` blank. Backed by a dedicated regression
  test, `tests/unit/test_no_runtime_dependencies.py`.
- **The GitHub Actions Python matrix is intact and unmodified by this
  diff**: `git diff` shows no changes to `.github/workflows/
  python-validation.yml` on this branch; its matrix
  (`["3.11", "3.12", "3.13", "3.14"]`, `fail-fast: false`) matches
  `pyproject.toml`'s `requires-python = ">=3.11"` and its four Python
  version classifiers exactly.
- **Both `uses:` lines in the sole workflow file are SHA-pinned**: `actions/
  checkout` and `actions/setup-python` are each pinned to a full 40-
  character commit SHA with a `# vX.Y.Z` comment; no exceptions found.
- **No publishing surface exists**: the only `permissions:` block in the
  workflow tree is `contents: read`, declared at the workflow level; no
  `id-token: write`, no artifact-upload step, no PyPI/publish step anywhere
  — consistent with `docs/roadmap.md` explicitly deferring PyPI publishing
  to an unscheduled future release.
- **`release-check`'s ordering is real `make`-enforced dependency wiring,
  not aspirational documentation**, and it is soundly cost-ordered:
  `format-check` → `lint` → `type-check` → `coverage` within `quality`
  (cheapest static checks before the ~3-minute test suite), and
  `quality` → `build` → `smoke-install` within `release-check` (cheapest
  gate first, before the real `python -m build` and the venv-creating
  install). Verified this is genuinely enforced, not just documented, by
  watching both `make quality` and `make release-check` actually abort at
  the cheapest step (`format-check`) before `lint`/`type-check`/
  `coverage`/`build`/`smoke-install` got a chance to run — the correct
  fail-fast behavior, currently tripped by C1's unrelated Markdown file
  rather than any defect in the ordering logic itself.
- **No unbounded or user-supplied deletion targets**: the `clean` target
  and every Makefile recipe operate on fixed, known paths (`dist build
  src/*.egg-info *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov
  .coverage`); `grep -n "sudo"` across the Makefile, workflow file, and
  `scripts/` returns nothing.

---

## Verdict

**Not release-ready as of this review, but close, and blocked by a
tooling-scope issue rather than an artifact defect.** Every check that
concerns the actual shipped package — wheel contents, sdist contents,
archive permissions, sdist self-containment, offline installability,
exact-wheel selection, dependency surface, CI matrix/pinning/permissions,
and release-check ordering — is independently verified clean, and several
(exact-wheel selection, archive-permission normalization, offline install)
are unusually well hardened for a project at this stage. The blocker is
that the exact required command, `make release-check` (and its
prerequisite `make quality`), fails today with a reproducible exit 2,
because an unscoped `ruff format --check .` picks up an unrelated Markdown
file. That is a same-day fix (reformat the one file, and/or scope
`format`/`format-check`/`lint` to `src tests`), alongside two Medium
completeness gaps (M1: assert redaction in `smoke-install`, not just JSON
validity; M2: document the `smoke-install` Makefile change in the
changelog) and one Low doc-staleness item (L1), before this branch should
be called release-ready for v0.4.0.
