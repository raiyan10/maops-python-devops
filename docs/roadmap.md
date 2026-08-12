# Roadmap

**v0.7.0 is the final planned release in this project's seven-day
portfolio arc.** The planned seven-day implementation (v0.1.0 through
v0.7.0) is complete; no further feature work is scheduled. Everything
below "Completed in v0.7.0" is an idea that was deliberately scoped out,
not a commitment to future work — see that section's own framing.

## Completed in v0.1.0

- `src`-layout package `maops_pydevops`, Python 3.11+, with a CI matrix
  configured for 3.11, 3.12, 3.13, and 3.14 (locally exercised on 3.12 so
  far — full-matrix validation depends on the workflow's actual run
  history).
- Console script `maops-py` and equivalent `python -m maops_pydevops`
  invocation, both calling one shared `cli.main()`.
- `maops-py doctor` (text and JSON output) — six required environment
  checks and five optional DevOps-tool presence checks.
- `maops-py version` / `maops-py --version`.
- Exit-code convention (0 success / 1 operational failure / 2 usage
  error), enforced across every documented command path.
- Typed, immutable core models with explicit serialization.
- Local quality gate (`make quality`, `make build`, `make smoke-install`,
  `make release-check`) and a matching `Python Validation` GitHub Actions
  workflow with SHA-pinned actions.
- Test suite with unit and integration coverage at or above 90%.

## Completed in v0.2.0

- Typed TOML configuration (`tomllib`, stdlib), with a default path of
  `$XDG_CONFIG_HOME/maops-py/config.toml` falling back to
  `$HOME/.config/maops-py/config.toml`, overridable via
  `MAOPS_PY_CONFIG_FILE`, and CLI/environment/file/default precedence
  resolution with full per-field source attribution.
- `maops-py config path` / `config init [--force]` / `config validate
  [PATH]` / `config show [--format text|json]` — secure, atomic
  configuration management (mode `0600`, symlink/directory refusal,
  `os.replace`-based atomic installation).
- `src/maops_pydevops/core/runner.py` — a reusable, safe subprocess
  execution layer (`shell=False`, fixed noninteractive child environment,
  configurable timeout, output truncation). Not exposed as an arbitrary
  command-execution CLI.
- `maops-py tools inspect [TOOL...] [--format text|json] [--timeout
  SECONDS]` — allowlisted, read-only version checks for `git`, `docker`,
  `kubectl`, `terraform`, and `ansible`.
- `--version` now always short-circuits, even alongside a subcommand,
  resolving the Day 1 `--version doctor` precedence quirk.

Not yet done: `doctor` itself does not read configuration to filter which
optional tools it checks — the configuration system introduced in v0.2.0
is deliberately scoped to `command_timeout_seconds`, `max_output_bytes`,
and `output_format` only.

## Completed in v0.3.0

- `maops-py inventory system [--format text|json]` — typed, structured
  host/OS/distribution/Python/CPU/memory/uptime facts, collected via pure
  `platform`/`os` introspection (no subprocess, no network/socket use).
  Optional fields degrade to explicit `null` plus a structured warning
  issue rather than being fabricated or omitted; the exit code is
  deliberately decoupled from that degradation (see
  `docs/subprocess-safety.md`).
- `maops-py inventory filesystem [PATH] [--format text|json] [--max-depth
  N] [--max-entries N] [--top N]` — a bounded, deterministic, read-only
  filesystem tree summary. Never follows symbolic links, never crosses
  mount points, never reads file content or computes a hash (see
  `docs/filesystem-inventory-safety.md`).
- Several Day 2 engineering-review findings resolved: an isolated,
  race-free build step for the release-artifact test suite; exhaustive
  JSON field-type coverage for every report type; type-aware
  configuration validation error messages; a `MANIFEST.in` that removes
  the sdist egg-info leak down to the one file setuptools' own
  sdist/egg_info integration force-includes unconditionally; and
  documented (not structurally changed) `--version` short-circuit and
  cross-command exit-code semantics.

## Completed in v0.4.0

- `maops-py logs parse PATH [--input-format auto|jsonl|syslog] [--format
  text|json] [--max-lines N] [--max-bytes N] [--max-line-bytes N]
  [--max-events N] [--no-redact]` — bounded, typed parsing of JSONL and
  syslog log files via a first-of-its-kind fd-safe reader
  (`core/log_reader.py`: `O_NOFOLLOW`/`O_CLOEXEC`/`O_NOATIME`,
  `os.fstat()` TOCTOU verification, bounded sequential reads, never
  `mmap`, never a whole-file read). Default secret redaction on the
  `message` field, disableable via `--no-redact`. See
  `docs/log-parsing.md` and `docs/log-redaction.md`.
