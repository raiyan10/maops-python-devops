# Day 2 v0.2.0 Release-Readiness Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`, console
command `maops-py`)
**Reviewer:** Independent engineering review, using the `python-reviewer`,
`python-test-engineer`, and `release-engineer` subagents (three parallel
passes, one follow-up resumption each where a response was truncated) plus
direct manual verification of every adversarial scenario in this document's
scope, against `.claude/CLAUDE.md`, `docs/configuration.md`,
`docs/subprocess-safety.md`, and the project's existing testing/documentation/
GitHub Actions guidance.
**Date:** 2026-08-04
**Branch reviewed:** `feature/day-2-config-runner`
**Method:** Day 1 (v0.1.0) functionality — `doctor`, `version`, the original
`core/models.py`/`core/platform.py` — is treated as regression-protected and
was not re-audited from scratch; this review focuses on the Day 2 delta
(typed TOML configuration, the safe subprocess runner, and `tools inspect`)
while confirming Day 1 tests still pass unmodified. No implementation files
were modified as part of this review. No sudo, no public network requests,
no writes to the real `HOME`, no git-history mutation.

A concurrency note for transparency: partway through this review, two
specialist subagents and the reviewer's own shell were independently running
`make build`/`make quality`/`make release-check` against the same working
tree at the same time, which caused one transient, spurious `dist/`-related
test failure (see Medium finding below — this is itself a real, if minor,
test-suite robustness finding, not a packaging defect). All numbers quoted in
this report come from fully serialized, uncontended reruns.

---

## Commands run

```
source .venv/bin/activate
make quality           # format-check, lint, type-check, coverage
make build              # sdist + wheel, then normalize_archive_permissions.py
make smoke-install        # isolated venv install + CLI exercise
make release-check         # quality -> build -> smoke-install (full chain)

maops-py config show --format json | python -m json.tool
maops-py tools inspect git --format json | python -m json.tool
python -m maops_pydevops config show --format json | python -m json.tool

pytest tests/unit/test_actions_pinning.py -v
git diff --stat .github/workflows/python-validation.yml
git diff CHANGELOG.md
find .github/workflows -type f
```

Plus hand-rolled adversarial checks (all documented inline below, all run
directly against the installed package or the built wheel, never against a
second copy of the source): malformed TOML, duplicate TOML keys, an unknown
configuration key, a boolean supplied for both numeric fields, an invalid
`MAOPS_PY_OUTPUT_FORMAT` override, a symbolic-link `config init` target with
and without `--force`, a directory `config init` target, a config path
containing spaces and shell metacharacters, an argv element containing shell
metacharacters, a not-found executable, a permission-denied executable, a
nonzero child exit, a timed-out child, malformed UTF-8 child output, an
oversized stdout/stderr pair, an unsupported tool name, all five allowlisted
tools simulated absent, a mixed pass/missing tool set, `import maops_pydevops`
from `/tmp` (outside the repo), a from-scratch wheel install into a
**second**, independently created temp venv (outside `make smoke-install`),
a stale/multiple-wheel regression against `scripts/verify_wheel.py`, and an
unpinned-action regression against the real pinning regex (run in-memory,
never against the real workflow file).

All four `make` targets, all three JSON entry points, and every adversarial
check **passed** on a clean, uncontended rerun.

---

## Total tests / coverage

- **259 tests**, all passing (up from Day 1's 72 — Day 2 added 187 new
  tests across `tests/unit/` and `tests/integration/`, with every Day 1 test
  file preserved and only one Day 1 test literal updated, the hardcoded
  `"0.1.0"` version-string assertion, to `"0.2.0"`).
- Coverage: **99.89%** line+branch (gate: `--cov-fail-under=90`). Every Day 2
  module (`core/config.py`, `core/config_models.py`, `core/runner.py`,
  `commands/config.py`, `commands/tools.py`) reports **100%** statement and
  branch coverage. The only partial line project-wide remains
  `src/maops_pydevops/__main__.py`'s `9->exit` branch — the same pre-existing,
  inherently-only-exercised-as-`__main__` marker noted in the Day 1 review,
  unchanged.
