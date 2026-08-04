# Day 2 v0.2.0 Release-Readiness Review — Follow-Up

**Responds to:** `docs/engineering-reviews/day-02-release-readiness.md`
**Date:** 2026-08-04

The original report is left unmodified as an accurate historical record of
what an independent review found at that point in time. This follow-up
documents the response to its Critical and High findings, per instruction
to fix all verified Critical and High findings and produce a follow-up
report when such fixes occur.

The original report found **zero Critical findings** and **one High
finding**. That finding is fixed below.

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
scenario the original finding described, **v0.2.0 is release-ready with no
remaining Critical or High findings.** The full quality gate
(`format-check`, `lint`, `type-check`, `coverage`) passes at 259 tests /
99.89% coverage, unchanged from the original review's numbers except for
the one corrected test. No further code, test, or packaging defect stands
between this deliverable and a v0.2.0 tag; the remaining Medium/Low/Future
items are triage candidates for a subsequent day, not release blockers, per
the original report's own release-blockers section.