- `maops-py logs analyze PATH [--input-format ...] [--format ...] [--top
  N] [--bucket-seconds N] [--repeat-threshold N] [--error-threshold N]
  [--no-redact]` — streaming, bounded-memory operational analysis
  (severity/source counts, normalized message signatures, epoch-integer
  time buckets, deterministic threshold findings). Individual events are
  never retained; deterministic parsing and aggregation only — no
  machine learning, artificial intelligence, behavioral detection, or
  general anomaly-detection claim. See `docs/log-analysis.md`.
- Still zero third-party runtime dependencies: `re`/`datetime` (both
  standard library) are the only additions.

## Completed in v0.5.0

- `maops-py health http URL [URL ...] [--method GET|HEAD] [--expect-status
  STATUS|STATUS-STATUS] [--timeout SECONDS] [--retries N] [--retry-delay
  SECONDS] [--workers N] [--format text|json]` — bounded HTTP availability
  checks via `http.client` (never `urllib.request`), with mandatory TLS
  certificate/hostname verification and no `--insecure` option, no
  request bodies, no response-body/header retention, and redirects never
  followed. See `docs/health-checks.md` and `docs/http-health-safety.md`.
- `maops-py health tcp TARGET [TARGET ...] [--timeout SECONDS] [--retries
  N] [--retry-delay SECONDS] [--workers N] [--format text|json]` —
  bounded, connect-only TCP checks (`hostname:port`, `IPv4:port`,
  `[IPv6]:port`); no application data sent, no banner read, no TLS
  handshake for a generic TCP target.
- The package's first intentional network access, deliberately isolated
  to `core/health_http.py`/`core/health_tcp.py` (the only two modules
  permitted to import `socket`/`ssl`/`http.client`) and
  `core/health_runner.py` (the only module permitted to import
  `concurrent.futures`) — every other command's existing network
  prohibition is unchanged and regression-tested.
- Deterministic per-target retry policy (`attempts = retries + 1`, fixed
  non-jittered delay) and bounded `ThreadPoolExecutor` concurrency (1-32
  workers, 1-100 targets), with report ordering that always matches
  original CLI target order regardless of completion order.
- Ten Day 4 carry-forward findings resolved: quoted-secret whitespace
  leak in redaction, byte-limit mid-line truncation fragment handling,
  smoke-install secret-absence assertions, RFC 3339 lowercase `z`
  handling, signature decimal/hex misclassification, PID magnitude
  bounds, `logs parse` text-output hostname rendering, a stale example
  version in `docs/inventory.md`, and several test-quality cleanups.
- Still zero third-party runtime dependencies: `http.client`, `ssl`,
  `socket`, `ipaddress`, `concurrent.futures`, and `urllib.parse` are all
  standard library.

## Completed in v0.6.0

- `maops-py report aggregate REPORT [REPORT ...] [--format
  text|json|markdown] [--output PATH] [--force]` — reads one or more
  `maops-py` JSON report files and produces a single, normalized summary.
  Report kind is detected purely structurally (a fixed, unique key
  combination per one of eight supported kinds) — never heuristically.
  Each detected report is normalized into a small, explicitly typed
  summary; the full input document is never blindly embedded. Bounded
  (max 50 files, 5 MiB each by default) and fd-safety-hardened the same
  way `core/log_reader.py` reads log content. See
  `docs/aggregated-reports.md`.
- `maops-py workflow validate FILE [--format text|json]` / `maops-py
  workflow run FILE [--format text|json|markdown] [--output PATH]
  [--force]` — declarative TOML automation workflows (`schema_version =
  1`, max 32 `[[steps]]`) over seven step kinds (`doctor`,
  `tools_inspect`, `inventory_system`, `inventory_filesystem`,
  `logs_analyze`, `health_http`, `health_tcp`), each executed through the
  package's own real internal APIs — never a shell command, never a
  recursive `maops-py` subprocess, never `eval`/`exec`, loops,
  conditions, templating, or scheduling. `workflow validate` performs no
  execution, network, or subprocess activity at all. Steps always
  execute sequentially in declared order; a failed step never discards
  already-completed results. Relative `inventory_filesystem`/
  `logs_analyze` paths resolve against the workflow file's own directory,
  never the process cwd (which is never mutated). See `docs/workflows.md`
  and `docs/workflow-security.md`.
- New typed models in `core/report_models.py` and `core/workflow_models.py`,
  following the existing frozen-dataclass, explicit-serialization
  conventions; `core/workflow_runner.py` reuses
  `core/report_aggregate.py`'s normalization directly on each workflow
  step's own real report, so a step's summary and an aggregated report's
  summary for the same underlying command share one code path.