- Coverage quality: independently spot-checked by the `python-test-engineer`
  pass against the atomic-write exception paths (`tempfile.mkstemp`,
  `os.fchmod`, `os.fsync` failure injection) and confirmed the branches are
  genuinely exercised, not accidentally satisfied by unrelated code paths.

---

## Package artifact details

Built via `make build` (`python -m build` + `scripts/normalize_archive_permissions.py`),
re-verified from a clean, uncontended rebuild using Python's `zipfile`/
`tarfile` modules directly (not `ls`/`unzip -l` — this host's filesystem
mount reports 0777 externally regardless of archive-internal metadata):

- `dist/maops_pydevops-0.2.0-py3-none-any.whl`
- `dist/maops_pydevops-0.2.0.tar.gz`

**Wheel contents:** 21 entries — the 15 expected source `.py` files
(`cli.py`, `version.py`, `__init__.py`, `__main__.py`,
`commands/{__init__,config,doctor,tools}.py`,
`core/{__init__,config,config_models,models,output,platform,runner}.py`)
plus 6 standard `dist-info` entries. Every regular-file entry mode is
**0644**; **zero world-writable entries** (`mode & 0o002 == 0`, checked
directly, not trusted from the project's own permission test). No `.venv`,
`.git`, test files, or `__pycache__` leaked in.

**Sdist contents:** 32 entries, same 0644 pattern, zero world-writable
entries. **Carried-forward, unchanged finding:** the sdist still contains
`src/maops_pydevops.egg-info/` (7 entries: the directory plus `PKG-INFO`,
`SOURCES.txt`, `dependency_links.txt`, `entry_points.txt`, `requires.txt`,
`top_level.txt`) — the exact same shape as the Day 1 v0.1.0 finding, because
no `MANIFEST.in` was added in the interim. Confirmed **not worsened, not
newly introduced elsewhere** — no `.py` files are part of the leak, so it
does not affect wheel installability or the 0644/no-stray-`.py` guarantees.

**Offline exact-wheel smoke installation**, verified two ways:
1. `make smoke-install`'s own isolated `mktemp`-venv flow (offline,
   `PIP_NO_INDEX=1`, `--no-deps`, no pip upgrade) — passed, including the two
   new Day 2 smoke checks (`config path` under an isolated fake `$HOME`, and
   `tools inspect git --format json | python -m json.tool` using
   `scripts/smoke/fake-git` on an isolated `PATH`).
2. A **second, independently created** temp venv outside `make
   smoke-install`'s own — `pip install --no-deps --no-index <wheel>` (pip's
   own log recorded `Ignoring indexes: https://pypi.org/simple`, confirming
   zero index contact), then `maops-py --version` / `config path` / `tools
   inspect git --format json | python -m json.tool` all succeeded with valid
   JSON output.

**Stale/multiple-wheel regression:** a second, fake wheel was placed in
`dist/` alongside the real one; `scripts/verify_wheel.py` and
`make smoke-install` both failed loudly (`ERROR: expected exactly 1 wheel...
found 2`) rather than silently selecting one via glob-and-head. The fake
wheel was removed afterward; `dist/` was confirmed restored to exactly the
real wheel + sdist.

**Import from an unrelated working directory:** `cd /tmp && python -c
"import maops_pydevops; print(maops_pydevops.__file__)"` (using the venv's
own interpreter) resolved to the installed package, not a stray same-named
directory, with zero stderr output.

---

## Configuration schema

Read directly from `core/config_models.py` (not re-derived from docs):

| Key | Type | Range | Default |
|---|---|---|---|
| `output_format` | string | `"text"` or `"json"` | `"text"` |
| `command_timeout_seconds` | number | `> 0.0`, `<= 300.0` | `10.0` |
| `max_output_bytes` | integer | `>= 1024`, `<= 1048576` | `65536` |

