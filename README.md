# MAOps Python DevOps Automation Toolkit

Python-based DevOps automation, structured diagnostics, and operational
reporting.

## Problem statement

Diagnosing whether a workstation or CI runner is actually ready to run
DevOps tooling — supported Python version, working package import, a
usable temp directory, and the presence of common CLI tools — usually
means running a handful of ad hoc shell commands and eyeballing the
output. `maops-py doctor` turns that into a single, read-only,
network-free command with both a human-readable and a machine-readable
(JSON) output, so the same check can be run by a person or wired into
automation.

## Scope

Day 1 / v0.1.0 delivers the packaging, CLI, and diagnostics foundation:

- A `src`-layout, stdlib-only Python package (`maops_pydevops`).
- A console script (`maops-py`) and an equivalent `python -m
  maops_pydevops` invocation.
- A single command, `doctor`, covering required environment checks and
  optional DevOps-tool presence checks.
- A full local quality gate (formatting, linting, strict typing, tests,
  coverage, build, isolated smoke-install) and a matching CI workflow.

Additional commands are future work — see [Roadmap](#roadmap).

## Project 1 vs. Project 2

This repository is **Project 2** of the MAOps DevOps portfolio. **Project
1** (`maops-linux-devops-toolkit`) is a Bash-based DevOps toolkit for
Linux hosts. Project 2 is a separate, from-scratch Python implementation:
it shares portfolio conventions (documentation shape, CI pinning policy,
review-agent structure) but no code, architecture, or runtime dependency
with Project 1.

## Installation

Use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

This installs the package in editable mode along with its development
dependencies (pytest, ruff, mypy, build). Runtime dependencies are
zero — v0.1.0 uses only the Python standard library.

## CLI examples

```bash
maops-py --help
maops-py -h
maops-py --version
maops-py version
maops-py doctor
maops-py doctor --format text
maops-py doctor --format json

# Equivalent module invocation
python -m maops_pydevops --version
python -m maops_pydevops doctor --format json
```

Exit codes: `0` success, `1` operational or required-check failure, `2`
CLI usage error (unknown command, invalid option value, no subcommand).

### Doctor: text output

```
$ maops-py doctor
MAOps Python DevOps Toolkit - Doctor Report
Version:              0.1.0
Python version:       3.12.3
Python executable:    /home/user/.venv/bin/python
Operating system:     Linux 6.8.0
Architecture:         x86_64
Filesystem encoding:  utf-8

Required checks:
  [PASS] python_version       Python 3.12.3 detected; minimum supported is 3.11.
  [PASS] package_import       maops_pydevops imported successfully.
  [PASS] os_family            Operating system family 'Linux' detected.
  [PASS] temp_directory       Temporary directory available at /tmp.
  [PASS] filesystem_encoding  Filesystem encoding is utf-8.
  [PASS] python_executable    Python executable resolved at /home/user/.venv/bin/python.

Optional tools:
  [PASS] git                  git found at /usr/bin/git.
  [WARN] docker               docker not found on PATH.
  [WARN] kubectl              kubectl not found on PATH.
  [WARN] terraform            terraform not found on PATH.
  [WARN] ansible              ansible not found on PATH.

Overall status: PASS
```

### Doctor: JSON output

```bash
$ maops-py doctor --format json | python -m json.tool
```

```json
{
  "version": "0.1.0",
  "python": {
    "version": "3.12.3",
    "executable": "/home/user/.venv/bin/python",
    "supported": true
  },
  "platform": {
    "system": "Linux",
    "release": "6.8.0",
    "architecture": "x86_64",
    "filesystem_encoding": "utf-8"
  },
  "checks": [
    {
      "name": "python_version",
      "status": "pass",
      "required": true,
      "detail": "Python 3.12.3 detected; minimum supported is 3.11."
    },
    {
      "name": "git",
      "status": "pass",
      "required": false,
      "detail": "git found at /usr/bin/git."
    },
    {
      "name": "docker",
      "status": "warn",
      "required": false,
      "detail": "docker not found on PATH."
    }
  ],
  "overall": "pass"
}
```

(The real output includes all six required checks and all five optional
tool checks; abbreviated here for readability.)

## Quality commands

```bash
make quality          # format-check + lint + type-check + coverage
make build             # sdist + wheel
make smoke-install      # install the built wheel into an isolated venv and exercise the CLI
make release-check       # quality + build + smoke-install
```

Coverage is enforced at a minimum of 90% (`pytest-cov`,
`--cov-fail-under=90`). Run `make help` for the full target list.

## Repository structure

```
src/maops_pydevops/
    __init__.py
    __main__.py        # python -m maops_pydevops
    cli.py               # argparse construction + dispatch
    version.py            # authoritative version lookup
    commands/
        doctor.py           # required + optional checks
    core/
        models.py             # enums + frozen dataclasses
        output.py               # text/JSON rendering
        platform.py               # injectable platform/python inspection
tests/
    unit/
    integration/
docs/
    architecture.md
    best-practices.md
    roadmap.md
    troubleshooting.md
    engineering-reviews/
.github/workflows/
    python-validation.yml
.claude/
    CLAUDE.md
    agents/
    skills/
```

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for what's implemented in v0.1.0
and what's under consideration for future releases.

## License

MIT — see [LICENSE](LICENSE).