- Nine Day 5 carry-forward findings resolved: Unicode bidi-override/
  zero-width formatting-character text sanitization, TCP-only
  `overall: "warn"` orchestration test coverage, strengthened health JSON
  field-type assertions, a loopback test proving the original HTTP query
  value reaches the server while the report shows only the redacted form,
  a deterministic TCP reversed-completion-order integration test, health
  report-builder `MIN_TARGETS` boundary coverage, a regression test
  proving the health smoke check is wired into `make smoke-install`, a
  CHANGELOG note documenting that smoke-install exercises real loopback
  network I/O, and stale `0.4.0` example versions in
  `docs/log-parsing.md`/`docs/log-analysis.md`.
- Still zero third-party runtime dependencies: every new module uses only
  `tomllib`, `os`, `stat`, `errno`, `json`, `tempfile`, `contextlib`, and
  `pathlib` — all already-used standard library.

## Completed in v0.7.0

Final hardening and portfolio-readiness release — no new commands, no
new network-capable subsystem, no new runtime dependency.

- Closed the Medium/Low findings deliberately deferred from the Day 6
  release-readiness follow-up: bidi/zero-width Unicode sanitization
  regression coverage across all applicable text/Markdown renderer
  combinations (not only the one previously tested), an expanded
  workflow no-network/no-subprocess architectural boundary covering
  `commands/workflow.py`, `core/workflow_models.py`,
  `core/workflow_parser.py`, and `core/workflow_runner.py` (plus a
  dynamic no-subprocess-during-execution proof using the real
  `build_doctor_report()`), stale `0.5.0`/`0.6.0` example versions
  corrected in `README.md`/`docs/inventory.md`/`docs/health-checks.md`/
  `docs/log-analysis.md`/`docs/log-parsing.md`/`docs/workflows.md`, a
  documentation-version-drift regression test
  (`tests/unit/test_version.py`), documented Markdown escaping
  rationale, production-boundary tests against the real
  `MAX_REPORT_COUNT`/`MAX_REPORT_FILE_BYTES` constants, explicit
  shell-metacharacter-inertness regression tests, and a workflow-layer
  health HTTP query-privacy integration test against a real ephemeral
  loopback server.
- A final security audit across the complete source tree confirmed no
  `shell=True`, `os.system`, `eval`, `exec`, `pickle`, unbounded
  concurrency, or unrestricted network behavior, and no new mutable
  global state or import-time side effect.
- New portfolio-facing documentation: [SECURITY.md](../SECURITY.md),
  [docs/release-process.md](release-process.md), and
  [docs/portfolio-guide.md](portfolio-guide.md).
- [docs/architecture.md](architecture.md) rewritten to represent the
  complete Day 1-7 architecture (Mermaid system-overview and packaging/
  release-boundary diagrams added); [README.md](../README.md)
  reorganized as the final portfolio landing page.
- Still zero third-party runtime dependencies — no new module or
  standard-library addition beyond what v0.6.0 already used.

## Optional future enhancements

These are not committed, scheduled, or designed — listed only as
plausible ideas that were deliberately scoped out of the completed
seven-day arc, not a roadmap for future work:

- Structured logging/verbosity flags (`-v`/`-q`) for the CLI.
- Configuration support for customizing which optional tools `doctor`
  checks for.
- Packaging distribution (PyPI publish workflow) once the CLI surface is
  stable enough to version externally.
- A `--follow-symlinks`/`--cross-filesystem` opt-in flag for `inventory
  filesystem`, should a real use case for it emerge — the current release
  deliberately hardcodes both to their safest values with no CLI
  override.
- Multiline/stack-trace continuation support for `logs parse`/`logs
  analyze`, should a real use case for it emerge — Day 4 deliberately
  parses each physical line independently, with no CLI override.
- A configurable additional secret-pattern list for `logs`' redaction
  pass, beyond the fixed set Day 4 ships with.
- Comma-separated `--expect-status` lists for `health http`, should a
  real use case for it emerge — Day 5 deliberately supports exactly one
  value or one range, with no CLI override.
- Custom request headers or authentication for `health http`, should a
  real use case for it emerge — Day 5 deliberately ships neither. TLS
  certificate/hostname verification staying mandatory, with no bypass
  option, is a deliberate safety invariant of this feature, not merely a
  Day 5 scoping gap.
- A scheduler or cron integration for `workflow run`, should a real use
  case for it emerge — Day 6 deliberately ships a synchronous,
  run-once-per-invocation command only; see
  `docs/workflow-security.md`'s closing section for why this is a
  deliberate scoping decision, not an oversight.
- Conditional or looping workflow steps, and inter-step variable
  substitution, should a real use case for them emerge — Day 6
  deliberately ships a fixed, sequential, always-run-every-step model
  with no templating of any kind. Adding either would materially change
  the "declarative data, never executable code" safety property
  `docs/workflow-security.md` establishes, so it would need its own
  design and review, not an incremental extension.
- A user-defined or plugin-supplied workflow step kind, should a real use
  case for it emerge — Day 6 deliberately ships a fixed, closed
  seven-kind enum with no registration or dynamic-loading mechanism.