Unknown keys, malformed TOML, and duplicate TOML keys are all rejected
(the last two natively by the standard-library `tomllib` parser). Boolean
values are explicitly excluded from both numeric fields via
`isinstance(x, bool)` checks that run *before* the general `int`/`float`
check (Python's `bool` is an `int` subclass, so this ordering is the actual
mechanism that makes the rejection work, not incidental).

---

## Precedence evidence

`resolve_config_path()` (path selection): `MAOPS_PY_CONFIG_FILE` (if
non-empty) → `XDG_CONFIG_HOME` (if non-empty) → `HOME` fallback — confirmed
live, including empty-string values correctly falling through to the next
source rather than being treated as "set."

`resolve_effective_config()` (per-field value selection): CLI > environment
> file > default, resolved **independently per field**:

```
$ MAOPS_PY_CONFIG_FILE=<file with output_format="json"> \
  MAOPS_PY_MAX_OUTPUT_BYTES=2048 \
  maops-py tools inspect git --timeout 5 --format json
```
produces `command_timeout_seconds` sourced `"cli"` (5.0), `max_output_bytes`
sourced `"environment"` (2048), and (for `config show` in the same session)
`output_format` sourced `"file"` (`"json"`) — three different sources for
three different fields in the same resolution pass, confirmed via direct
`config show --format json` inspection.

An invalid environment override never silently falls back to a lower-
precedence source — verified live:
```
$ MAOPS_PY_OUTPUT_FORMAT=xml maops-py config show
Error: invalid MAOPS_PY_OUTPUT_FORMAT value: 'xml'
(exit 1, no report body printed)
```

---

## Runner safety evidence

Every item below was independently reproduced against the real
`core/runner.py::run_command()`, not inferred from source alone:

| Check | Result |
|---|---|
| `argv` with embedded shell metacharacters (`; rm -rf / #`) | passed through **literally** as `sys.argv[1]`, never interpreted |
| Executable not found | `RunFailureReason.NOT_FOUND`, `exit_code=None` |
| Executable found but not executable (permission denied) | `RunFailureReason.PERMISSION_DENIED`, `exit_code=None` |
| Nonzero child exit | `exit_code` preserved exactly (tested with `sys.exit(3)` → `3`) |
| Timeout (0.3s timeout, 5s sleep) | `timed_out=True`, `RunFailureReason.TIMEOUT`, `duration_ms≈304` (real, monotonic-clock-measured, not a stub value) |
| Malformed UTF-8 (`b'ok-\xff-end'`) | decoded to `"ok-�-end"` deterministically (`errors="replace"`) |
| Oversized stdout **and** stderr independently (100 KB each, `max_output_bytes=1024`) | both truncated to exactly 1024 bytes, both `*_truncated=True`, independently flagged |
| Missing working directory | `RunFailureReason.INVALID_WORKING_DIRECTORY`, no subprocess ever spawned |
| `stdin` isolation | child's `sys.stdin.read()` returns `''` — `stdin=subprocess.DEVNULL` confirmed |
| `shell=False` | the single `subprocess.run()` call site always passes it explicitly; confirmed both by source inspection and a monkeypatched-kwargs capture test |
| Fixed child env | `LC_ALL=C LANG=C NO_COLOR=1 PAGER=cat GIT_PAGER=cat TERM=dumb CHECKPOINT_DISABLE=1` present in every child, confirmed live; rest of the parent environment is inherited (not stripped to just these 7), confirmed live and correctly documented as "inherit + override," not "replace" |

The `CHECKPOINT_DISABLE=1` override (added during an earlier review-and-fix
cycle on this same branch, prior to this report) was independently
re-verified present and end-to-end effective: a stub `terraform` script that
exits nonzero unless `CHECKPOINT_DISABLE=1` reaches its environment reports
`status: pass` when inspected via `tools inspect terraform`, proving the
runner's fixed-env override genuinely reaches the child process rather than
only being asserted by a mock.

---

## Tool command inventory

Read directly from `commands/tools.py::TOOL_ALLOWLIST` — exactly five
tools, exactly these fixed, hardcoded, read-only argv tuples:

