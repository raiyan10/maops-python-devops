# Workflows

`maops-py workflow` runs a declarative, sequential automation workflow —
a fixed TOML file describing a small, ordered list of existing `maops-py`
checks to run and combining their results into one report. See
[docs/workflow-security.md](workflow-security.md) for the full security
model (declarative data, never executable code).

```bash
maops-py workflow validate FILE
maops-py workflow validate FILE --format text|json

maops-py workflow run FILE
maops-py workflow run FILE --format text|json|markdown
maops-py workflow run FILE --output PATH
maops-py workflow run FILE --output PATH --force
```

## Workflow file format

TOML, `schema_version = 1` (the only supported value in this release),
a `name`, and one or more `[[steps]]` (minimum 1, maximum 32):

```toml
schema_version = 1
name = "release readiness"

[[steps]]
id = "doc"
kind = "doctor"

[[steps]]
id = "sysinv"
kind = "inventory_system"

[[steps]]
id = "fsinv"
kind = "inventory_filesystem"
path = "."
max_depth = 2
top = 5

[[steps]]
id = "logs"
kind = "logs_analyze"
path = "app.log"
error_threshold = 1

[[steps]]
id = "api"
kind = "health_http"
urls = ["https://api.example.com/health"]
retries = 2

[[steps]]
id = "db"
kind = "health_tcp"
targets = ["db.internal:5432"]
```

Every step requires `id` (a non-empty string, unique within the file) and
`kind` (one of the seven supported kinds below). Unknown top-level keys
and unknown per-step keys are both rejected outright — the same
"unrecognized key makes the file invalid" policy `core/config.py`
established for `maops-py config` files.

## Supported step kinds

