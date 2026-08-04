# Day 2 v0.2.0 Release-Readiness Review — Follow-Up

**Responds to:** `docs/engineering-reviews/day-02-release-readiness.md`
**Date:** 2026-08-04

The original report is left unmodified as an accurate historical record of
what an independent review found at that point in time. This follow-up
documents the response to its Critical and High findings, per instruction
to fix all verified Critical and High findings and produce a follow-up
report when such fixes occur.

The original report found **zero Critical findings** and **one High
finding**. That finding is fixed below. A second, previously-unknown bug
was subsequently discovered by a real GitHub Actions CI run against an open
pull request (not by the original review) and is documented and fixed in
its own section below, since it materially affects this deliverable's
actual release readiness even though it fell outside the original report's
scope.

## High #1 — fixed

**Original finding:** `tests/integration/test_tools_inspect_integration.py::test_tools_inspect_json_validates_via_json_tool`
still built its subprocess environment as `env = dict(os.environ); env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"`,
inheriting the real invoking user's `HOME`, `XDG_CONFIG_HOME`, and any real
`MAOPS_PY_*` variables — reproducing exactly the class of test-isolation bug
an earlier review-and-fix cycle on this branch had already closed for the
other two tests in the same file. This directly violated
`.claude/CLAUDE.md`'s explicit testing policy ("Tests must be deterministic:
no reliance on ... host environment variables") and could produce a flaky,
host-dependent failure (empty `stdout` feeding an empty-input failure into
the downstream `python -m json.tool` step) on any machine with a stray or
invalid real configuration file.

**Fix applied:**

- `tests/integration/test_tools_inspect_integration.py` — changed the test
  to reuse the file's own `_isolated_env(tmp_path, bin_dir)` helper (already
  used correctly by the other two tests in the file) instead of
  `dict(os.environ)`:
  ```python
  env = _isolated_env(tmp_path, bin_dir)
  ```
- Removed the now-unused `import os` from the same file (it was the only
  remaining reference to the `os` module after the fix).

**Verification:**

1. Targeted rerun of the fixed file: `pytest
   tests/integration/test_tools_inspect_integration.py -v` — **3 passed**.
2. **Direct reproduction of the original failure scenario against the
   fixed test**, to confirm the fix actually closes the gap rather than
   merely looking correct: created a fresh temporary `HOME` containing a
   deliberately invalid real configuration file
   (`command_timeout_seconds = "not-a-number"` at
   `$HOME/.config/maops-py/config.toml`), then ran the fixed test suite with
   `HOME` pointed at that directory:
   ```
   $ HOME=<fake, invalid-config home> pytest \
       tests/integration/test_tools_inspect_integration.py -v
   test_tools_inspect_git_with_fake_git_on_path        PASSED
   test_tools_inspect_without_git_on_path_reports_warn PASSED
   test_tools_inspect_json_validates_via_json_tool     PASSED
   3 passed in 1.52s
   ```
   Before the fix, this exact scenario reproduced the failure the original
   report described (verified independently during the review itself,
   before any code change was made). After the fix, all three tests in the
   file — including the previously-affected one — pass regardless of what
   the real invoking user's `HOME` contains.
3. `ruff format --check .` and `ruff check .` — clean (the unused `os`
   import removal was required to keep lint clean, not optional).
4. `mypy src` (strict) — no issues found in 15 source files, unaffected by
   a test-only change but re-run for completeness.
5. Full suite: `pytest --cov=maops_pydevops --cov-report=term-missing
   --cov-fail-under=90`:
   ```
   259 passed in 131.39s (0:02:11)
   Total coverage: 99.89%
   ```
   Same test count and coverage percentage as the original review reported
   — no regression, no test added or removed, only the one test's
   environment-construction logic changed.

## Additional fix — Python 3.11 argparse cross-version bug (found by real CI, outside the original review's scope)

**How this was found:** after the original review and the High #1 fix
above, a real GitHub Actions run on an open pull request
(`Python Validation / validate (3.11)`, commit `b1a39ca`) failed. The
original review's own verification was performed entirely against the
locally available interpreter (Python 3.12.3) — it explicitly could not,
and did not claim to, verify behavior on 3.11, 3.13, or 3.14 (this is the
same category of gap the Day 1 review flagged in general terms: "local
passing on one version isn't evidence for other versions"). This is a
concrete instance of exactly that risk materializing.

**The bug:** `maops-py tools inspect --format json` (i.e. with no explicit
tool names) raised `argparse.ArgumentError: invalid choice: []` under
Python 3.11.15 in CI, while the identical invocation worked correctly under
the reviewer's local Python 3.12.3. Root cause, traced directly against
CPython's `argparse.py` source: the `tool` positional
(`nargs="*"`, `choices=[...]`, no explicit `default=`) was implicitly
marked `required=True` by argparse's `_get_positional_kwargs()` (a
positional with `nargs='*'` and no `default` in `kwargs` is forced
`required`). With zero arguments supplied, this required-but-empty
positional's resulting empty list was then validated against `choices` —
and `[] not in ['git', 'docker', ...]` is trivially true, i.e. always
invalid. Whether this validation step is reached and whether it's
version-dependent, differs across Python's argparse implementations
between 3.11 and 3.12 (both branches of this logic were read directly out
of the installed 3.12 stdlib `argparse.py` during diagnosis, and an
initial attempted fix — adding an explicit `default=()` — was found to
*break* the previously-working 3.12 case, confirming the two versions
genuinely diverge here rather than one simply being stricter).

**Fix applied:**