```
git        -> git --version
docker     -> docker --version
kubectl    -> kubectl version --client=true
terraform  -> terraform version
ansible    -> ansible --version
```

Confirmed via grep: no other call site anywhere in `src/` constructs a
`CommandSpec`, and no CLI flag, environment variable, or configuration key
accepts an arbitrary command or argv — Day 2 does not expose a
general-purpose command-execution CLI.

Adversarial simulations (via injectable `which=`/`run=` parameters, never by
depending on real git/docker/kubectl/terraform/ansible installation state):

- Unsupported tool name (`maops-py tools inspect helm`) → **exit 2**,
  rejected by argparse `choices=` before any package code runs.
- All five tools simulated absent → all `warn`, `overall: warn`, **exit 1**.
- Mixed (git present+passing, rest absent) → `overall: warn`, **exit 1**
  (only one tool `pass`, four `warn`, none `fail`).
- Nonzero exit / timed-out / permission-denied child → each maps to a
  distinct `fail` status with the correct `detail` string; report still
  contains **all** requested tools even after an earlier one fails.

---

## Action-pin evidence

`.github/workflows/python-validation.yml` — confirmed **byte-for-byte
untouched** this cycle (`git diff --stat` produces no output), and no second
workflow file exists anywhere under `.github/workflows/`:

```
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1     # v7.0.1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
```

`permissions: contents: read` at workflow level only; triggers `push`/
`pull_request` to `main` plus `workflow_dispatch`; matrix
`python-version: ["3.11", "3.12", "3.13", "3.14"]`, `fail-fast: false`; no
artifact-upload or publish step.

`pytest tests/unit/test_actions_pinning.py -v` → **4 passed**. Regression
check performed independently: the exact pinning regex
(`^[^@]+@[0-9a-f]{40}\s+#\s*v\d+\.\d+\.\d+\s*$`) run in-memory against
`actions/checkout@v4` and `actions/checkout@main` correctly **rejects**
both, and correctly **accepts** both real pinned lines above.

Day 2 added zero new dependencies (`tomllib` is standard library on the
3.11+ floor already declared), so the CI matrix required no changes and none
were made.

---

## Findings

### Critical

None.

### High

