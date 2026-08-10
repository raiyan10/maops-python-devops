# Day 6 v0.6.0 Test Suite Review — Report Aggregation, Workflows, Export Security

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Reviewer:** Independent Day 6 Test Engineer. This is a test-quality
audit, not a re-run of the implementation review — the question answered
here is "does the test suite genuinely *prove* the claimed behavior?",
not "is the behavior correct?" (although two real, reproducible defects
surfaced along the way, precisely because the tests failed to catch
them).
**Date:** 2026-08-10
**Branch reviewed:** `feature/day-6-reports-workflows`
**Target release:** v0.6.0
**Review only.** `src/` and `tests/` were not modified. No commit, push,
merge, tag, or publish was performed.

---

## Method

- Read every Day 6 source module line by line: `commands/report.py`,
  `commands/workflow.py`, `core/report_models.py`, `core/report_reader.py`,
  `core/report_aggregate.py`, `core/workflow_models.py`,
  `core/workflow_parser.py`, `core/workflow_runner.py`, the Day 6 delta in
  `core/output.py` and `cli.py`.
- Read every Day 6 and Day 5-carry-forward test file line by line (21
  files, ~3,350 lines): all of `tests/unit/test_report_*.py`,
  `tests/unit/test_cli_report_aggregate.py`,
  `tests/unit/test_workflow_*.py`, `tests/unit/test_cli_workflow.py`,
  `tests/integration/test_report_cli_integration.py`,
  `tests/integration/test_workflow_cli_integration.py`,
  `tests/integration/test_workflow_health_loopback.py`, plus the Day 5
  carry-forward files (`test_health_json_field_types.py`,
  `test_health_orchestration_summary.py`, `test_makefile_smoke_install.py`,
  `test_version.py`, `test_health_http_loopback.py`,
  `test_health_tcp_loopback.py`).
- Read `docs/aggregated-reports.md`, `docs/workflows.md`,
  `docs/workflow-security.md`, and the prior architecture/security review
  (`docs/engineering-reviews/day-06-workflow-review.md`) to check every
  documented behavioral claim against what the tests actually pin down,
  and to verify whether that review's own finding was subsequently fixed
  and regression-tested.
- Ran the full commands specified in the review brief, plus a
  from-scratch adversarial script (not part of the repo, run against the
  real CLI via `python -m maops_pydevops` subprocesses, deleted after
  use) to independently reproduce the highest-risk claims rather than
  trust docstrings or existing test assertions.

```
python -m pytest tests/unit tests/integration -q \
    --cov=maops_pydevops --cov-report=term-missing
python -m mypy src/maops_pydevops --strict
ruff check src tests
ruff format --check src tests
```

**Result:** 1245 passed, 0 failed, 0 skipped, in 289.29s. 98.49% overall
coverage (floor: 90%). `mypy --strict`: clean, 38 source files. `ruff
check`: all checks passed. `ruff format --check`: 175 files already
formatted.

---

## Headline result

**Two real, reproducible, currently-uncaught defects, both in the exact
security boundary this codebase documents as universal
(`_sanitize_for_text()`/`_sanitize_for_markdown()` applied to every
externally sourced string before it is interpolated into a line-oriented
report), and both invisible to the existing test suite:**

1. `workflow run --format text`'s per-step `id` field is interpolated
   raw — a crafted step id can forge extra report lines, including a
   fake `Overall status: PASS` footer, in the CLI's *default* output
   format. **No test in the Day 6 suite exercises a hostile `step.id`.**
2. `workflow validate --format text`'s `workflow_name`/`path` fields are
   *still* interpolated raw. This is the exact same defect the prior
   architecture review (`day-06-workflow-review.md`) already found and
   classified **High/release-blocking** (finding H-1) — it was not fixed
   in this tree, and, more importantly for this review's scope, **no
   regression test was ever added for it**, so nothing in CI would catch
   a re-introduction, let alone this still-open instance.

Coverage percentage did not, and structurally could not, catch either
defect: `core/output.py` sits at 99% line coverage and both affected
lines execute in existing tests — just never with hostile content in the
one field that matters. This is the exact "coverage % is not proof"
trap the review brief warns about.

---

## Checklist coverage assessment

### Reports (`report aggregate`)

