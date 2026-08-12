# MAOps Python DevOps Automation Toolkit

A small, dependency-free Python CLI for structured, read-only DevOps
diagnostics, operational reporting, and declarative automation —
`maops-py`.

## Project summary

`maops-python-devops` is Project 2 of a two-project portfolio pair.
Project 1, `maops-linux-devops-toolkit`, solves a related problem in
Bash. This project is an independent, from-scratch Python implementation
sharing portfolio house style (documentation conventions, CI structure,
review process) but no code or architecture with Project 1. It was built
as seven scoped, tagged daily releases (v0.1.0 through v0.7.0), each
release-quality on its own — see
[docs/portfolio-guide.md](docs/portfolio-guide.md) for the full narrative
and [docs/roadmap.md](docs/roadmap.md) for the day-by-day breakdown.

## Why it exists

DevOps and platform teams routinely need small, trustworthy diagnostic
tools: "what does my environment look like," "is this endpoint up,"
"what does this log actually say happened," "did last night's checks all
pass." These tools are usually either shell scripts (fast to write, hard
to keep safe and typed as they grow) or heavyweight frameworks (safe, but
overkill for a diagnostics CLI). `maops-py` explores a third point: a
small, strictly typed, dependency-free Python CLI that treats its own
security boundaries — no shell, no arbitrary command execution, a
narrowly scoped network surface — as first-class design constraints from
day one, not retrofitted later.

## Key capabilities

- **`doctor`** — read-only environment diagnostics: required checks
  (Python version, package import, OS family, temp directory,
  filesystem encoding, executable resolution) and optional DevOps-tool
  presence checks, text or JSON output.
- **`config`** — typed TOML configuration (`path`/`init`/`validate`/
  `show`) with CLI > environment > file > default precedence and secure,
  atomic file management. See [docs/configuration.md](docs/configuration.md).
- **`tools inspect`** — allowlisted, read-only version checks for `git`,
  `docker`, `kubectl`, `terraform`, `ansible` through a safe subprocess
  layer (`shell=False`, fixed argv, timeout, output truncation) — never
  an arbitrary command-execution surface. See
  [docs/subprocess-safety.md](docs/subprocess-safety.md).
- **`inventory system` / `inventory filesystem`** — typed host/OS/CPU/
  memory/uptime facts and a bounded, deterministic filesystem tree
  summary, collected via pure `platform`/`os` introspection (no
  subprocess, no network). See [docs/inventory.md](docs/inventory.md).
- **`logs parse` / `logs analyze`** — a bounded, fd-safe log reader
  feeding deterministic JSONL/syslog parsing, default secret redaction,
  and streaming operational analysis (severity/source counts, message
  signatures, time-bucket peaks, threshold findings) — deterministic
  parsing only, no ML or behavioral-detection claim. See
  [docs/log-parsing.md](docs/log-parsing.md) and
  [docs/log-analysis.md](docs/log-analysis.md).
- **`health http` / `health tcp`** — bounded HTTP/TCP availability
  checks against explicitly supplied endpoints, mandatory TLS
  verification (no `--insecure` option), no response-body retention,
  redirects never followed — an availability checker, not a
  vulnerability scanner. See [docs/health-checks.md](docs/health-checks.md).
- **`report aggregate`** — normalizes one or more `maops-py` JSON reports
  (any of eight supported kinds, detected structurally) into one summary,
  with secure atomic `--output` export. See
  [docs/aggregated-reports.md](docs/aggregated-reports.md).
- **`workflow validate` / `workflow run`** — declarative TOML automation
  over a fixed set of seven step kinds, each executed through the
  package's own existing internal APIs — never a shell command, never a
  recursive `maops-py` subprocess. See [docs/workflows.md](docs/workflows.md).

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
maops-py doctor
```

```
$ maops-py doctor
MAOps Python DevOps Toolkit - Doctor Report
Version:              0.7.0
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

