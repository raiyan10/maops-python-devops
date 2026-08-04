# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-04

Adds typed configuration management and a reusable, safe subprocess execution
layer, demonstrated through an allowlisted, read-only tool-inspection
command. The toolkit remains standard-library-only at runtime.

### Added

- TOML configuration support (`tomllib`, stdlib) with a default path of
  `$XDG_CONFIG_HOME/maops-py/config.toml`, falling back to
  `$HOME/.config/maops-py/config.toml`, overridable via
  `MAOPS_PY_CONFIG_FILE`. Supported keys: `output_format`,
  `command_timeout_seconds`, `max_output_bytes`, with strict schema
  validation (unknown keys, malformed TOML, duplicate keys, and
  bool-as-numeric values are all rejected).
- `maops-py config path` / `config init [--force]` / `config validate
  [PATH]` / `config show [--format text|json]` — secure, atomic
  configuration file management (mode `0600`, symlink/directory refusal,
  `os.replace`-based atomic installation) and effective-configuration
  introspection with full source attribution (`cli` / `environment` /
  `file` / `default`).
- Typed CLI/environment/file/default configuration precedence resolution,
  with invalid environment values failing operationally rather than
  silently falling back to a lower-precedence source.
- `src/maops_pydevops/core/runner.py` — a reusable, safe subprocess
  execution layer (`shell=False`, `stdin=DEVNULL`, separate stdout/stderr
  capture, configurable timeout, monotonic-clock duration, UTF-8-with-
  replacement decoding, byte-based output truncation, fixed noninteractive
  child environment). No arbitrary command-execution CLI is exposed.
- `maops-py tools inspect [TOOL...] [--format text|json] [--timeout
  SECONDS]` — allowlisted, read-only version checks for `git`, `docker`,
  `kubectl`, `terraform`, and `ansible`, using fixed argv definitions
  executed via the safe runner.
- New documentation: `docs/configuration.md`, `docs/subprocess-safety.md`.

### Changed

- `--version` now always short-circuits, even when a subcommand is also
  supplied (e.g. `maops-py --version doctor` prints only the version and
  exits `0`; `doctor` never runs). Previously `--version` was silently
  ignored once a subcommand was present. `maops-py doctor --version`
  remains an unrecognized-argument usage error (exit `2`), unchanged.

### Fixed

- `maops-py tools inspect` with no explicit tool names (and thus no
  positional arguments at all) raised `argparse.ArgumentError: invalid
  choice: []` under Python 3.11's argparse, while working correctly under
  3.12 — a version-dependent interaction between `nargs="*"`, `choices=`,
  and an implicitly-`None` default on a required-by-default positional.
  Tool-name validation is now performed explicitly in
  `run_tools_inspect()` instead of via argparse `choices=`, which sidesteps
  the cross-version inconsistency entirely; unsupported tool names still
  exit `2` with a clear error message.

## [0.1.0] - 2026-08-03

Initial release of the MAOps Python DevOps Automation Toolkit. Establishes
the packaging, CLI, and diagnostics foundation for Project 2 of the MAOps
DevOps portfolio.

### Added

- `src`-layout package `maops_pydevops`, installable with `pip install -e ".[dev]"`,
  targeting Python 3.11+, with a CI matrix configured to validate 3.11,
  3.12, 3.13, and 3.14 on every push (locally exercised on 3.12 so far;
  see the CI workflow run history for actual multi-version results).
- Console script `maops-py`, with `python -m maops_pydevops` invoking the
  identical CLI through a single shared entry point.
- `maops-py doctor` — a read-only, network-free environment diagnostic
  command with `text` (default) and `json` output formats, covering
  supported Python version, package import, supported OS family,
  temporary-directory availability, filesystem encoding, and Python
  executable resolution as required checks, and git/docker/kubectl/
  terraform/ansible presence as optional (warn-only) checks.
- `maops-py version` / `maops-py --version` for toolkit version reporting,
  backed by a single authoritative version source in `pyproject.toml`.
- Exit-code convention: `0` success, `1` operational/required-check
  failure, `2` CLI usage error.
- Typed, immutable core models (`CheckStatus`, `OutputFormat`,
  `PythonInfo`, `PlatformInfo`, `DoctorCheck`, `DoctorReport`) with
  explicit serialization.
- Full local quality gate via `Makefile` (`format`, `lint`, `type-check`,
  `test`, `coverage`, `build`, `smoke-install`, `quality`,
  `release-check`).
- GitHub Actions workflow `Python Validation`, running `make
  release-check` across the full Python support matrix with pinned,
  read-only-permission Actions.
