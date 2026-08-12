# Release Process

This document describes the real, complete process this project follows
to cut a release, from opening a branch to publishing a GitHub Release.
It reflects what has actually happened across v0.1.0 through v0.7.0, not
an aspirational process that was never exercised.

## 1. Branch

Work starts on a branch prefixed by change type —
`feature/day-N-<short-name>` for the day's main feature branch (e.g.
`feature/day-7-final-hardening`), or `fix/`, `docs/`, `refactor/`,
`chore/` for smaller, out-of-band changes. See
[CONTRIBUTING.md](../CONTRIBUTING.md#branch-naming).

## 2. Implementation

Code changes land on the branch following the typing, testing, and
security policy in [`.claude/CLAUDE.md`](../.claude/CLAUDE.md): mypy
strict mode, frozen dataclasses, explicit serialization, dependency
injection over real-environment coupling in tests, and the package's
narrow, enumerated exceptions to "no subprocess"/"no network"/"no writes
outside build or test temp directories."

## 3. Quality

```bash
make quality   # format-check + lint + type-check + coverage
```

This runs, in order: `ruff format --check`, `ruff check`, `mypy --strict`
(scoped to `src/` — see `[tool.mypy]` in `pyproject.toml`), and `pytest`
with `--cov-fail-under=90`. All four must pass with zero findings before
moving on; this is the same chain `.github/workflows/python-validation.yml`
runs in CI, just executed locally first so failures are caught before a
push.

## 4. Build

```bash
make build
```

Removes any previous `build/`, `dist/`, and `src/maops_pydevops.egg-info/`
directories, runs `python -m build` (PEP 517, via `setuptools.build_meta`)
to produce both the wheel and sdist, then runs
`scripts/normalize_archive_permissions.py dist` to rewrite every archive
member's mode bits to `0644` (files) / `0755` (directories) — this
neutralizes a real, encountered problem where building from a
Windows-drvfs-mounted path leaks `0777` permissions into the archive;
only zip/tar metadata is rewritten, never file content, so wheel `RECORD`
hashes remain valid.

**`make build` is not offline.** `python -m build` creates an isolated
PEP 517 build environment and may install the project's declared
`build-system.requires` (currently `setuptools>=77.0.1`) from PyPI into
that isolated environment if it is not already cached. Only the
*smoke-install* step below is deliberately offline — do not conflate the
two.

## 5. Smoke-install

```bash
make smoke-install
```

This is the step that proves the **exact built wheel** — not editable
source, not a fresh `pip install` from PyPI — actually works end to end:

1. `scripts/verify_wheel.py` confirms `dist/` contains exactly one wheel
   matching the expected `maops_pydevops-<version>-py3-none-any.whl`
   name (never a glob-and-take-the-first-match).
2. A fresh virtualenv is created in a `mktemp -d` temporary directory,
   with a `trap ... EXIT` cleanup so the temp directory is always removed.
3. The wheel is installed with `PIP_NO_INDEX=1 pip install --no-deps` —
   **this step is deliberately offline**: `PIP_NO_INDEX=1` forbids pip
   from consulting any package index, and `--no-deps` skips dependency
   resolution entirely (safe because the runtime dependency list is
   empty). This is the one part of the release process with a genuine,
   enforced offline guarantee.
4. The installed console script (`maops-py`) and the `python -m
   maops_pydevops` module invocation are both exercised, proving
   entry-point parity.
5. Every command group is smoke-tested against the installed wheel:
   `doctor`, `config path`, `tools inspect` (via the deterministic
   `scripts/smoke/fake-git` stub, never real `git`), `inventory system`,
   `inventory filesystem` (against a generated fixture tree), `logs
   parse`/`logs analyze` (against a generated fixture log, including an
   explicit assertion that a synthetic secret never leaks into JSON
   output), `health http`/`health tcp` (via
   `scripts/smoke/health_smoke_check.py`'s real loopback server/listener
   — no public network), `report aggregate` (JSON and a `--output
   --format markdown` write, asserted non-empty), and `workflow
   validate`/`workflow run` (via `scripts/smoke/workflow_smoke_check.py`,
   also real-loopback-only).
6. `HOME` is pointed at a fresh temp directory (`smoke_home`) for every
   invocation that touches configuration resolution — never the real
   invoking user's home directory.

## 6. Specialist reviews

Before a release is called ready, the branch goes through targeted
review passes — architecture/security, test-suite quality, and
release/packaging — each producing a dated document under
[docs/engineering-reviews/](engineering-reviews/). Findings are
classified Critical/High/Medium/Low; the project's release policy is
that **any verified Critical or High finding blocks the release**,
while Medium/Low findings may ship and be scheduled as deferred
follow-up work (see, for example,
[docs/engineering-reviews/day-06-release-readiness-followup.md](engineering-reviews/day-06-release-readiness-followup.md)
for how the v0.6.0 blocker was triaged and fixed, and how the v0.7.0
branch subsequently closed the Medium/Low items deferred from that pass).

## 7. Blocker remediation

Any verified Critical/High finding is fixed on the same branch, with a
regression test proven to fail on the pre-fix source and pass on the
post-fix source, before the branch is considered release-ready. The fix
and its test land in the same review cycle that found the defect — a
finding is never carried forward as a "known issue" if it meets the
Critical/High bar.

## 8. Release-check

```bash
make release-check   # quality + build + smoke-install
```

The single command that chains steps 3-5 end to end, run once more
against the fully fixed tree as a final local gate before opening a pull
request. This is also, verbatim, the only substantive step CI runs (see
step 10).

## 9. Pull request

A pull request is opened from the feature branch against `main`,
describing the day's changes and summarizing quality-gate results. This
is also where `docs/engineering-reviews/` artifacts and the CHANGELOG
entry for the new version are included in the diff.

## 10. Python 3.11-3.14 CI

Opening (or updating) the pull request triggers
`.github/workflows/python-validation.yml`: a single workflow, `contents:
read` permissions only, running `make release-check` across a
`fail-fast: false` matrix of Python 3.11, 3.12, 3.13, and 3.14 on
`ubuntu-latest`. Both actions used (`actions/checkout`,
`actions/setup-python`) are pinned to full 40-character commit SHAs with
a trailing `# vX.Y.Z` comment — never a tag or branch name — enforced by
`tests/unit/test_actions_pinning.py`. `HOME` is pointed at a
runner-temporary directory before `make release-check` runs, for the same
real-HOME-isolation reason the local smoke-install does it.

## 11. Merge

Once CI is green across all four Python versions, the pull request is
merged into `main`. Per this project's own policy (see
[CONTRIBUTING.md](../CONTRIBUTING.md#commits-and-releases) and
[`.claude/CLAUDE.md`](../.claude/CLAUDE.md)), commits, merges, tags, and
releases are performed by the repository owner — an AI assistant working
in this repository does not merge, tag, or publish without explicit,
in-conversation instruction to do so.

## 12. Release-check on merged main

After merging, `make release-check` is run again against the merged
`main` branch (not just the pre-merge feature branch) as a final
sanity check that the merge itself introduced no regression — a fast,
cheap confirmation given step 10 already validated the exact merged diff
across the full Python matrix.

## 13. Annotated tag

A signed or annotated `git tag -a vX.Y.Z -m "..."` is created on the
merge commit, matching `pyproject.toml`'s `[project] version` exactly —
`version.py::get_version()` reads this back at call time via
`importlib.metadata.version()`, so the tag, the package metadata, and the
CHANGELOG's version heading are always kept in agreement (regression-
tested by `tests/unit/test_version.py`).

## 14. GitHub Release

A GitHub Release is published from the tag, with release notes drawn
from the corresponding `CHANGELOG.md` section. The wheel and sdist built
in step 4 may be attached as release artifacts. **There is no PyPI
publishing step and no CI workflow that publishes anywhere** — this
project deliberately ships only source and GitHub Releases; see
[docs/roadmap.md](roadmap.md) for why PyPI publication is listed only as
a possible, not planned, future enhancement.

---

## What `make build`/`make smoke-install`/`make release-check` do and do not guarantee

| Command | What it does | Offline? |
|---|---|---|
| `make build` | `python -m build` (isolated PEP 517 environment) + archive permission normalization | **No** — the isolated build backend may fetch `build-system.requires` from PyPI if not already cached |
| `make smoke-install` | Installs the *exact* built wheel into a fresh, temporary venv with `PIP_NO_INDEX=1 --no-deps`, then exercises every command group against it | **Yes** — this is the one deliberately offline step |
| `make release-check` | `quality` (format/lint/type-check/coverage) → `build` → `smoke-install`, in order | Only the `smoke-install` portion is offline; `build` is not |

Do not claim the entire build/release process is offline — only the
exact-wheel install-and-smoke-test step makes that guarantee.
