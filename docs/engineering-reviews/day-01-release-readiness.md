# Day 1 v0.1.0 Release-Readiness Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`, console
command `maops-py`)
**Reviewer:** Independent engineering review (no memory of prior sessions on
this repository; every claim below was re-derived from the code, tests, and
command output produced during this review)
**Date:** 2026-08-03
**Branch reviewed:** `feature/day-1-python-foundation`
**Method:** Applied the review criteria in `.claude/agents/python-reviewer.md`,
`.claude/agents/python-test-engineer.md`, `.claude/agents/release-engineer.md`,
and `.claude/skills/{python-review,python-best-practices,python-testing,
devops-review,github-actions,documentation}/SKILL.md` directly (these are not
invokable as live subagents in this environment), against `.claude/CLAUDE.md`
as the authoritative project policy.

---

## Commands run

```
source .venv/bin/activate
make quality           # format-check, lint, type-check, coverage
make build              # sdist + wheel, then normalize_archive_permissions.py
make smoke-install        # isolated venv install + CLI exercise (run standalone)
make release-check         # quality -> build -> smoke-install (full chain)

maops-py doctor --format json | python -m json.tool
python -m maops_pydevops doctor --format json | python -m json.tool

git status --short
git ls-files --others --exclude-standard
```

Plus hand-rolled adversarial checks (documented inline below): unknown
commands, invalid `--format`, simulated optional-tool presence/absence,
simulated unsupported Python/OS, import from an unrelated CWD, a from-scratch
wheel install into a **second**, independently created temp venv (outside
`make smoke-install`), an install exercised from a path containing spaces, a
stale-wheel regression against `scripts/verify_wheel.py`, an unpinned-action
regression against the pinning regex from `tests/unit/test_actions_pinning.py`
(run against an in-memory string, never against the real workflow file), and
direct `zipfile`/`tarfile` inspection of the built wheel and sdist.

All four `make` targets and both JSON entry points **passed** on this host.

---

## Python versions: targeted vs. actually verified

| | Claimed/targeted | Actually verified in this review |
|---|---|---|
| `requires-python` | `>=3.11` | N/A (metadata only) |
| Classifiers | 3.11, 3.12, 3.13, 3.14 | N/A (metadata only) |
| `docs/roadmap.md` / `CHANGELOG.md` wording | "CI-validated on 3.11, 3.12, 3.13, and 3.14" | **Not verified** — see below |
| Actual interpreter used for every command in this review | — | **3.12.3 only** (`.venv`, Linux/WSL2, x86_64) |

**This is a material documentation-accuracy gap, not a nitpick.** The CI
workflow (`.github/workflows/python-validation.yml`) declares a
`python-version: ["3.11", "3.12", "3.13", "3.14"]` matrix, but:

1. The workflow file itself is **untracked in git** (see Critical finding
   below) — it has never been pushed to a remote, so GitHub Actions could not
   possibly have executed it yet.
2. There is no CI run history to point to.
3. Every command in this review, and (by construction) every prior local
   `make quality`/`make release-check` run, executed under Python 3.12.3
   only, because that's the only interpreter installed in `.venv`.

Local passing results on 3.12 are **not evidence** that the codebase is
correct on 3.11, 3.13, or 3.14. The code doesn't use anything version-specific
that stands out on inspection (no walrus/match tricks tied to a single minor
version, `StrEnum` requires 3.11+ which is already the floor), but nothing
has actually exercised 3.13/3.14 syntax or stdlib changes, or 3.11's absence
of features introduced later. **Treat multi-version support as an open risk
until the workflow is committed, pushed, and has at least one green run
across all four matrix legs.**

---

## Total tests / coverage

- **72 tests**, all passing (`tests/unit/`: 20 files; `tests/integration/`: 6
  files).
- Coverage: **99.58%** line+branch (gate: `--cov-fail-under=90`). Only
  partially-covered line is `src/maops_pydevops/__main__.py` line 9's
  `sys.exit(main())` branch marker (`9->exit`, 86% on that one file) — this is
  the `if __name__ == "__main__":` guard, which is inherently only exercised
  when run as `__main__`, and the integration tests do exercise it via
  `python -m maops_pydevops`. Not a real gap.