Overall status: PASS
```

`maops-py` and `python -m maops_pydevops` are equivalent — both call the
same `cli.main()`, so either invocation always behaves identically.

## Representative commands

```bash
maops-py --version
maops-py doctor --format json
maops-py config init
maops-py tools inspect git kubectl --format json
maops-py inventory system --format json
maops-py inventory filesystem . --max-depth 1 --top 5
maops-py logs parse app.log --format json
maops-py logs analyze app.log --top 5
maops-py health http https://example.com/health --format json
maops-py health tcp 127.0.0.1:3306
maops-py report aggregate doctor.json health.json --format markdown
maops-py workflow validate release.toml
maops-py workflow run release.toml --output report.json
```

Exit codes: `0` success, `1` operational or required-check failure, `2`
CLI usage error. What counts as a `1` varies meaningfully by command —
see [docs/subprocess-safety.md](docs/subprocess-safety.md)'s "Exit-code
and warning semantics across commands" section for the complete
breakdown. This list is representative, not exhaustive — each command's
own doc (linked above) covers its full flag reference and example
output.

## Architecture

`src`-layout package (`maops_pydevops`): `cli.py` (argparse construction
+ dispatch only) calls one `commands/*.py` orchestration function per
subcommand, each composing typed frozen-dataclass models from `core/*.py`
and rendering through one shared text/JSON/Markdown output layer. Two
narrow, explicit exceptions to "no subprocess, no network" — a fixed
five-tool allowlist in `core/runner.py`, and a fixed HTTP/TCP surface in
`core/health_http.py`/`core/health_tcp.py` — are each isolated to a
single module and enforced by dedicated architectural regression tests.
See [docs/architecture.md](docs/architecture.md) for the complete
diagrammed system, including the v0.6.0+ report-aggregation/workflow
composition layer and the v0.7.0 packaging/release boundary.

## Security philosophy

No `shell=True`, `os.system`, `eval`, `exec`, or `pickle` anywhere in
`src/`. No arbitrary command execution at any layer — `tools inspect`'s
five allowlisted version checks are the only subprocess surface, and
`workflow run`'s declarative step files are proven data, not code
(shell-metacharacter payloads are preserved as inert literal text, never
interpreted). Network access is isolated to two modules with mandatory
TLS verification and no insecure-mode flag. Every file-content read uses
an fd-safe, symlink-refusing pattern; every file write outside a build/
test temp directory is atomic and symlink-race-proof. Zero third-party
runtime dependencies across all seven releases. See
[SECURITY.md](SECURITY.md) for the complete boundary catalogue.

## Testing and release engineering

`tests/unit/` (fully isolated via `monkeypatch`/dependency injection —
no real host state, clock, or network) and `tests/integration/` (real
subprocess invocations of the installed CLI, real loopback-only network
I/O, never a public host), enforced at a 90% coverage floor. Every
release runs `make quality` → `make build` → `make smoke-install` (an
isolated, offline install of the exact built wheel) → `make
release-check`, then Python 3.11-3.14 CI, before a tag and GitHub
Release. See [docs/release-process.md](docs/release-process.md) for the
complete process and what each `make` target does and does not
guarantee.

## Release evolution

| Version | Highlights |
|---|---|
| v0.1.0 | CLI skeleton, `doctor`, exit-code convention, CI matrix. |
| v0.2.0 | Typed TOML configuration; safe subprocess runner; `tools inspect`. |
| v0.3.0 | `inventory system`/`inventory filesystem` — read-only host/filesystem facts. |
| v0.4.0 | `logs parse`/`logs analyze` — fd-safe log reading, redaction, streaming analysis. |
| v0.5.0 | `health http`/`health tcp` — the package's first intentional network access. |
| v0.6.0 | `report aggregate` and declarative `workflow` automation. |
| v0.7.0 | Final hardening: closed deferred test/doc findings, security audit, portfolio docs. |

Full detail per release: [CHANGELOG.md](CHANGELOG.md) and
[docs/roadmap.md](docs/roadmap.md).

## Documentation

- [docs/architecture.md](docs/architecture.md) — complete system design.
- [docs/portfolio-guide.md](docs/portfolio-guide.md) — project narrative for a technical reviewer.
- [docs/release-process.md](docs/release-process.md) — the real release process.
- [SECURITY.md](SECURITY.md) — security boundaries and reporting.
- [docs/configuration.md](docs/configuration.md), [docs/subprocess-safety.md](docs/subprocess-safety.md),
  [docs/inventory.md](docs/inventory.md), [docs/filesystem-inventory-safety.md](docs/filesystem-inventory-safety.md),
  [docs/log-parsing.md](docs/log-parsing.md), [docs/log-analysis.md](docs/log-analysis.md),
  [docs/log-redaction.md](docs/log-redaction.md), [docs/health-checks.md](docs/health-checks.md),
  [docs/http-health-safety.md](docs/http-health-safety.md), [docs/aggregated-reports.md](docs/aggregated-reports.md),
  [docs/workflows.md](docs/workflows.md), [docs/workflow-security.md](docs/workflow-security.md) —
  per-feature contracts.
- [docs/best-practices.md](docs/best-practices.md), [docs/troubleshooting.md](docs/troubleshooting.md),
  [CONTRIBUTING.md](CONTRIBUTING.md) — development reference.
- [docs/roadmap.md](docs/roadmap.md) — release history and optional future enhancements.
- [docs/engineering-reviews/](docs/engineering-reviews/) — dated specialist review documents.

## Quality commands

```bash
make quality          # format-check + lint + type-check + coverage (>=90%)
make build             # sdist + wheel
make smoke-install      # install the built wheel into an isolated venv and exercise the CLI
make release-check       # quality + build + smoke-install
```

Run `make help` for the full target list.

## Project status

**v0.7.0 is the final planned release in this project's seven-day
portfolio arc.** All seven planned days are complete; no further feature
work is scheduled. See [docs/roadmap.md](docs/roadmap.md)'s "Optional
future enhancements" section for ideas that were deliberately scoped out
rather than implemented.

## License

MIT — see [LICENSE](LICENSE).
