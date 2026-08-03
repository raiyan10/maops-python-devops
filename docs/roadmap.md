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

## Post-v0.1.0 possibilities

These are not committed, scheduled, or designed yet — listed only as
plausible next steps, to be scoped on their own day:

- Additional read-only diagnostic or reporting commands beyond `doctor`.
- Structured logging/verbosity flags (`-v`/`-q`) for the CLI.
- A configuration file for customizing which optional tools `doctor`
  checks for.
- Packaging distribution (PyPI publish workflow) once the CLI surface is
  stable enough to version externally.