- Coverage quality (per `python-test-engineer` criteria): every exit-code
  branch (0/1/2), every required-check failure path (via monkeypatch/
  injectable parameters), optional-tool presence/absence, and both doctor
  output formats are explicitly asserted — not just incidentally exercised.
  This is genuinely meaningful coverage, not inflated by trivial lines.

---

## Package artifact details

Built via `make build` (`python -m build` + `scripts/normalize_archive_permissions.py`):

- `dist/maops_pydevops-0.1.0-py3-none-any.whl` (~11.9 KB)
- `dist/maops_pydevops-0.1.0.tar.gz` (~12.1 KB)

**Wheel contents** (verified with Python's `zipfile`, not `ls -l` — WSL/drvfs
always reports 0777 externally regardless of archive-internal metadata):
all 10 `.py` files + 6 `dist-info` entries, every regular-file entry at mode
**0644**, every directory-implied entry at 0755, **zero world-writable
entries** (checked against `mode & 0o002`, the correct other-write bit).
Clean — no `.venv`, `.git`, test files, or `__pycache__` leaked in.

**Sdist contents** (verified with `tarfile`): same 0644/0755 pattern, `uid`/
`gid`/`uname`/`gname` all zeroed for reproducibility. **However**, the sdist
contains a stray `src/maops_pydevops.egg-info/` directory (`PKG-INFO`,
`SOURCES.txt`, `dependency_links.txt`, `entry_points.txt`, `requires.txt`,
`top_level.txt`) that should not ship in a release sdist — see Medium
finding below. This is reproducible: confirmed on two independent `python -m
build` runs, not a stale artifact.

Neither archive contains a world-writable member. This was independently
re-verified from scratch (not by trusting the project's own
`test_release_permissions.py`, though that test also passed).

---

## CLI inventory

```
maops-py [-h] [--version] {version,doctor} ...
maops-py version
maops-py doctor [--format {text,json}]
python -m maops_pydevops   # identical interface, same main()
```

Exit codes verified for every path:

| Invocation | Exit |
|---|---|
| `maops-py --version` / `maops-py version` | 0 |
| `maops-py doctor` (overall pass) | 0 |
| `maops-py doctor` (any required check fails) | 1 |
| `maops-py <unknown>` | 2 (argparse `invalid choice`) |
| `maops-py doctor --format xml` | 2 (argparse `invalid choice`) |
| `maops-py` (no args) | 2 (help printed to stderr) |
| `maops-py -h` / `--help` | 0 |

Quirk found (see Low finding): `maops-py --version doctor` silently runs
`doctor` and ignores `--version`, because `main()` only checks the top-level
`--version` flag when `args.command is None`. Not a correctness bug against
the stated exit-code convention, but an inconsistency worth a decision (error
vs. honor `--version` first).

---

## Doctor output (both entry points, cross-checked)

`maops-py doctor --format json | python -m json.tool` and
`python -m maops_pydevops doctor --format json | python -m json.tool`
produced **byte-identical structured output** (version, python, platform,
6 required checks, 5 optional checks, overall), both valid JSON, no ANSI, no
stray log lines. Check order is fixed and verified deterministic across two
consecutive in-process calls to `build_report()`:

```
python_version, package_import, os_family, temp_directory,
filesystem_encoding, python_executable,   # required, in this order
git, docker, kubectl, terraform, ansible  # optional, in this order
```

Adversarial simulations (via the injectable `build_report(python_version=,
os_system=)` parameters and `shutil.which` monkeypatching — never by mutating
`sys.version_info`):

- All optional tools **absent** (simulated): all 5 → `warn`, `overall: pass`
  (optional failures never affect overall — correct).
- All optional tools **present** (simulated): all 5 → `pass`.
- Unsupported Python `(3, 9, 0)` (simulated): `python_version` → `fail`,
  `overall: fail`.
- Unsupported OS `"PlayStation"` (simulated): `os_family` → `fail`, `overall:
  fail`.
- Combined unsupported Python + OS: both required checks fail independently,
  `overall: fail` — no short-circuiting that would hide one failure behind
  another.

---

## Action-pin evidence

`.github/workflows/python-validation.yml` — 2 `uses:` lines, both matching
`^[^@]+@[0-9a-f]{40}\s+#\s*v\d+\.\d+\.\d+\s*$`:

```
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1     # v7.0.1  (40 hex chars, confirmed by wc -c)
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0  (40 hex chars, confirmed by wc -c)
```

