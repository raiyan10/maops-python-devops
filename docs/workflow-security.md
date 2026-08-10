# Workflow Security

`maops-py workflow` is the package's first feature that reads a
user-authored file and, based on its content, decides which of several
different operations to perform. This document is the complete
"declarative data, never executable code" contract for that feature.

## The workflow file is data, not code

A workflow TOML file is parsed and validated (`core/workflow_parser.py`)
into a fixed, closed set of typed Python dataclasses
(`core/workflow_models.py`) — `Workflow`, `WorkflowStep`, and one
frozen parameter dataclass per supported step kind
(`DoctorStepParams`, `ToolsInspectStepParams`,
`InventorySystemStepParams`, `InventoryFilesystemStepParams`,
`LogsAnalyzeStepParams`, `HealthHttpStepParams`, `HealthTcpStepParams`).
There is no code path anywhere in this package that:

- Interprets a workflow field as a shell command, shell fragment, or
  shell metacharacter sequence.
- Performs `${...}`-style template expansion, environment-variable
  substitution, or command substitution on any workflow field.
- Executes `eval`, `exec`, a dynamic `import`, or `__import__` on
  workflow content.
- Instantiates a step kind other than the seven fixed kinds in
  `WorkflowStepKind` — an unrecognized `kind` value is a validation
  error (exit `2`), never silently ignored or executed as something else.
- Passes a workflow-supplied string to `core/runner.py`'s
  `run_command()` (the sole subprocess-execution primitive in this
  package) at all. `tools_inspect` workflow steps call
  `commands/tools.py:build_inspect_report()` — the exact same function
  `maops-py tools inspect` itself calls — which resolves each requested
  tool name against the fixed, five-tool allowlist
  (`TOOL_ALLOWLIST`) and always executes one of five fixed, hardcoded
  argv tuples. A workflow file can select *which* allowlisted tools to
  check (exactly like `maops-py tools inspect git docker` can); it can
  never supply an argv, a flag, or a different executable.

## No recursive `maops-py` subprocess

`workflow run` never shells out to a second `maops-py` process. Every
step is executed by calling the real, in-process Python function the
equivalent CLI subcommand itself calls
(`commands/doctor.py:build_report()`, `commands/tools.py:
build_inspect_report()`, `commands/inventory.py:build_system_report()`/
`build_filesystem_report()`, `commands/logs.py:
build_log_analysis_report()`, `commands/health.py:
build_health_http_report()`/`build_health_tcp_report()`) from
`core/workflow_runner.py` — the one module in `core/` permitted to
import from `commands/`, since its entire purpose is to orchestrate
across those other commands' own orchestration functions.

## No general automation primitives

None of the following exist anywhere in the workflow schema or
implementation, in this release or as a partial/hidden capability:

- **Loops or repetition** — a step runs exactly once per workflow run.
- **Conditionals** — every declared step always runs; there is no
  "run step B only if step A passed" branching.
- **Variables, templating, or field interpolation** — every field value
  is used exactly as written; there is no `{{ }}`/`${ }` substitution of
  any kind, from the environment, from an earlier step's output, or
  otherwise.
- **Cron scheduling or a daemon mode** — `workflow run` executes once,
  synchronously, and exits. There is no built-in scheduler in this
  release (see `docs/workflows.md`'s closing section); run it from an
  external scheduler if recurring execution is needed.
- **Plugins or user-defined step kinds** — `WorkflowStepKind` is a fixed
  `StrEnum`; there is no registration mechanism, entry-point discovery,
  or dynamic-loading path that could add a new step kind at runtime.
- **SSH, remote execution, or any other host-reaching mechanism** beyond
  the two already-existing, narrowly scoped network-capable modules
  (`health_http`/`health_tcp` steps — see below).
- **Arbitrary glob expansion.** No workflow field expands a shell glob;
  `inventory_filesystem`'s `path` is a single literal path (or a single
  lexical join against the workflow file's directory), never a pattern.

## Network access stays scoped to `health_http`/`health_tcp` steps

The only two workflow step kinds that can make a network connection are
`health_http` and `health_tcp` — because they call
`commands/health.py:build_health_http_report()`/
`build_health_tcp_report()`, the exact same functions
`maops-py health http`/`health tcp` call, which in turn are the only
code paths in this entire package permitted to import
`socket`/`ssl`/`http.client` (`core/health_http.py`, `core/health_tcp.py`)
or `concurrent.futures` (`core/health_runner.py`). Every other step kind
(`doctor`, `tools_inspect`, `inventory_system`, `inventory_filesystem`,
`logs_analyze`) inherits the exact same "no network" invariant its
equivalent CLI subcommand already has, unchanged.

`health_http`/`health_tcp` workflow steps carry forward every existing
safety property of `health http`/`health tcp` unmodified: HTTPS always
validates certificates and hostnames (no `--insecure` equivalent), no
request bodies, no response-body/header retention, redirects never
followed, TCP checks are connect-only, and `urls`/`targets` are validated
with the real `validate_http_target()`/`validate_tcp_target()` functions
— see `docs/http-health-safety.md` for the complete network safety
model, which applies to a workflow step exactly as it applies to the
standalone CLI command.

## `workflow validate` performs no operations at all

`workflow validate` calls only `core/workflow_parser.py`'s
`parse_workflow_file()`/`validate_workflow_document()` — pure parsing and
type/range checking, with no side effects. It specifically never:

- Opens a network connection (even to validate that a `health_http`
  target is reachable — `validate_http_target()`/`validate_tcp_target()`
  check only syntax and semantics, exactly as they do for the standalone
  `health http`/`health tcp` commands).
- Executes a subprocess or resolves a tool executable via
  `shutil.which()`.
- Opens, reads, or otherwise accesses the content of any path referenced
  by an `inventory_filesystem`/`logs_analyze` step — only the *string*
  value of `path` is validated (type-checked; existence is never
  probed).
- Mutates the process's current working directory, environment, or any
  filesystem state.

This is enforced by a dedicated regression test suite
(`tests/unit/test_workflow_no_network_no_subprocess.py`), which validates
a workflow file declaring every network- and subprocess-capable step kind
with `socket.socket`/`socket.create_connection`/`subprocess.Popen` all
monkeypatched to raise if called — validation of that file must still
succeed without ever invoking any of them.

## Relative path resolution

`inventory_filesystem`'s and `logs_analyze`'s `path` fields resolve
against the workflow TOML file's own directory (a pure lexical
`os.path.abspath()`-style join — never `Path.resolve()`, which would
silently walk through symlink components, and never a filesystem access
of any kind to compute), not the process's actual working directory. The
process's cwd is never read via a mechanism other than this lexical join,
and `os.chdir()` is never called anywhere in this package. See
`docs/workflows.md`'s "Relative path semantics" section for examples.

## Input bounds

- Maximum `32` steps per workflow file, checked before any step is
  parsed further, let alone executed.
- `health_http`/`health_tcp` steps: `1`-`100` targets (the existing
  `health http`/`health tcp` bound).
- Every other per-step numeric field is bounded identically to its CLI
  flag equivalent (see `docs/workflows.md`'s step-kind table).
- Unknown top-level and per-step TOML keys are always rejected — a
  typo or an attempt to add an unsupported field never fails open.

## What `workflow` does **not** claim to do

This is not a general-purpose automation, orchestration, or CI/CD engine.
It does not replace `make`, a shell script, or a CI pipeline definition
for tasks outside the seven fixed step kinds above. If a task needs
anything this document lists as absent — a shell command, a loop, a
condition, a schedule — `maops-py workflow` is not the right tool for it
in this release.