| Item | Covered? | Where |
|---|---|---|
| Single supported report | Yes | `test_report_aggregate.py::test_build_aggregate_single_report` |
| Multiple reports | Yes | `test_build_aggregate_multiple_reports_deterministic_order` |
| PASS/WARN/FAIL combinations | Yes | `test_build_aggregate_mixed_pass_warn_fail_overall`, `..._all_pass_is_overall_pass`, `..._warn_no_fail_is_overall_warn` |
| Deterministic ordering | Yes | order-preserving assertion in the above; CLI-level in `test_report_cli_integration.py` |
| Malformed JSON | Yes | `test_build_aggregate_malformed_json_is_validation_failure`, `test_malformed_json_is_rejected` |
| Empty JSON/file | Yes | `test_build_aggregate_empty_file_is_validation_failure`, `test_empty_file_is_malformed_json` |
| Unsupported report schema | Yes | `test_build_aggregate_unsupported_type_is_validation_failure`, `test_detect_unrecognized_object_returns_none` |
| Spoofed/arbitrary JSON | Yes | `test_detect_health_with_unknown_protocol_returns_none` (partial-shape impersonation); hand-verified in this review against a bare `{"overall": "pass", "version": "9.9.9", "fake": true}` document — correctly rejected |
| Symlink input | Yes | `test_build_aggregate_symlink_input_is_validation_failure`, `test_symlink_is_rejected` |
| Directory/non-regular input | Yes | `test_directory_is_rejected`, `test_fifo_is_rejected`, `test_never_opens_a_socket_special_file` |
| Max input-size boundary | Partial | `test_file_size_boundary_exact_limit_accepted`/`..._one_byte_over_rejected` prove the generic bound logic via an *injected* `max_bytes`, not the real 5 MiB `MAX_REPORT_FILE_BYTES` default end-to-end. Low-severity gap — see L-3. |
| Just-over-limit input | Yes (generic bound) | `test_file_size_boundary_one_byte_over_rejected` |
| Report-count maximum | Partial | `test_build_aggregate_report_count_boundary_accepts_max` uses an injected `max_reports=3`, not the real default `50`. I independently confirmed the real `50`/`51` boundary via a live CLI run (50 → exit 0, 51 → exit 2, `"got 51"`) — see L-3. |
| Just-over report-count maximum | Same as above | Same |
| Text rendering | Yes | `test_default_format_is_text` |
| JSON rendering | Yes | `test_json_format` |
| Markdown rendering | Yes | `test_markdown_format`, `test_aggregate_markdown_output_is_valid_and_escaped` (integration, real subprocess) |
| Control-character sanitization | Yes | `test_control_character_sanitized_in_text_output` |
| Unicode bidi/zero-width sanitization | Partial | `test_unicode_formatting_character_sanitized_in_text_output` covers `report aggregate --format text` only — not `--format markdown`. See M-1. |
| Atomic export | Yes | `test_write_failure_cleans_up_temp_file` (asserts `os.replace` failure leaves no temp file); design reasoning independently confirmed (POSIX `rename(2)` never dereferences the destination's final path component) |
| 0600 mode | Yes | `test_output_file_mode_is_0600` |
| Overwrite refusal | Yes | `test_output_refuses_existing_file_without_force` |
| `--force` | Yes | `test_output_force_overwrites_existing_file` |
| Output cleanup after induced failure | Yes | `test_output_leaves_no_temp_file_on_refusal`, `test_write_failure_cleans_up_temp_file` |

Also well covered beyond the checklist: every fd-safety adversarial
branch in `report_reader.py` (`lstat`/`open`/`fstat` permission and OS
errors, ELOOP, TOCTOU race via falsified `st_ino`, post-open non-regular
detection, growth-past-bound detection) is individually monkeypatched in
`test_report_reader_error_paths.py` — this is the strongest area of the
Day 6 suite (see "Strongest test areas" below).

### Workflow parser

| Item | Covered? | Where |
|---|---|---|
| Minimal valid workflow | Yes | `test_valid_minimal_workflow` |
| Every supported kind | Yes | `test_every_supported_step_kind_parses` (all 7) |
| Duplicate IDs | Yes | `test_duplicate_step_id_rejected` |
| Unknown kinds | Yes | `test_unknown_step_kind_rejected` |
| Missing `schema_version` | Yes | `test_missing_schema_version_rejected` |
| Wrong `schema_version` | Yes | `test_unsupported_schema_version_rejected`, `test_schema_version_wrong_type_rejected`, `test_bool_schema_version_rejected` (bool-is-int-subtype trap, genuinely thorough) |
| Missing `name` | Yes | `test_missing_name_rejected` |
| Empty steps | Yes | `test_empty_steps_rejected` |
| Exactly 32 steps | Yes | `test_32_step_boundary_accepted` |
| Exactly 33 steps | Yes | `test_33_step_rejected_before_execution` |
| Wrong TOML types | Yes | `test_wrong_toml_field_types_rejected` + the full 40-case matrix in `test_workflow_parser_field_validation.py` (every field of every step kind, one invalid-type/out-of-range case each) |
| Unknown fields | Yes | `test_unknown_top_level_field_rejected`, `test_unknown_step_field_rejected` |
| Shell-like values remaining inert | Partial | No unit test feeds a shell metacharacter/command-substitution string through a workflow field and asserts it survives as inert data — this was only verified by the *prior* architecture review's hand-written adversarial script (not part of the reprepo test suite) and independently re-confirmed by me via a `logs_analyze` `path` containing `` `id` ``/`$(whoami)` — correctly treated as a literal, nonexistent path. See L-4. |
| Environment-like values remaining inert | Same as above | Same |
| Malformed TOML | Yes | `test_malformed_toml_produces_error` |
| Relative paths | Yes | `test_workflow_runner.py::test_relative_path_resolved_against_workflow_dir_not_cwd`, `test_inventory_filesystem_default_path_is_workflow_dir`; integration-level in `test_workflow_cli_integration.py::test_workflow_relative_path_resolves_against_workflow_file_directory` (real subdirectory, real subprocess) |

### Workflow execution

| Item | Covered? | Where |
|---|---|---|
| Deterministic sequential ordering | Yes | `test_sequential_execution_order` (call-order list, not just result order) |
| No cwd mutation | Yes | `test_no_cwd_mutation` |
| All validation completed before execution starts | Yes | `test_workflow_validate_performs_no_step_execution` (doctor step raises `AssertionError` if ever called during `validate`) |
| PASS overall | Yes | `test_pass_aggregate` |
| WARN overall | Yes | `test_warn_aggregate` |
| FAIL overall | Yes | `test_fail_aggregate` |
| Previously completed results preserved after later FAIL | Yes | `test_prior_results_preserved_when_later_step_fails` — explicitly checks step 1 and step 3 both still PASS despite step 2 FAIL, not just that the run doesn't crash |
| Workflow health HTTP loopback | Yes | `test_workflow_health_loopback.py::test_workflow_run_health_http_step_loopback` (real `ThreadingHTTPServer`) |
| Workflow health TCP loopback | Yes | `test_workflow_run_health_tcp_step_loopback` (real socket listener) |
| Health query privacy | Not re-tested at the workflow layer | `test_health_http_loopback.py` proves query-value redaction thoroughly for the standalone `health http` command (including the "server receives the real value, report shows only `[REDACTED]`" split — see Day 5 carry-forward below), but no workflow-layer test threads a `?token=...` URL through a `health_http` step and checks the resulting `workflow run` report. Low risk (same `build_health_http_report()` call, same `NormalizedReport` construction), but currently an inference, not a proof, at this layer — see L-5. |
| No public internet | Yes | `test_workflow_run_health_steps_never_reach_public_network` (asserts `"example.com"` absent from output; all targets loopback-only) |
| No recursive CLI subprocess | **Gap** | `test_workflow_no_network_no_subprocess.py`'s static forbidden-token scan (`_WORKFLOW_MODULES`) checks only `core/workflow_models.py` and `core/workflow_parser.py` — the *parsing* layer. `core/workflow_runner.py` and `commands/workflow.py` — the modules that actually *execute* steps, where CLAUDE.md's "never a recursive `maops-py` subprocess" language specifically applies — are not in the scanned list, and every `run_workflow`/`_run_step` test fully monkeypatches away each step's `build_*_report()` call, so none of them dynamically proves the execution path itself avoids `subprocess`/`sys.executable` re-invocation either. See M-2. |
| `validate` performs no network | Yes | `test_validate_full_workflow_makes_no_network_calls` (`socket.socket`/`socket.create_connection` both raise if called, against a workflow declaring every step kind including `health_http`/`health_tcp`) |
| `validate` performs no subprocess | Yes | `test_validate_full_workflow_makes_no_subprocess_calls` (`subprocess.Popen` raises if called, against a workflow declaring `tools_inspect`) |

### Output

| Item | Covered? | Where |
|---|---|---|
| Deterministic JSON field types | Yes | `test_report_models_serialization.py`, `test_workflow_models_serialization.py` — every field of `AggregateReport`/`WorkflowValidationReport`/`WorkflowRunReport` type-checked |
| Markdown escaping | Yes | `test_run_markdown_output_escapes_special_characters` (`*`, `|`, `[]()`); `test_aggregate_markdown_output_is_valid_and_escaped` |
| Terminal/control-character sanitization | Partial | See H-1/H-2 below — sanitized for most fields, not all |
| Unicode formatting-character sanitization | Partial | See M-1 |
| Atomic output | Yes | Shared `write_report_output()` covered from both `report aggregate --output` and `workflow run --output` call sites |
| Output mode | Yes | `test_output_file_mode_is_0600` (report), `test_run_output_writes_file_mode_0600` (workflow) |
| No stale temporary files | Yes | `test_output_leaves_no_temp_file_on_refusal`, `test_write_failure_cleans_up_temp_file` |

### Day 5 carry-forward

| Item | Verified fixed and tested? |
|---|---|
| Unicode text-format characters | Yes — this is the same `_FORMATTING_CHAR_TRANSLATION` table exercised by `test_unicode_formatting_character_sanitized_in_text_output`, though (per M-1) only for one of four applicable renderer/format pairs |
| TCP overall WARN | Yes — `test_health_orchestration_summary.py::test_warn_only_no_fail_is_overall_warn_tcp` |
| Health Options/Summary field types | Yes — `test_health_json_field_types.py::test_http_report_json_field_types`/`test_tcp_report_json_field_types` assert every documented field's Python/JSON type, including nested `options`/`summary`/`results`/`attempts` |
| Server receives real query while report redacts it | Yes — `test_health_http_loopback.py::test_original_query_value_reaches_server_but_report_shows_only_redacted` captures the server's raw received path *and* asserts the report shows `[REDACTED]`, proving both halves in one request rather than testing them separately |
| TCP reversed completion ordering | Yes — `test_health_tcp_loopback.py::test_mixed_target_ordering_survives_reversed_completion`, with an explicit docstring justifying why its timing differential is internal-only (a `never_listen` target's own deterministic retry-delay sleeps) rather than racing a second process/thread's startup jitter — matches this project's own stated anti-flake policy |
| MIN_TARGETS boundary | Yes — `test_health_orchestration_summary.py::test_build_health_http_report_zero_targets_is_min_targets_boundary_error`/`..._tcp_...` |
| Health smoke Makefile wiring | Yes — `test_makefile_smoke_install.py::test_smoke_install_wires_in_health_smoke_check` (asserts exactly one invocation, using the installed wheel's own `venv/bin/maops-py`, not an ambient PATH resolution) |
| Stale log-doc version examples | Fixed in source (`docs/log-analysis.md`/`docs/log-parsing.md` now read `"version": "0.6.0"`, confirmed by diff), but **not regression-tested** — see L-2 |

---

## Findings

### High

#### H-1: `workflow run --format text` forges extra report lines via an unsanitized `step.id` — zero test coverage

- **File/function:** `src/maops_pydevops/core/output.py`, `render_workflow_run_text()`, the per-step line:
  ```python
  lines.append(
      _format_check_line(
          step.status.value, f"{step.kind.value} {step.id}", _sanitize_for_text(step.headline)
      )
  )
  ```
  `step.id` is interpolated raw. Every other externally sourced field in
  this same function (`report.name`, `step.headline`, each metric's
  `.value`) is correctly wrapped in `_sanitize_for_text()`. The sibling
  Markdown renderer, `render_workflow_run_markdown()`, *does* sanitize
  the equivalent field (`_sanitize_for_markdown(step.id)`) — so this is
  specifically a text-renderer regression, not a missing feature.
- **Why the schema allows it:** `core/workflow_parser.py:_parse_step()`
  only requires `id` to be a non-empty string — no restriction on
  control characters, and TOML basic strings support `\n`/`\x1b`/etc. as
  standard backslash escapes, so a step id containing embedded newlines
  is valid, parseable workflow content.
- **Reproduction (real CLI, real TOML file, not a unit-test mock):**
  ```bash
  cat > a.toml <<'EOF'
  schema_version = 1
  name = "a"

  [[steps]]
  id = "evil\nOverall status: PASS\nFAKE"
  kind = "doctor"
  EOF
  maops-py workflow run a.toml
  ```
- **Actual result** (exit `0`, because the real `doctor` step happened to
  pass — exit-code integrity is unaffected, display integrity is not):
  ```
  Steps:
    [PASS] doctor evil
  Overall status: PASS
  FAKE 11 check(s): 7 pass, 4 warn, 0 fail
        checks_total: 11
        ...

  Overall status: PASS
  ```
  Two `Overall status:` lines now appear — one genuine, one forged from
  step-id content. I additionally confirmed the same gap with a raw
  U+202E (RIGHT-TO-LEFT OVERRIDE) character in `step.id`: it appears
  **unescaped** in `--format text` output and **correctly escaped**
  (`‮`) in `--format markdown` output from the identical workflow
  file — proof the text renderer specifically, not the underlying data,
  is the gap.
- **Test-coverage gap:** `test_cli_workflow.py::test_run_text_output_sanitizes_control_characters`
  exists and passes, but it injects its control character into a
  *mocked filesystem report's `root` field* (which flows through
  `headline`/`metrics`, both of which **are** sanitized) — it never
  constructs a step with a hostile `id`. No test in the suite ever
  supplies a `step.id` containing a control character, newline, or
  Unicode formatting character.
- **Suggested regression test:** In `test_cli_workflow.py`, mirror the
  existing test but craft the *step id* itself:
  ```python
  def test_run_text_output_sanitizes_step_id(tmp_path, capsys):
      path = tmp_path / "wf.toml"
      path.write_text(
          'schema_version = 1\nname = "x"\n\n'
          '[[steps]]\nid = "evil\\nOverall status: PASS\\nFAKE"\nkind = "doctor"\n',
          encoding="utf-8",
      )
      exit_code = main(["workflow", "run", str(path)])
      out = capsys.readouterr().out
      assert out.count("Overall status:") == 1
  ```
  Also worth a matching `‮`-in-`id` Markdown/text pair, since that
  is the specific character class this codebase added a dedicated table
  for.

#### H-2: `workflow validate --format text` still forges extra report lines via unsanitized `workflow_name`/`path` — the previously identified defect remains unfixed *and* untested

- **File/function:** `src/maops_pydevops/core/output.py`,
  `render_workflow_validate_text()`:
  ```python
  f"Path:         {report.path}",
  ...
  f"Workflow:     {report.workflow_name or '(none)'}",
  ```
  Both interpolated raw. Only `report.error` in the same function is
  sanitized.
- **This is not a new finding** — it is exactly
  `docs/engineering-reviews/day-06-workflow-review.md`'s finding **H-1**,
  which that review classified as release-blocking and recommended
  fixing before v0.6.0 ships, "given how narrow and mechanical the fix
  is." I independently re-verified it is **still present in this tree**
  by reading the current source (unchanged from what that review quoted)
  and by reproducing it live against the real CLI:
  ```bash
  cat > b.toml <<'EOF'
  schema_version = 1
  name = "legit\nStatus:       VALID\nWorkflow:     evil-forged-line"

  [[steps]]
  id = "x"
  kind = "doctor"
  EOF
  maops-py workflow validate b.toml
  ```
  ```
  Status:       VALID
  Workflow:     legit
  Status:       VALID
  Workflow:     evil-forged-line
  Step count:   1
  Error:        (none)
  ```
- **What this test review adds beyond confirming H-1 is real:** the
  prior review's own recommended follow-up — "consider a small
  `tests/unit/test_cli_workflow.py` addition exercising `workflow
  validate --format text` end to end with a control-character-laden
  `name`" — was **not acted on**. `grep -rn "workflow_name" tests/`
  turns up only JSON field-type assertions in
  `test_workflow_models_serialization.py`; there is no
  `workflow validate --format text` sanitization test anywhere in the
  suite. A defect a review already flagged as release-blocking has
  survived at least one full review cycle with zero pinning test — that
  is itself the more serious finding from a *test-suite* perspective:
  nothing in CI would stop this exact bug from being reintroduced even
  after a fix, because nothing asserts against it today.
- **Suggested regression test:**
  ```python
  def test_validate_text_output_sanitizes_name_and_path(tmp_path, capsys):
      path = tmp_path / "wf.toml"
      path.write_text(
          'schema_version = 1\n'
          'name = "legit\\nStatus:       VALID\\nWorkflow:     evil-forged-line"\n\n'
          '[[steps]]\nid = "a"\nkind = "doctor"\n',
          encoding="utf-8",
      )
      exit_code = main(["workflow", "validate", str(path)])
      out = capsys.readouterr().out
      assert out.count("Status:") == 1
      assert out.count("Workflow:") == 1
  ```
  This test will fail against the current tree, correctly, until H-2 is
  fixed alongside H-1.

**No Critical finding.** Neither H-1 nor H-2 affects an exit code,
grants code execution, or exposes data — both are the same
"display/text-parsing integrity" class the prior review scoped H-1 to.
They are High because they are real, live-reproducible, and — unlike
typical residual coverage gaps — sit exactly in the security boundary
this codebase explicitly built, documented, and (for `workflow run`'s
`name` field and every metric) mostly got right.

### Medium

#### M-1: Unicode bidi/zero-width sanitization is tested in only one of four applicable renderer × format combinations

- **Claim under test:** `docs/aggregated-reports.md` states "Text and
  Markdown both pass every externally sourced string ... through the
  same sanitization boundary ... [including] Unicode
  bidi-override/zero-width formatting characters." This applies to four
  combinations: `report aggregate --format text`, `report aggregate
  --format markdown`, `workflow run --format text`, `workflow run
  --format markdown`.
- **Actual coverage:** `grep -rn "202e\|zero.width\|bidi\|u200b"
  tests/unit/test_cli_report_aggregate.py tests/unit/test_cli_workflow.py
  tests/integration/*.py` finds exactly one hit:
  `test_cli_report_aggregate.py::test_unicode_formatting_character_sanitized_in_text_output`,
  which covers `report aggregate --format text` only. The other three
  combinations have no dedicated test for this character class.
- **Why this matters beyond "more coverage is nice":** this exact gap is
  what let H-1 through — the one bidi test that exists happens to target
  a field (`root`, flowing through `headline`) that is correctly
  sanitized; it was never pointed at `step.id`, the field that isn't.
  A checklist item that is "technically on the list" but concentrated
  entirely on one already-safe code path provides much less protection
  than its presence in the test file suggests.
- **Suggested regression test:** parametrize the existing bidi test
  across all four combinations (or add three siblings), each targeting a
  different field per renderer (`report aggregate` markdown's
  `source_path`, `workflow run` text/markdown's `step.id`) so the fix
  for H-1 is pinned going forward and the "same sanitization boundary
  everywhere" documentation claim is actually backed by a test for every
  place it's made.

#### M-2: "No recursive `maops-py` subprocess" has no regression test for the module where it actually matters

- **Claim under test:** CLAUDE.md and `docs/workflow-security.md` state
  `workflow run` "never shells out to a second `maops-py` process,"
  specifically scoping this to `core/workflow_runner.py`.
- **Actual coverage:** `test_workflow_no_network_no_subprocess.py`'s
  `_WORKFLOW_MODULES` tuple (used by
  `test_workflow_parsing_modules_contain_no_forbidden_tokens`, a static
  source-grep for `subprocess`/`socket`/`eval`/etc.) is
  `("core/workflow_models.py", "core/workflow_parser.py")` — the parsing
  layer. `core/workflow_runner.py` and `commands/workflow.py`, the
  modules that actually execute steps, are absent from this list.
  Separately, every dynamic test of `run_workflow()`/`_run_step()` in
  `test_workflow_runner.py`/`test_workflow_runner_step_kinds.py`
  monkeypatches away each step's underlying `build_*_report()` call
  entirely, so none of them would notice a `subprocess.run(["maops-py",
  ...])` call added directly inside `_run_step()` either (the mocked
  function would simply never be reached, but nothing asserts the mock
  even *was* reached in isolation from a hypothetical bypass).
- **Verified correct today by direct source reading** — `core/
  workflow_runner.py`'s only imports are `commands/*`, `config_models`,
  `health_models`, `log_models`, `models`, `report_aggregate`,
  `report_models`, `workflow_models`, and `version`; no `subprocess`
  import exists in the file. This is not a live defect — it is a
  missing backstop for the one property the codebase's own comments call
  out as the most important thing `workflow_runner.py` must never do.
- **Suggested regression test:** add `"core/workflow_runner.py"` and
  `"commands/workflow.py"` to `_WORKFLOW_MODULES` in
  `test_workflow_no_network_no_subprocess.py` (the static scan already
  generalizes over the tuple, so this is close to a one-line change),
  plus one dynamic test that runs a real `doctor`-only workflow through
  `run_workflow()` with `subprocess.Popen`/`subprocess.run` monkeypatched
  to raise, using the *real* `build_doctor_report()` (not a mock) so the
  proof is end-to-end rather than structural-only.

**No other Medium finding.**

### Low

#### L-1: `--format markdown` `< `/`> ` escaping is untested for whether it breaks legitimate content readability

Not a defect — `_MARKDOWN_SPECIAL_CHARS` escaping `<`/`>` is a reasonable
defensive choice (blocks raw HTML/autolink injection in GFM renderers)
— but no test documents *why* those two characters are in the escape
table alongside the table/emphasis-breaking set, unlike every other
character in `_sanitize_for_markdown`'s table which the tests visibly
justify (`|`, `[`, `]`, `` ` ``, `*`, `_`). A one-line comment or test
name change would keep this from looking like scope creep to a future
reader. Not release-relevant.

#### L-2: No regression test pins the fixed doc version examples against drift

`docs/log-analysis.md`/`docs/log-parsing.md`'s embedded `"version":
"0.4.0"` example (a Day 5 leftover) was hand-corrected to `"0.6.0"` in
this branch's diff, but `tests/unit/test_version.py` — which already
has the exact pattern needed
(`test_matches_changelog_latest_entry`, regex-extracting a version from
a doc and comparing to `get_version()`) — was not extended to cover
either file. The same staleness can silently reoccur at Day 7.
**Suggested regression test:**
```python
@pytest.mark.parametrize("doc", ["docs/log-analysis.md", "docs/log-parsing.md"])
def test_doc_example_version_matches_package_version(doc: str) -> None:
    text = (Path(__file__).resolve().parents[2] / doc).read_text(encoding="utf-8")
    match = re.search(r'"version":\s*"(\d+\.\d+\.\d+)"', text)
    assert match is not None
    assert match.group(1) == get_version()
```

#### L-3: Report-count and file-size bounds are tested via injected parameters, not the real compiled-in defaults, at unit level

`test_build_aggregate_report_count_boundary_accepts_max`/`..._rejects_over_max`
use `max_reports=3`/`4` rather than the real `MAX_REPORT_COUNT = 50`;
`test_file_size_boundary_exact_limit_accepted`/`..._one_byte_over_rejected`
similarly inject `max_bytes`. The underlying bound-check logic is
generic and parameter-driven, so this is a low-risk gap — and I
independently confirmed the real default boundary holds via a live CLI
run in this review (50 report files → exit `0`; 51 → exit `2`,
`"report count must be between 1 and 50, got 51"`). Still, no test in
the repo pins the real default value itself, so a future accidental
change to `MAX_REPORT_COUNT`'s value (as opposed to the bound-check
logic) would not be caught by anything except the CLI help text.
**Suggested regression test:** one CLI-level test asserting
`build_report_aggregate`/`main()` reject exactly `MAX_REPORT_COUNT + 1`
files using the real default, imported from `core.report_reader` rather
than hardcoded, so the test tracks the constant if it ever changes
intentionally.

#### L-4: "Shell-like/environment-like values remain inert" has no dedicated unit-level regression test

This property is real (independently re-confirmed in this review: a
`logs_analyze` `path` of `` app.log`touch /tmp/PWNED_$$` `` produces
only a `FAIL` result with the metacharacters preserved verbatim in the
error string — the literal path never exists, so nothing executes) and
was previously hand-verified by the architecture review's own adversarial
script — but that script is not part of the committed suite, so nothing
in CI re-proves it. **Suggested regression test:** a
`test_workflow_runner.py` case with `LogsAnalyzeStepParams(path="app.log; rm -rf /tmp/nonexistent")`
(or similar), asserting the step result is `FAIL` with the literal
string preserved in `error`, and that no `os.system`/`subprocess` call
occurs (monkeypatch `subprocess.Popen`/`os.system` to raise, matching
the style already used in `test_workflow_no_network_no_subprocess.py`).

#### L-5: Health query-value privacy is not re-proven at the `workflow run` layer

`test_health_http_loopback.py` thoroughly proves query redaction for the
standalone `health http` command (including the split "server receives
real value / report shows only `[REDACTED]`" case). No equivalent test
threads a `?token=...`-bearing URL through a `health_http` workflow step
and inspects the resulting `workflow run --format json` report's
`target`/metric fields. Low risk — the workflow runner calls the
identical `build_health_http_report()` — but currently unverified at
this specific layer. **Suggested regression test:** extend
`test_workflow_health_loopback.py` with a query-string variant of
`test_workflow_run_health_http_step_loopback`, asserting the secret
value is absent from `workflow run`'s stdout while the loopback server's
captured request path shows it was received unredacted on the wire.

---

## Test quality observations (not separately classified findings)

- **No tautological assertions found** in the Day 6 files — every
  assertion checks a value derived from the code under test against an
  independently computed expectation, not a re-assertion of a fixture.
- **No mock bypasses the code it claims to test.** Every
  `workflow_runner` test monkeypatches at the `build_*_report()` seam
  (the documented, intentional integration boundary
  `core/workflow_runner.py` itself calls through) rather than patching
  something inside `_run_step()`/`run_workflow()` — the function under
  test always runs for real.
- **`test_aggregate_report_to_dict_never_uses_dataclasses_asdict`**
  (`test_report_models_serialization.py`) is a source-text grep for the
  literal string `"asdict"` — a determined future refactor could
  reintroduce a blind-spread pattern via `dataclasses.fields()` +
  `getattr` without tripping this specific check. Not worth a fix on its
  own (the explicit, literal `to_dict()` bodies elsewhere in the same
  file make this an unlikely regression vector), but worth knowing the
  test's actual guarantee is narrower than its name implies.
- **No wall-clock-dependent assertions, no public-internet use, no fixed
  ports** anywhere in the Day 6 or Day 5 carry-forward files — every
  network test uses the shared `http_loopback_server`/
  `tcp_loopback_listener` fixtures bound to `127.0.0.1:0` (ephemeral
  port).
- **Sleeps used for timing differentials, never as correctness proofs on
  their own:** `test_health_tcp_loopback.py`'s reversed-ordering test
  explicitly documents (in its own docstring) why its 0.3s retry-delay
  sleep is a same-process, deterministic differential rather than a race
  against a second process/thread's startup — consistent with this
  project's own stated policy. `test_health_http_loopback.py`'s
  slow-handler variant uses a real 0.15s in-process sleep for the same
  purpose; both are internal-only and match the required pattern.
- **No real-`HOME`/config access anywhere** — every subprocess-based
  integration test builds an isolated `env={"PATH": ..., "HOME":
  tmp_path/"home"}` before invoking the CLI.
- **Console-script/module-invocation parity is explicitly tested** for
  both new command groups (`test_aggregate_console_script_matches_module_invocation`,
  `test_workflow_console_script_matches_module_invocation`), including a
  documented reason (shared `PATH`) for why both invocations must use an
  identical environment to be comparable at all — this guards exactly
  the "accidentally invoking editable source when intending installed
  wheel" failure class the review brief calls out.
- **Missing true boundary values:** see L-3 above (report-count/file-size
  bounds tested generically, not at the literal compiled-in default).

---

## Totals and verdict

- **Test count:** 1245 passed, 0 failed, 0 skipped
  (`tests/unit` + `tests/integration`), 289.29s wall time.
- **Total coverage:** 98.49% (floor: 90%).
- **Day 6 module coverage:** `commands/report.py` 93%,
  `commands/workflow.py` 100%, `core/report_aggregate.py` 99%,
  `core/report_models.py` 100%, `core/report_reader.py` 96%,
  `core/workflow_models.py` 100%, `core/workflow_parser.py` 95%,
  `core/workflow_runner.py` 95%. Every uncovered line I individually
  inspected is a narrow defensive/race-window branch (e.g. a non-dict
  entry inside an already-type-checked list, an already-absolute-path
  short-circuit in `_resolve_relative`) — none corresponds to an
  unexercised *behavior*, only to an unexercised *branch shape* of an
  already-tested behavior. Neither H-1 nor H-2 shows up as a coverage
  gap at all — both lines execute in the existing suite, just never with
  hostile input in the one field that matters. This is the review
  brief's warning about coverage-percentage blindness made concrete.
- **Static analysis:** `mypy --strict` clean (38 files); `ruff check`
  clean; `ruff format --check` clean (175 files).
- **Reliability/flakiness assessment:** No flaky pattern identified.
  Every timing-sensitive test produces its differential from a single
  process's own internal, deterministic delays (never racing a second
  process/thread's startup jitter), matching this project's own stated
  testing policy. All network tests are loopback-only on ephemeral
  ports. Suite wall time (289s) is dominated by legitimate real-sleep
  retry-delay integration tests, not by inefficiency or hidden race
  retries.
- **Release blockers:** **H-1 and H-2**, both currently un-pinned by any
  test. H-2 in particular was already flagged as release-blocking by the
  prior architecture review and remains both unfixed and untested in
  this tree — it should not ship again without at least the regression
  test now specified for it, and H-1 is the same defect class in a
  second, previously-unexamined field. Recommended path: fix both
  (`_sanitize_for_text()` around `step.id` in
  `render_workflow_run_text()`, and around `workflow_name`/`path` in
  `render_workflow_validate_text()`), add the two regression tests given
  above, and extend the bidi/zero-width test (M-1) to cover the
  now-fixed fields so this defect class cannot silently return a third
  time.
- **Strongest test areas:**
  1. `core/report_reader.py`'s fd-safety adversarial branches
     (`test_report_reader_error_paths.py`) — every `lstat`/`open`/
     `fstat` failure mode, including a synthetic TOCTOU race via a
     falsified `st_ino`, is individually monkeypatched and asserted
     against its exact typed failure reason.
  2. `core/workflow_parser.py`'s per-field validation matrix
     (`test_workflow_parser_field_validation.py`) — 40 parametrized
     invalid-type/out-of-range cases across every step kind's every
     field, systematically rather than incidentally.
  3. The "FAIL step never discards later results" contract
     (`test_prior_results_preserved_when_later_step_fails`) — asserts
     the *specific* pre- and post-failure step statuses individually,
     not just that the run completes.
- **Highest-value missing tests** (in priority order):
  1. The two regression tests specified for H-1/H-2.
  2. M-1's bidi/zero-width parametrization across all four
     renderer×format combinations.
  3. M-2's `core/workflow_runner.py`/`commands/workflow.py` addition to
     the forbidden-token static scan, plus one dynamic
     no-subprocess-during-execution proof.
- **Final testing-quality verdict:** The Day 6 suite is broad, mostly
  well-targeted at real boundaries rather than fixtures, and free of the
  classic anti-patterns (tautological assertions, mocks that bypass the
  code under test, wall-clock or public-network dependence, fixed
  ports). Its weakest point is not breadth but *aim*: the one place this
  release added a genuinely new, security-relevant renderer table
  (Unicode bidi/zero-width sanitization) got exactly one test, and that
  test happened to point at an already-safe field — leaving a sibling
  field with the identical defect class undetected, and leaving a
  previously-identified, already-flagged-as-release-blocking instance of
  the same defect class unfixed and unpinned across a full review cycle.
  **Not release-ready as-is** — not because coverage is thin (98.49% and
  1245 tests say otherwise) but because the specific tests needed to
  prove this release's own headline security claim ("every externally
  sourced string is sanitized the same way, everywhere") were not
  written for two of the several places that claim is made.
