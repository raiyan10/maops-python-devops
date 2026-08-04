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

Day 1 / v0.1.0 delivered the packaging, CLI, and diagnostics foundation.
Day 2 / v0.2.0 adds typed configuration management and a reusable, safe
subprocess execution layer, demonstrated through an allowlisted,
read-only tool-inspection command:

- A `src`-layout, stdlib-only Python package (`maops_pydevops`) —
  `tomllib` (standard library since Python 3.11) is the only addition,
  and it is still zero third-party runtime dependencies.
- A console script (`maops-py`) and an equivalent `python -m
  maops_pydevops` invocation.
- `doctor`, covering required environment checks and optional
  DevOps-tool presence checks.
- `config path` / `config init` / `config validate` / `config show` —
  typed TOML configuration with CLI/environment/file/default precedence
  and secure, atomic file management.
- `tools inspect` — allowlisted, read-only version checks for `git`,
  `docker`, `kubectl`, `terraform`, and `ansible`, executed through a
  safe subprocess layer (`shell=False`, fixed argv, timeout, output
  truncation). See [docs/subprocess-safety.md](docs/subprocess-safety.md)
  for the full safety boundary — Day 2 does not expose an arbitrary
  command-execution CLI.
- A full local quality gate (formatting, linting, strict typing, tests,
  coverage, build, isolated smoke-install) and a matching CI workflow.

See [docs/configuration.md](docs/configuration.md) for the complete
configuration reference, and [Roadmap](#roadmap) for what's next.

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
zero — `maops-py` uses only the Python standard library, including
`tomllib` for configuration parsing.

## CLI examples

```bash
maops-py --help
maops-py -h
maops-py --version
maops-py version
maops-py doctor
maops-py doctor --format text
maops-py doctor --format json

maops-py config path
maops-py config init
maops-py config init --force
maops-py config validate
maops-py config show --format json

maops-py tools inspect
maops-py tools inspect git
maops-py tools inspect git kubectl --format json

# Equivalent module invocation
python -m maops_pydevops --version
python -m maops_pydevops doctor --format json
python -m maops_pydevops config show --format json
```

Exit codes: `0` success, `1` operational or required-check failure, `2`
CLI usage error (unknown command, invalid option value, no subcommand).
`--version` always short-circuits, even alongside a subcommand — e.g.
`maops-py --version doctor` prints only the version and exits `0`.

### Doctor: text output

```
$ maops-py doctor
MAOps Python DevOps Toolkit - Doctor Report
Version:              0.2.0
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
  "version": "0.2.0",
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

### Configuration: init and show

```bash
$ maops-py config path
/home/user/.config/maops-py/config.toml

$ maops-py config init
created configuration file at /home/user/.config/maops-py/config.toml

$ maops-py config show --format json | python -m json.tool
```

```json
{
    "path": "/home/user/.config/maops-py/config.toml",
    "exists": true,
    "valid": true,
    "values": {
        "output_format": "text",
        "command_timeout_seconds": 10.0,
        "max_output_bytes": 65536
    },
    "sources": {
        "output_format": "default",
        "command_timeout_seconds": "default",
        "max_output_bytes": "default"
    }
}
```

A freshly initialized file changes nothing — every value is still
`"default"` until you uncomment a line in the generated template. See
[docs/configuration.md](docs/configuration.md) for the full precedence
model and every supported key.

### Tool inspection: text and JSON output

```bash
$ maops-py tools inspect git kubectl
MAOps Python DevOps Toolkit - Tool Inspection
Version:     0.2.0
Config path: /home/user/.config/maops-py/config.toml

Tools:
  [PASS] git                  git executable found at /usr/bin/git; exited 0.
  [WARN] kubectl              kubectl not found on PATH.

Overall status: WARN
```

```bash
$ maops-py tools inspect git --format json | python -m json.tool
```

```json
{
    "version": "0.2.0",
    "configuration": {
        "path": "/home/user/.config/maops-py/config.toml",
        "command_timeout_seconds": 10.0,
        "max_output_bytes": 65536
    },
    "tools": [
        {
            "name": "git",
            "executable": "/usr/bin/git",
            "status": "pass",
            "exit_code": 0,
            "timed_out": false,
            "duration_ms": 2,
            "stdout": "git version 2.43.0\n",
            "stderr": "",
            "stdout_truncated": false,
            "stderr_truncated": false,
            "detail": "git executable found at /usr/bin/git; exited 0."
        }
    ],
    "overall": "pass"
}
```

Only `git`, `docker`, `kubectl`, `terraform`, and `ansible` can ever be
inspected, and only via a fixed, read-only version-check argv per tool —
`maops-py` does not expose a general command-execution CLI. See
[docs/subprocess-safety.md](docs/subprocess-safety.md) for the complete
safety boundary.

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
        config.py             # config CLI orchestration
        tools.py                # allowlisted tool inspection
    core/
        models.py             # enums + frozen dataclasses (doctor, tools)
        config_models.py         # config-domain enums + frozen dataclasses
        output.py                  # text/JSON rendering
        platform.py                  # injectable platform/python inspection
        config.py                      # config path/parse/validate/init
        runner.py                        # safe subprocess execution layer
tests/
    unit/
    integration/
docs/
    architecture.md
    best-practices.md
    configuration.md
    subprocess-safety.md
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

See [docs/roadmap.md](docs/roadmap.md) for what's implemented in v0.2.0
and what's under consideration for future releases.

## License

MIT — see [LICENSE](LICENSE).
