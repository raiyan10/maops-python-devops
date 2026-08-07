# Roadmap

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

## Post-v0.4.0 possibilities

These are not committed, scheduled, or designed yet — listed only as
plausible next steps, to be scoped on their own day:

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