`permissions: contents: read` declared once at workflow level, no job-level
override, no elevated scopes. Triggers: `push` to `main`, `pull_request` to
`main`, `workflow_dispatch` — nothing broader. No artifact-upload or publish
step exists.

**Regression check performed:** ran the exact regex pair from
`tests/unit/test_actions_pinning.py` against an in-memory string containing
`actions/checkout@v4` (never touching the real workflow file) — confirmed the
pattern **rejects** the tag reference and **accepts** the real SHA-pinned
line. The pinning test would genuinely catch a regression, not just pass by
construction.

**Caveat:** none of this has ever run on GitHub's infrastructure — the
workflow file is untracked (see Critical finding). The pinning, permissions,
and trigger design are correct as authored, but "CI quality" as an
operational fact (does it actually run, does it actually catch a real PR)
is unverified.

---

## Findings

### Critical

1. **The entire Day 1 deliverable is uncommitted to git.** `git status
   --short` shows only `README.md` as modified; every other file in the
   project — `src/`, `tests/`, `pyproject.toml`, `Makefile`, `.github/`,
   `docs/*.md` (except the pre-existing README stub), `scripts/`, `.claude/`,
   `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `.gitignore`,
   `.gitattributes`, `.editorconfig`, `.python-version` — is untracked
   (`git ls-files --others --exclude-standard` lists ~50 files). The only
   commit on this branch is `54564fe chore: initialize Project 2 repository`,
   which added a 3-line README. **Why it matters:** none of this work exists
   in version-control history. A `git clean -fdx`, a bad `checkout`, a lost
   working directory, or simply switching branches without stashing would
   destroy the entire v0.1.0 implementation with no recovery path. It also
   means the GitHub Actions workflow has never been pushed and therefore
   **cannot have run**, which directly undermines the "CI-validated on
   3.11–3.14" claims in `CHANGELOG.md` and `docs/roadmap.md` (see High
   finding #2). This must be committed (and the CI-validation claims
   corrected or the workflow actually run) before this can be called
   release-ready. `docs/architecture.md`, `docs/best-practices.md`, etc. —
   `git status --short`, `git ls-files --others --exclude-standard`.

### High

2. **Documentation overclaims CI validation that has not occurred.**
   `CHANGELOG.md:17` ("CI validated against 3.11, 3.12, 3.13, and 3.14") and
   `docs/roadmap.md:5-6` ("CI-validated on 3.11, 3.12, 3.13, and 3.14") state
   this as an accomplished fact. In reality, the workflow has never been
   committed/pushed (Critical #1) and this review only exercised Python
   3.12.3 locally. **Why it matters:** a reader (including a future
   maintainer or hiring reviewer) would reasonably conclude multi-version
   compatibility is proven; it isn't. Fix: soften to "targets" until the
   workflow has an actual green run, or add the run link once it exists.
   `CHANGELOG.md:16-17`, `docs/roadmap.md:5-6`.

### Medium

3. **`src/maops_pydevops.egg-info/` leaks into the sdist.** Reproduced on two
   independent `python -m build` runs: `dist/maops_pydevops-0.1.0.tar.gz`
   contains `maops_pydevops-0.1.0/src/maops_pydevops.egg-info/{PKG-INFO,
   SOURCES.txt,dependency_links.txt,entry_points.txt,requires.txt,
   top_level.txt}`. **Why it matters:** this is build-generated metadata, not
   source — it shouldn't be a tracked part of the release sdist tarball
   (it's redundant with the top-level `PKG-INFO` setuptools already writes,
   and it's the kind of "stray file leaking into the distribution" the
   release-engineer review criteria explicitly call out). Low risk in
   practice (doesn't affect wheel build correctness, doesn't affect
   installability), but it's packaging hygiene debt. Fix: exclude via a
   `MANIFEST.in` (`prune src/*.egg-info`) or `sdist.exclude` config; verify
   with a `python -m build --sdist` + `tarfile` re-inspection.
   `pyproject.toml` (no `[tool.setuptools]` sdist-exclusion section exists).

4. **`.python-version` (3.11) and the active dev venv (3.12.3) disagree,
   and neither 3.11 nor any version other than 3.12 has actually been
   exercised.** This compounds finding #2 above: the project's own pinned
   local-dev version (3.11) isn't what `make quality`/`make release-check`
   actually ran under in this review or (per `.mypy_cache/3.11` vs. the
   installed interpreter) apparently in prior local runs either. Not
   necessarily wrong (3.12 is in the supported range), but it means "runs
   clean locally" has only ever meant "runs clean on 3.12." `.python-version`,
   `.venv/bin/python --version`.

### Low

5. **`maops-py --version doctor` silently ignores `--version`.**
   `cli.py:main()` only checks `args.version` when `args.command is None`
   (`cli.py:92-96`); when a subcommand is also present, `_COMMANDS[args.command]`
   runs unconditionally and the top-level `--version` flag is silently
   dropped. Confirmed by direct execution: `maops-py --version doctor` prints
   the full doctor report, not the version. **Why it matters:** minor
   argparse-consistency surprise — a user combining flags gets silently
   different behavior than either flag alone would suggest, with no error and
   no warning. Fix: either make it a usage error (mutually exclusive) or
   explicitly document/decide the precedence. `src/maops_pydevops/cli.py:87-98`.

6. **`test_console_script_version`/`test_console_script_doctor_text` skip
   silently if `maops-py` isn't resolvable via `shutil.which` at collection
   time.** (`tests/integration/test_console_script_entrypoint.py:9-11`) In a
   misconfigured CI/dev environment where the editable install didn't
   register the console script on `PATH`, these two tests would silently
   skip rather than fail loudly, masking exactly the kind of
   "console-script entry point broken" regression they exist to catch. Low
   severity because `make install`/`make release-check` normally guarantees
   the script is present, but it's a soft dependency on host state that the
   project's own testing policy (`.claude/skills/python-testing/SKILL.md`) is
   otherwise strict about avoiding.

7. **`tool.mypy.files = ["src"]` excludes `tests/` from strict type
   checking.** Consistent with common practice and not against stated policy
   (which describes typing rules for "public functions" generally understood
   as library code), but it does mean the well-typed test suite's own typos
   or drift wouldn't be mypy-caught. Cosmetic/low.

8. **README "Repository structure" code block has inconsistent, drifting
   indentation** on the nested `commands/`/`core/` comment alignment
   (`README.md:163-192` — each successive line's trailing comment is offset
   by one more space than the last). Purely cosmetic.

### Future enhancements

- Add a Bandit-style `S` (flake8-bandit) rule set to the Ruff `select` list
  in `pyproject.toml` for automated security-pattern linting, since the
  project already has strict manual safety restrictions in
  `.claude/CLAUDE.md` — codifying them in the linter would make regressions
  fail fast instead of relying on `test_no_subprocess_shell.py`/
  `test_no_network.py` alone.
- Once the workflow actually runs, link the passing run (or badge) from
  README/CHANGELOG so "CI validated" claims are independently checkable.
- Consider a `MANIFEST.in` (see Medium #3) as part of general packaging
  hygiene, not just to fix the egg-info leak.

---

## Scores (out of 5)

| Area | Score | Notes |
|---|---|---|
| Architecture | 5 | Clean `src/` layout, strict parser/execution separation, single shared `main()`, no duplicated entry-point logic. Matches its own documented architecture exactly. |
| Python correctness | 5 | No bugs found in `cli.py`, `doctor.py`, `models.py`, `output.py`, `platform.py` beyond the minor `--version`-with-subcommand quirk (Low #5). |
| Type safety | 5 | mypy strict, zero `Any`, zero `# type: ignore`, frozen dataclasses, explicit `to_dict()` per field. |
| CLI quality | 4 | Exit codes, help, subcommands all correct and argparse-native; docked for the `--version`+subcommand precedence quirk. |
| Doctor usefulness | 4 | Deterministic, well-structured, both formats validated, correct required/optional split. Docked slightly because several "required" checks (temp-dir availability, filesystem encoding) are near-impossible to fail on any real host, so their diagnostic value is mostly theoretical/defensive rather than practical. |
| Security | 5 | No `shell=True`/`os.system`/`eval`/`exec`/`pickle`/`subprocess` anywhere in `src/`; optional-tool checks are `shutil.which()`-only; verified with grep and with tests that monkeypatch `subprocess`/`socket` to raise if touched. |
| Packaging | 3.5 | Wheel is clean; sdist leaks `egg-info` (Medium #3); permissions correctly normalized and independently re-verified; stale-wheel and no-network guarantees hold up under adversarial testing. |
| Automated testing | 5 | 72 tests, 99.58% coverage, genuinely meaningful (exit codes, injected failure paths, JSON schema/type checks, deterministic ordering, monkeypatched host-independence) — not inflated. |
| CI quality | 2.5 | The workflow-as-written is well-designed (SHA-pinned, minimal permissions, minimal triggers, correct matrix) — but it has **never run** because it (and everything else) is uncommitted. Design quality is high; operational evidence is zero. |
| Documentation | 3.5 | README/CLI examples/CHANGELOG/architecture docs are otherwise accurate and match the real interface exactly, but the "CI-validated on 3.11–3.14" claim is not currently true (High #2). |

**Overall: 3.9 / 5** — strong engineering discipline and a genuinely
well-built v0.1.0, held back by one process failure (nothing is committed)
that is trivial to fix but currently blocks calling this "released" in any
meaningful sense, plus one documentation overclaim that follows directly
from it.

---

## Strongest three areas

1. **Test suite design.** Deterministic dependency injection for
   Python-version/OS/tool-presence simulation, explicit exit-code assertions
   on every path, JSON schema/type validation, and a stale-wheel regression
   test (`test_verify_wheel_script.py::test_fails_when_a_stale_extra_wheel_is_present`)
   that proves the release script's own safety property rather than just
   asserting it works in the happy path.
2. **Security/safety discipline.** Zero `shell=True`/`os.system`/`eval`/
   `exec`/`pickle`/`subprocess` in runtime code, `shutil.which()`-only
   optional-tool detection, and tests that actively monkeypatch `subprocess`
   and `socket` to fail loudly if touched — this is enforced, not just
   asserted in docs.
3. **Typed model layer.** Frozen dataclasses, `StrEnum`s, explicit
   `to_dict()`/`to_json()` per field (no `dataclasses.asdict()`
   blind-spreading), mypy strict with zero escape hatches. The JSON schema is
   traceable directly from the code, exactly as `docs/architecture.md`
   claims.

## Five highest-priority improvements

1. **Commit and push everything** (Critical #1) — this is the single
   blocking item; nothing else about "release readiness" is meaningful while
   the release artifacts' own source doesn't exist in git history.
2. **Get the CI workflow to actually run** (push it, open a PR or trigger
   `workflow_dispatch`) and correct or substantiate the "CI-validated"
   language in `CHANGELOG.md`/`docs/roadmap.md` (High #2) once there's a real
   run to point to.
3. **Fix the sdist egg-info leak** (Medium #3) via `MANIFEST.in` or
   equivalent exclude config, then re-verify with `tarfile`.
4. **Decide and fix the `--version`-with-subcommand precedence** (Low #5) —
   either error on the combination or document/honor the intended
   precedence.
5. **Harden the console-script tests against silent skip** (Low #6) — assert
   the script is installed rather than skipping if it's missing, so a broken
   entry point fails loudly in CI.

## Unresolved findings

All eight findings above (Critical #1 through Low #8) are unresolved as of
this review — no code was modified as part of this review per its
constraints. Future enhancements are open suggestions, not defects.

## Release blockers

- **Critical #1** (uncommitted work) blocks any release claim outright.
- **High #2** (CI-validation overclaim) blocks shipping the current
  CHANGELOG/roadmap wording as-is; must be corrected or substantiated before
  external-facing release notes go out.

Medium/Low findings are not release-blocking but should be triaged promptly.

## Final v0.1.0 readiness recommendation

**Not yet release-ready — blocked on process, not on code.** The
implementation itself (CLI, doctor diagnostics, typed models, packaging
mechanics, test suite, workflow design) is high quality and passed every
functional, security, and adversarial check performed in this review,
including checks the project's own test suite doesn't run automatically
(manual wheel install into a second isolated venv, install from a
space-containing path, regex-level pinning regression test, direct
archive-permission inspection). However, calling this "v0.1.0 release-ready"
while the entire deliverable sits uncommitted on a local branch — with a CI
workflow that has structurally never executed — is not defensible. Fix
Critical #1 (commit, push) and High #2 (correct or substantiate the
CI-validation claim, ideally by getting one real green matrix run), and this
becomes a straightforward "ready to tag" v0.1.0.
