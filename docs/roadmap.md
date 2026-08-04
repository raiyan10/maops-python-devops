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

## Post-v0.2.0 possibilities

These are not committed, scheduled, or designed yet — listed only as
plausible next steps, to be scoped on their own day:

- Additional read-only diagnostic or reporting commands beyond `doctor`
  and `tools inspect`.
- Structured logging/verbosity flags (`-v`/`-q`) for the CLI.
- Configuration support for customizing which optional tools `doctor`
  checks for.
- Packaging distribution (PyPI publish workflow) once the CLI surface is
  stable enough to version externally.