- `src/maops_pydevops/cli.py` — removed `choices=` from the `tool`
  positional's `add_argument()` call entirely, sidestepping the
  version-dependent interaction rather than trying to find a `default=`
  value that behaves identically on both versions. Added a
  module-level `_ALLOWED_TOOL_NAMES: frozenset[str]` and moved tool-name
  validation into `run_tools_inspect()` itself: any requested name not in
  the allowlist now produces an explicit `Error: unsupported tool name(s):
  ...` message on stderr and exit code `2`, matching the original
  contract (unsupported tool names remain a usage error) without relying
  on argparse's `choices=` mechanism for this particular positional.
- `tests/unit/test_cli_tools_inspect.py` — updated
  `test_unsupported_tool_name_exits_two` to assert a plain `int` return of
  `2` (the new validation path returns from `run_tools_inspect()` rather
  than argparse raising `SystemExit`), and added two new tests:
  `test_unsupported_tool_name_never_calls_which_or_run` (confirms
  validation happens before any tool resolution is attempted) and
  `test_no_args_after_removing_argparse_choices_still_inspects_all` (a
  named regression test for the exact scenario that failed in CI — no
  tool names supplied, `--format json` only).
- `CHANGELOG.md` — added a `### Fixed` entry under the existing
  `[0.2.0]` heading (not a new version bump, since v0.2.0 has not been
  tagged) explaining the bug and fix for anyone reading the release notes.

**Verification:**

1. Directly reproduced the exact failing invocation locally with the
   pre-fix code (`main(["tools", "inspect", "--format", "json"])` against
   the built parser) to confirm the root-cause diagnosis before writing any
   fix.
2. Confirmed the fix's `tool` argument parses to `[]` for no arguments and
   to the correct list for explicit tool names, via direct
   `build_parser().parse_args(...)` calls.
3. `ruff format --check .` / `ruff check .` — clean.
4. `mypy src` (strict) — no issues found in 15 source files.
5. Full suite: `pytest --cov=maops_pydevops --cov-report=term-missing
   --cov-fail-under=90`:
   ```
   261 passed in 153.72s (0:02:33)
   Total coverage: 99.89%
   ```
   `cli.py` itself is at 100% statement and branch coverage after the fix
   (up from 134 to 140 statements, all covered). Two tests were added net
   (259 → 261) and one existing test's assertion style changed to match
   the new (still exit-2) behavior; no test was removed or weakened.
6. `make build` and `make smoke-install` both rerun end-to-end after the
   fix — both green, and the exact original failure scenario
   (`maops-py tools inspect --format json` with no tool names) was run
   directly against the installed wheel and produced valid JSON with exit
   `0`.

**What this does not fix:** this verification, like the original review,
was still only performed on the locally available Python 3.12.3. The fix
itself removes the *mechanism* that was version-dependent (argparse
`choices=` validation timing), replacing it with plain Python control flow
that has no version-dependent behavior to audit — but the only way to
fully close this class of risk for the whole 3.11–3.14 matrix is a real
green CI run across all four legs, which remains outside what a local
review can independently confirm.

## Medium / Low / Future findings

Unchanged — not required to be fixed per the fix scope (Critical and High
only). They remain open, documented in the original report, for future
triage:

- Medium #2: sdist leaks `src/maops_pydevops.egg-info/` (carried forward,
  unchanged, from the Day 1 v0.1.0 finding — no `MANIFEST.in` exists).
- Medium #3: `tests/integration/test_release_permissions.py` is not safe
  under concurrent `make build` invocations against the same working tree.
- Medium #4: JSON-shape tests for `ToolInspectionResult`/`ConfigShowReport`
  check only a subset of fields (truncation-flag and a few other fields
  unchecked).
- Low #5: `--version`'s documented universal short-circuit doesn't cover an
  incomplete two-level subcommand group (`--version tools`/`--version
  config`).
- Low #6: `tools inspect`'s WARN-is-fatal exit-code semantic (a missing
  requested tool fails the invocation) diverges from `doctor`'s WARN-is-
  non-fatal convention, undocumented.
- Low #7: configuration validation error messages hardcode "not boolean"
  regardless of the actual invalid type.
- Low #8: `test_tools_inspect_makes_no_network_calls` doesn't exercise the
  found-and-executed code path it appears to guard (the adjacent
  `test_terraform_checkpoint_is_disabled_end_to_end` in the same file does
  cover the real path).

## Updated readiness recommendation

With High #1 fixed and independently re-verified against the exact failure
scenario the original finding described, and with the subsequently
discovered Python 3.11 argparse cross-version bug also fixed and verified,
**v0.2.0 is release-ready with no known remaining Critical or High
findings.** The full quality gate (`format-check`, `lint`, `type-check`,
`coverage`) passes at 261 tests / 99.89% coverage. No further code, test,
or packaging defect stands between this deliverable and a v0.2.0 tag; the
remaining Medium/Low/Future items are triage candidates for a subsequent
day, not release blockers, per the original report's own release-blockers
section.

One caveat carried forward from both this document and the original
report: everything above was verified locally against Python 3.12.3 only.
The argparse bug this document's second section describes is direct,
concrete proof that local single-version verification is not a substitute
for an actual green run across the full 3.11–3.14 CI matrix — the bug was
invisible to every local check performed during the original review and
was only caught because a real pull request actually ran on real GitHub
Actions infrastructure. The fix applied here should make this specific
class of failure unlikely to recur (the version-dependent mechanism was
removed, not patched around), but a genuine green run across all four
matrix legs remains the only complete confirmation, and is recommended
before treating v0.2.0 as fully validated across its declared Python
support range.