1. **A Day 2 integration test still leaks the real host environment into a
   subprocess, reproducing exactly the class of bug an earlier review pass
   on this same branch already fixed elsewhere.**
   `tests/integration/test_tools_inspect_integration.py::test_tools_inspect_json_validates_via_json_tool`
   (lines 68-88) builds its subprocess environment as:
   ```python
   env = dict(os.environ)
   env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
   ```
   The other two tests in the same file were fixed earlier this cycle to use
   an explicit, minimal `_isolated_env(tmp_path, bin_dir)` helper
   (`{"PATH": str(bin_dir), "HOME": str(home)}` only) — this third test was
   missed. **Why it matters:** this test inherits the real invoking user's
   `HOME`, `XDG_CONFIG_HOME`, and any real `MAOPS_PY_*` variables. If the
   host has a stray or invalid real configuration file, or an invalid
   `MAOPS_PY_COMMAND_TIMEOUT_SECONDS`/`MAOPS_PY_MAX_OUTPUT_BYTES` set,
   `tools inspect` fails operationally (empty stdout), and the downstream
   `python -m json.tool` step fails on empty input — a flaky, host-dependent
   failure in exactly the file whose docstring claims to guard against a
   "real-looking subprocess call" leaking anything. This directly violates
   `.claude/CLAUDE.md`'s explicit testing policy: "Tests must be
   deterministic: no reliance on ... host environment variables." Verified
   independently by reading the current file content (not taken on either
   subagent's word). Currently masked in CI only because the workflow sets a
   job-level temporary `HOME` before any step runs — incidental, not a
   substitute for per-test isolation, and this reviewer's own local machine
   (which happens to have no stray config file right now) also currently
   masks it. Fix: `env = _isolated_env(tmp_path, bin_dir)`, same as the
   other two tests in the file.

### Medium

2. **`src/maops_pydevops.egg-info/` still leaks into the sdist — carried
   forward, unchanged, from the Day 1 v0.1.0 finding.** Same 7-entry shape
   confirmed on a fresh `python -m build` run. No `MANIFEST.in` was added in
   the interim. Not blocking (doesn't affect wheel correctness or
   installability, no `.py` files involved), but this has now persisted
   across two release cycles without a fix.

3. **`tests/integration/test_release_permissions.py` is not safe under any
   concurrent test/build invocation against the same working tree.** This
   is a genuinely new finding this cycle, reproduced live during this
   review: the test shells out to a fresh `make build` (which does `rm -rf
   dist build ...` first) and then globs `dist/*.whl`/`dist/*.tar.gz`
   directly against the shared repo-root `dist/` directory. When a second,
   concurrent `make build`/`make quality` process is running against the
   same checkout, this test can transiently observe zero, one, or a
   partially-written artifact and fail with a spurious `ValueError: not
   enough values to unpack`. Reproduced independently by two different
   reviewers (this session's own shell and the `release-engineer` subagent)
   hitting the identical failure at the identical concurrency window, and
   confirmed to disappear entirely under serialized execution. Not a defect
   in packaging correctness — a defect in the test's isolation from shared
   mutable state. Fix: have `_run_build()` write to a `tmp_path`-scoped
   output directory instead of the shared repository `dist/`, or accept
   this test is not safe to run in parallel with anything else touching
   `dist/` and document that constraint.

4. **JSON-shape tests for the two new report types check only a subset of
   fields, leaving truncation-flag and status/detail fields unverified for
   type.** Specifically:
   - `tests/unit/test_cli_tools_inspect.py::test_json_field_types` checks 7
     of `ToolInspectionResult`'s 10 fields plus 2 of 3 `configuration`
     fields — `status`, `executable`, `detail`, `stderr`,
     `stdout_truncated`, `stderr_truncated`, `configuration.path`, and
     `overall` are unchecked.
   - `test_json_null_fields_for_missing_tool` checks 4 of the 7 fields that
     should be `None` for a missing tool — `stderr`, `stdout_truncated`,
     `stderr_truncated` are unchecked (only `executable`, `exit_code`,
     `duration_ms`, `stdout` are asserted `None`).
   - `tests/unit/test_cli_config_show.py::test_json_field_types` omits
     `values.output_format` and both `sources.command_timeout_seconds`/
     `sources.max_output_bytes` type checks.

   None of these represent an actual runtime defect — every field's real
   value was cross-checked by equality assertions elsewhere in the same
   files — but the specific "assert every field's *type*" coverage the
   review criteria call for is incomplete for exactly the fields (truncation
   booleans) most likely to silently degrade into a wrong type in a future
   change.

### Low

5. **`--version`'s documented "always short-circuits, even alongside a
   subcommand" claim does not cover an incomplete two-level subcommand
   group**, and this is stated identically (without the exception) in four
   places: `README.md:100`, `.claude/CLAUDE.md:49`, `CHANGELOG.md:45`,
   `docs/architecture.md:57`. Reproduced live:
   ```
   $ maops-py --version tools
   usage: maops-py tools [-h] {inspect} ...
   maops-py tools: error: the following arguments are required: tools_command
   (exit 2)
   ```
   vs. the documented behavior working correctly for a *complete*
   subcommand (`maops-py --version doctor` → prints only the version, exits
   0). Root cause: `config_command`/`tools_command` are declared
   `required=True` on their nested `add_subparsers()` calls, so argparse
   raises a usage error during `parser.parse_args()` — before `main()` ever
   gets to inspect `args.version`. Not a security or correctness issue, but
   a real behavior-vs-documentation mismatch a user or script relying on the
   documented universal short-circuit could be surprised by. Fix: either
   narrow the doc claim to "alongside a complete subcommand" (cheap, four
   one-line edits) and add a regression test for `--version tools`/
   `--version config`, or restructure the two-level parsers so `--version`
   is checked before subcommand-presence validation (larger change).

6. **`tools inspect`'s exit-code semantics for a missing (but not failed)
   optional tool diverge from `doctor`'s, and this divergence is nowhere
   explicitly documented.** `doctor`'s optional-tool `WARN` never affects
   `overall`/the exit code (a missing git/docker/etc. is always non-fatal
   for `doctor`). `tools inspect`'s `_compute_overall()` treats any `WARN`
   as making `overall` non-`PASS`, and `run_tools_inspect()` returns exit 1
   for any non-`PASS` overall — so a single requested-but-missing tool fails
   the whole invocation. This matches the originally specified contract for
   `tools inspect` exactly (`0: overall pass; 1: overall warn or fail`), so
   it is **intentional, not a bug** — but a CI script author who has
   internalized `doctor`'s "missing tool = non-fatal warning" convention
   could reasonably assume the same for `tools inspect` and be surprised
   when a single missing tool fails their pipeline step. Neither
   `docs/configuration.md`, `docs/subprocess-safety.md`, nor the README's
   exit-code summary states this explicitly. Fix: one sentence in the
   README's exit-code summary and/or `docs/subprocess-safety.md` noting the
   contrast with `doctor`.

7. **Configuration validation error messages hardcode "not boolean" even
   when the actual invalid value is a different type entirely.**
   `core/config.py:120` and `:137` always render
   `"command_timeout_seconds must be numeric, not boolean"` /
   `"max_output_bytes must be an integer, not boolean"` whenever
   `_is_numeric_non_bool`/`_is_int_non_bool` reject a value — including when
   the actual offending value is a string or a float where an int was
   required. Reproduced live: `max_output_bytes = 65536.0` (a TOML float)
   produces `"max_output_bytes must be an integer, not boolean"`, which is
   confusing since no boolean was involved. Purely a diagnostic-message
   accuracy issue — validation correctness and the exit code are unaffected.

8. **`tests/unit/test_no_network_runner.py::test_tools_inspect_makes_no_network_calls`
   does not exercise the code path it appears to guard.** `which()` is
   mocked to always return `None`, so `_inspect_tool()` short-circuits
   before `run()`/`run_command()` is ever called — the `socket.socket`/
   `socket.create_connection` monkeypatches in this test are never actually
   exercised, so the test would pass identically even if `run_command()`
   opened a live socket. Not a real gap in the *suite's* overall coverage,
   since the adjacent `test_terraform_checkpoint_is_disabled_end_to_end` in
   the same file does correctly exercise the real, unmocked `run_command()`
   path — but this specific test's own name and monkeypatches overstate what
   it verifies.

### Future enhancements

- Add a `MANIFEST.in` (`prune src/*.egg-info`) to finally close the sdist
  leak (finding #2) — it has now persisted across two release cycles.
- Parameterize `test_release_permissions.py`'s `_run_build()` to target a
  `tmp_path`-scoped output directory rather than the shared repository
  `dist/`, eliminating the concurrency hazard (finding #3) at its root
  rather than relying on serialized test execution.
- Add a Bandit-style `S` (flake8-bandit) rule set to the Ruff `select` list,
  as suggested in the Day 1 review and still not applied — now doubly
  relevant with `core/runner.py`'s legitimate, narrowly-scoped `subprocess`
  usage in the codebase, so the linter could enforce the "only
  `core/runner.py` may import `subprocess`" boundary automatically rather
  than relying solely on `test_no_subprocess_shell.py`'s per-module
  assertions.
- Add an explicit `monkeypatch.delenv()` sweep for all four `MAOPS_PY_*`
  variables as a documented, shared pattern (not a `conftest.py`, per this
  project's existing no-conftest convention — a repeated inline fixture is
  fine) so the "config tests never depend on stray host `MAOPS_PY_*`
  variables" guarantee is self-evident rather than incidental to always
  setting `MAOPS_PY_CONFIG_FILE`.
- Branch the config-validation error messages (finding #7) on the actual
  observed type rather than a fixed "not boolean" string.

---

## Scores (out of 5)

| Area | Score | Notes |
|---|---|---|
| Architecture | 5 | Nested `config`/`tools` subparser groups, typed result dataclasses instead of custom exceptions, and the module-boundary discipline (`core/runner.py` sole `subprocess` importer, `core/config.py` sole named-env-var reader) all hold up under adversarial review by all three specialist passes; zero architectural violations found. |
| Python correctness | 4.5 | No functional defects in any reviewed path; docked for the `--version`+incomplete-subcommand-group documentation mismatch (Low #5) and the misleading validation error messages (Low #7). |
| Type safety | 5 | mypy strict clean across all 15 source files, zero `Any`, the `TypeGuard[float]`→`TypeGuard[int \| float]` fix from the prior review cycle confirmed correct, frozen dataclasses and explicit `to_dict()`/`to_json()` throughout, no `dataclasses.asdict()` anywhere. |
| Configuration safety | 5 | Every adversarial check in this review's scope (malformed TOML, duplicate keys, unknown key, bool-as-numeric/int both directions, invalid env override, symlink refusal with/without `--force`, directory-target refusal, atomic init with cleanup on every failure branch, mode 0600 independent of umask, path with spaces/shell metacharacters) passed exactly as specified, confirmed independently by all three review passes plus direct reproduction in this report. |
| Runner safety | 5 | `shell=False` at the single call site, exact argv preservation with shell metacharacters proven inert, `stdin=DEVNULL`, not-found/permission-denied/timeout all distinctly identified, byte-exact truncation with independent per-stream flags, UTF-8-replace decoding, and the `CHECKPOINT_DISABLE=1` fix confirmed genuinely effective end-to-end (not just asserted by a mock) — no defects found in this area by any reviewer. |
| CLI quality | 4 | Exit codes 0/1/2 correct on every path, console-script/`python -m` parity confirmed with zero duplicated logic; docked for the `--version`+incomplete-group precedence gap (Low #5) and the undocumented `tools inspect` WARN-is-fatal divergence from `doctor` (Low #6). |
| Operational usefulness | 4.5 | `config`/`tools inspect` genuinely useful and match their documented contracts; docked slightly because the WARN-is-fatal exit-code semantic (Low #6) is a plausible surprise for anyone porting a `doctor`-style CI probe to `tools inspect` without reading the fine print. |
| Packaging | 4 | Wheel is clean (0644, zero world-writable, exactly the expected 15 `.py` files), release-check ordering is a real enforced prerequisite chain not just documentation, offline exact-wheel installation independently re-verified in a second isolated venv; docked for the still-unfixed sdist egg-info leak now spanning two releases (Medium #2) and the newly surfaced test-concurrency hazard (Medium #3). |
| Automated testing | 4 | 259 tests, 99.89% coverage, and the adversarial-check matrix this review required was almost entirely already covered by dedicated tests — but one real, reproduced test-isolation violation of the project's own stated determinism policy remains unfixed (High #1), plus incomplete JSON field-type coverage in three test functions (Medium #4). |
| Documentation | 3.5 | `docs/configuration.md` and `docs/subprocess-safety.md` are thorough and accurate for everything they cover; docked because the `--version` short-circuit claim (repeated in four separate documents) doesn't carve out its one real exception, and the `tools inspect` exit-code contrast with `doctor` isn't documented anywhere despite being a meaningful behavioral fact for downstream CI consumers. |

**Overall: 4.45 / 5** — a substantially stronger release than Day 1's 3.9/5
in every dimension that mattered there (this deliverable's own git history
is a separate, out-of-scope concern for this review), with genuinely
thorough adversarial safety coverage in the two highest-stakes new areas
(configuration file handling and subprocess execution) and zero Critical or
High findings in either. The one High finding is a test-suite reliability
gap, not a defect in the shipped CLI's own behavior.

---

## Strongest three areas

1. **Subprocess safety discipline, proven rather than merely asserted.**
   `shell=False`, exact argv preservation, byte-exact truncation, and —
   notably — the `CHECKPOINT_DISABLE=1` fix from an earlier review cycle on
   this branch was re-verified in this review with a stub executable that
   *fails* unless the override genuinely reaches the child process, not just
   a monkeypatch assertion. This is the kind of adversarial test design that
   actually catches the class of bug it exists to catch.
2. **Configuration validation and atomic-init correctness.** Bool-vs-numeric
   handling exploits Python's `bool`-is-an-`int`-subclass correctly in both
   directions; symlink refusal is unconditional and checked before `force`
   is even consulted; every failure branch in the atomic-write sequence
   (`mkstemp`, `fchmod`, `fsync`, and the exception-handler cleanup itself)
   was independently confirmed to leave no leaked file descriptor and no
   orphaned temp file.
3. **Typed-result architecture with zero new custom exception classes.**
   Every public function in `core/config.py` and `core/runner.py` returns a
   frozen dataclass encoding success or a specific failure reason, extending
   Day 1's `DoctorCheck.status` pattern rather than introducing a parallel
   exception hierarchy — confirmed by grep to hold with no exceptions across
   the entire Day 2 delta.

## Five highest-priority improvements

1. **Fix the remaining test-isolation gap** (High #1) —
   `test_tools_inspect_json_validates_via_json_tool` still inherits the real
   host environment; a one-line change (`_isolated_env(tmp_path, bin_dir)`,
   already defined in the same file) closes it.
2. **Add a `MANIFEST.in`** (Medium #2 / Future enhancement) — the sdist
   egg-info leak has now persisted across two release cycles with an
   available, well-understood fix.
3. **Make `test_release_permissions.py` concurrency-safe** (Medium #3) —
   route its build output through a `tmp_path`, not the shared repository
   `dist/`, so this test stops being a source of spurious failures under any
   future parallel test execution.
4. **Document the two real behavior-vs-expectation gaps** (Low #5, #6) —
   the `--version`+incomplete-subcommand-group exception and the `tools
   inspect` WARN-is-fatal exit-code contrast with `doctor` are both cheap,
   one-paragraph documentation fixes that remove genuine surprise for
   downstream consumers.
5. **Fill in the missing JSON field-type assertions** (Medium #4) — three
   test functions already exist and already check most fields; extending
   them to cover the remaining fields (especially the truncation booleans)
   costs little and closes a real, if narrow, coverage gap.

## Unresolved findings

All eight findings above (High #1 through Low #8) are unresolved as of this
review — no code was modified as part of this review per its constraints.
Future enhancements are open suggestions, not defects.

## Release blockers

None. The single High finding (#1) is a test-suite reliability issue that
can produce a flaky CI result in an unusual host configuration; it does not
indicate any defect in the shipped `maops-py` CLI's own behavior, and the
workflow's existing job-level temporary-`HOME` step means it is very
unlikely to manifest in the project's actual CI runs today. It should be
fixed promptly, but it does not block tagging v0.2.0.

## Final v0.2.0 readiness recommendation

**Release-ready.** Every adversarial check specified for this review — TOML
malformation, duplicate keys, unknown keys, boolean-type confusion, invalid
environment overrides, symlink and directory refusal with and without
`--force`, path/argv shell-metacharacter inertness, the full runner failure
taxonomy (not-found, permission-denied, timeout, oversized/malformed
output), the full tool-inspection status matrix, offline exact-wheel
installation into two independently created venvs, stale-wheel rejection,
import-from-an-unrelated-directory, and unpinned-action rejection — passed
exactly as specified, independently confirmed by three specialist review
passes plus direct reproduction in this document. No Critical or High
finding touches the shipped CLI's actual runtime behavior, security posture,
or packaging correctness; the one High finding is a test-suite determinism
gap with an available one-line fix, and the Medium/Low findings are
documentation-accuracy and test-coverage-completeness items, not defects.
Recommend fixing High #1 and adding the `MANIFEST.in` (Medium #2) as
immediate follow-ups, but neither blocks tagging v0.2.0 today.