Each kind maps directly onto the equivalent CLI subcommand's own
parameters, executed through the package's actual internal API
(`commands/*.py`'s `build_*_report()` functions) — never a shell command,
never a recursive `maops-py` subprocess:

| `kind` | Equivalent command | Extra fields (all optional unless marked) |
|---|---|---|
| `doctor` | `maops-py doctor` | none |
| `tools_inspect` | `maops-py tools inspect` | `tools` (array of strings, from the same fixed allowlist as `tools inspect`), `timeout_seconds` |
| `inventory_system` | `maops-py inventory system` | none |
| `inventory_filesystem` | `maops-py inventory filesystem` | `path` (default: the workflow file's own directory), `max_depth`, `max_entries`, `top` |
| `logs_analyze` | `maops-py logs analyze` | `path` **(required)**, `input_format`, `max_lines`, `max_bytes`, `max_line_bytes`, `top`, `bucket_seconds`, `repeat_threshold`, `error_threshold`, `redact` |
| `health_http` | `maops-py health http` | `urls` **(required, array, 1-100)**, `method`, `expect_status_min`, `expect_status_max`, `timeout_seconds`, `retries`, `retry_delay_seconds`, `workers` |
| `health_tcp` | `maops-py health tcp` | `targets` **(required, array, 1-100)**, `timeout_seconds`, `retries`, `retry_delay_seconds`, `workers` |

Every field's type and range is validated using the exact same bounds the
equivalent CLI flag enforces (e.g. `max_depth` is `0`-`64`, `--retries`
equivalent `retries` is `0`-`5`), and `health_http`'s `urls`/`health_tcp`'s
`targets` are validated with the real `validate_http_target()`/
`validate_tcp_target()` functions `health http`/`health tcp` themselves
use — a workflow's target/tool mistakes are caught with the identical
rules the equivalent CLI subcommands enforce, not a second, independently
maintained copy of them. `tools_inspect`'s `tools` is checked against the
real, fixed five-tool allowlist (`git`, `docker`, `kubectl`, `terraform`,
`ansible`).

There is deliberately no way to express: a shell command, an arbitrary
Python callable, a loop, a conditional, a retry-the-whole-step policy
beyond what the underlying command already supports, a cron/schedule, or
a plugin. See [docs/workflow-security.md](workflow-security.md) for the
complete list of excluded capabilities and why.

## `workflow validate`: parse and check only

```bash
$ maops-py workflow validate release.toml
MAOps Python DevOps Toolkit - Workflow Validation
Version:      0.7.0
Path:         release.toml
Status:       VALID
Workflow:     release readiness
Step count:   6
Error:        (none)
```

`workflow validate` **never executes a step** — it never resolves a tool
executable, opens a socket, or reads a log/filesystem path's content. It
parses the TOML document and schema-validates every field (including
running `health_http`/`health_tcp` targets through the real,
network-free `validate_*_target()` functions). Exit `0` for a valid
workflow, `2` for a schema/usage error (with the specific reason printed).

## `workflow run`: sequential execution

Steps always execute **in declared order**, one at a time — never
reordered, never parallelized across steps (a `health_http`/`health_tcp`
step's own targets may still run concurrently within that one step,
exactly as `health http`/`health tcp` already do). Every declared step
always runs to completion, regardless of an earlier step's outcome: a
step that cannot produce a report (a filesystem root that vanished, an
unreachable target) becomes a `fail` result with its `error` field
explaining why, but does not abort the run or discard already-completed
steps' results.

```json
{
  "version": "0.7.0",
  "path": "release.toml",
  "name": "release readiness",
  "options": {"max_steps": 32},
  "summary": {"steps": 6, "pass_count": 5, "warn_count": 1, "fail_count": 0},
  "steps": [
    {
      "id": "doc",
      "kind": "doctor",
      "status": "pass",
      "headline": "11 check(s): 11 pass, 0 warn, 0 fail",
      "metrics": [
        {"label": "checks_total", "value": "11"},
        {"label": "checks_pass", "value": "11"},
        {"label": "checks_warn", "value": "0"},
        {"label": "checks_fail", "value": "0"}
      ],
      "error": null
    }
  ],
  "overall": "warn"
}
```

Each step's `status`/`headline`/`metrics` are produced by the exact same
normalization `report aggregate` uses (`core/report_aggregate.py:
normalize_report()`, applied directly to the step's own real, in-memory
report object) — a workflow step's summary and an aggregated report's
summary for the same underlying command come from one shared code path.
See [docs/aggregated-reports.md](aggregated-reports.md) for the
normalization contract in full.

## Overall status and exit codes

```
FAIL  if any step is FAIL
WARN  if none FAIL and at least one WARNs
PASS  otherwise
```

| Exit | Meaning |
|---|---|
| `0` | `overall` is `pass` or `warn` (`workflow run`); the workflow is valid (`workflow validate`). |
| `1` | `overall` is `fail` (`workflow run`), or writing `--output` failed. |
| `2` | Schema/usage error — malformed TOML, missing/wrong-typed field, unknown key, duplicate step id, unsupported `schema_version`, 0 or 33+ steps, or an invalid `health_http`/`health_tcp` target/`tools_inspect` tool name. |

## Relative path semantics

`inventory_filesystem`'s `path` and `logs_analyze`'s `path` resolve
**relative to the workflow TOML file's own directory** — never the
process's current working directory, and the process's cwd is never
mutated (`os.chdir()` is never called anywhere in this package). Both
`inventory filesystem`/`logs analyze` (the CLI subcommands) still resolve
their own bare-path arguments against the *process's* cwd as always;
workflows are the one place a path is deliberately re-based, because a
workflow file is meant to be portable and runnable from any directory.
If `inventory_filesystem`'s `path` is omitted, it defaults to the
workflow file's own directory (not the process cwd either).

```toml
# workflows/nightly.toml
[[steps]]
id = "fsinv"
kind = "inventory_filesystem"
path = "../data"   # resolves to <dir containing nightly.toml>/../data
```

## Bounds

- `schema_version`: must equal `1`.
- Steps per workflow: `1`-`32`.
- `health_http`/`health_tcp` targets per step: `1`-`100` (the existing
  `health http`/`health tcp` bound, unchanged).
- Every other numeric field uses the identical bound its CLI flag
  equivalent already enforces — see the table above and
  `docs/health-checks.md`/`docs/log-analysis.md`/`docs/inventory.md` for
  the per-field ranges.

## Output formats and secure export

Identical to `report aggregate`: `--format text` (default), `--format
json`, or `--format markdown`; `--output PATH` writes atomically at mode
`0600`, refuses an existing target unless `--force`, always refuses a
symbolic link target even with `--force`, requires the parent directory
to already exist, and leaves no temporary file behind on failure. See
[docs/aggregated-reports.md](aggregated-reports.md#secure---output-export)
for the complete contract (shared verbatim between the two commands), and
[docs/aggregated-reports.md](aggregated-reports.md#markdown-escaping-rationale)
for why each Markdown-significant character is escaped in `--format
markdown` output (also shared verbatim — both commands render through the
same `_sanitize_for_markdown()`).

## No scheduler or cron feature

`maops-py workflow` runs once, synchronously, when invoked — there is no
built-in scheduling, daemon mode, or cron integration in this release.
Run it from your own scheduler (`cron`, a CI pipeline, a systemd timer)
the same way you would any other CLI command.
