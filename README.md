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
Day 2 / v0.2.0 added typed configuration management and a reusable, safe
subprocess execution layer, demonstrated through an allowlisted,
read-only tool-inspection command. Day 3 / v0.3.0 adds typed, structured,
read-only system and filesystem inventory:

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
- `inventory system` / `inventory filesystem` — typed host/OS/CPU/
  memory/uptime facts and a bounded, deterministic filesystem tree
  summary, collected via pure `platform`/`os` introspection with no
  subprocess or network/socket use. See
  [docs/inventory.md](docs/inventory.md) and
  [docs/filesystem-inventory-safety.md](docs/filesystem-inventory-safety.md)
  for the complete field and safety contracts.
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

maops-py inventory system
maops-py inventory system --format json
maops-py inventory filesystem
maops-py inventory filesystem .
maops-py inventory filesystem . --max-depth 1 --top 5 --format json

# Equivalent module invocation
python -m maops_pydevops --version
python -m maops_pydevops doctor --format json
python -m maops_pydevops config show --format json
python -m maops_pydevops inventory system --format json
```

Exit codes: `0` success, `1` operational or required-check failure, `2`
CLI usage error (unknown command, invalid option value, no subcommand).
`--version` short-circuits whenever argument parsing itself succeeds —
e.g. `maops-py --version doctor` prints only the version and exits `0` —
but **not** for an incomplete two-level group given with no leaf
subcommand: `maops-py --version tools` still exits `2`, since argparse's
own required-subcommand validation runs before `--version` is ever
inspected. Which `warn`-level conditions affect the exit code also
differs by command (`doctor`'s optional-tool warnings never do,
`tools inspect`'s do, `inventory`'s never do) — see
[docs/subprocess-safety.md](docs/subprocess-safety.md) for the complete
breakdown.

### Doctor: text output

```
$ maops-py doctor
MAOps Python DevOps Toolkit - Doctor Report
Version:              0.3.0
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
  "version": "0.3.0",
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
Version:     0.3.0
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
    "version": "0.3.0",
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

### Inventory: system

```bash
$ maops-py inventory system
MAOps Python DevOps Toolkit - System Inventory
Version:               0.3.0
Hostname:              myhost
OS:                    Linux 6.8.0
OS version:            #1 SMP ...
Machine:               x86_64
Distribution:          Ubuntu 24.04
Python:                3.12.3 (CPython)
Python executable:     /home/user/.venv/bin/python
CPU logical count:     8
Load average (1/5/15): 0.12 0.08 0.04
Memory used:           50.0% of 17179869184 bytes
Uptime:                12345.67s

Issues:

Overall status: PASS
```

```bash
$ maops-py inventory system --format json | python -m json.tool
```

```json
{
    "version": "0.3.0",
    "host": {
        "hostname": "myhost",
        "os_family": "Linux",
        "os_release": "6.8.0",
        "os_version": "#1 SMP ...",
        "machine": "x86_64"
    },
    "distribution": {
        "id": "ubuntu",
        "name": "Ubuntu",
        "version_id": "24.04",
        "available": true
    },
    "python": {
        "version": "3.12.3",
        "implementation": "CPython",
        "executable": "/home/user/.venv/bin/python"
    },
    "cpu": {
        "logical_count": 8,
        "load_average_1m": 0.12,
        "load_average_5m": 0.08,
        "load_average_15m": 0.04
    },
    "memory": {
        "available": true,
        "total_bytes": 17179869184,
        "available_bytes": 8589934592,
        "used_bytes": 8589934592,
        "used_percent": 50.0
    },
    "uptime": {
        "available": true,
        "seconds": 12345.67
    },
    "issues": [],
    "overall": "pass"
}
```

Optional fields that could not be collected (e.g. `distribution` on a
non-Linux host) become explicit JSON `null` plus a warning entry in
`issues` — never fabricated data. This command always exits `0` for a
successfully-produced report, regardless of `overall` being `pass` or
`warn`. See [docs/inventory.md](docs/inventory.md) for the complete field
reference.

### Inventory: filesystem

```bash
$ maops-py inventory filesystem . --max-depth 1 --top 5
MAOps Python DevOps Toolkit - Filesystem Inventory
Version:            0.3.0
Root:               /home/user/project
Max depth:          1
Max entries:        10000
Scanned entries:    12
Directories:        3
Files:              9
Symlinks:           0
Other:              0
Total file bytes:   45210
Skipped entries:    0
Inaccessible:       0
Different fs:       0
Max depth reached:  true
Truncated:          false

Largest files:
         10615  CHANGELOG.md
          9910  README.md
          2898  Makefile

Issues:

Overall status: PASS
```

```bash
$ maops-py inventory filesystem . --max-depth 1 --top 5 --format json | python -m json.tool
```

```json
{
    "version": "0.3.0",
    "root": "/home/user/project",
    "options": {
        "max_depth": 1,
        "max_entries": 10000,
        "top": 5,
        "follow_symlinks": false,
        "same_filesystem": true
    },
    "summary": {
        "scanned_entries": 12,
        "directories": 3,
        "files": 9,
        "symlinks": 0,
        "other": 0,
        "total_file_bytes": 45210,
        "skipped_entries": 0,
        "inaccessible_entries": 0,
        "different_filesystem_entries": 0
    },
    "largest_files": [
        {"path": "/home/user/project/CHANGELOG.md", "relative_path": "CHANGELOG.md", "size_bytes": 10615, "modified_ns": 1785900000000000000}
    ],
    "issues": [],
    "max_depth_reached": true,
    "truncated": false,
    "overall": "pass"
}
```

Never follows symbolic links, never crosses mount points, never reads
file content or computes a hash — see
[docs/filesystem-inventory-safety.md](docs/filesystem-inventory-safety.md)
for the complete safety boundary. Only a root path that cannot be
classified at all (nonexistent or inaccessible) causes a non-zero exit;
recoverable per-entry issues during traversal never do.

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
        inventory.py              # inventory CLI orchestration
    core/
        models.py             # enums + frozen dataclasses (doctor, tools)
        config_models.py         # config-domain enums + frozen dataclasses
        inventory_models.py        # inventory-domain enums + frozen dataclasses
        output.py                    # text/JSON rendering
        platform.py                    # injectable platform/python inspection
        config.py                        # config path/parse/validate/init
        runner.py                          # safe subprocess execution layer
        system_inventory.py                  # injectable host/OS/CPU/memory/uptime collection
        filesystem_inventory.py                # bounded, deterministic filesystem scanner
tests/
    unit/
    integration/
docs/
    architecture.md
    best-practices.md
    configuration.md
    subprocess-safety.md
    inventory.md
    filesystem-inventory-safety.md
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

See [docs/roadmap.md](docs/roadmap.md) for what's implemented in v0.3.0
and what's under consideration for future releases.

## License

MIT — see [LICENSE](LICENSE).
