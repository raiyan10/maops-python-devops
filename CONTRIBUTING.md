# Contributing

## Development environment

- Python 3.11+ (see `.python-version`).
- A virtual environment: `python3 -m venv .venv && source .venv/bin/activate`.
- Install with dev dependencies: `python -m pip install -e ".[dev]"`.
- Tooling used: `pytest`, `pytest-cov`, `ruff`, `mypy`, `build` — all
  installed via the `dev` optional-dependency group, no separate
  `requirements.txt`.

## Quality gate

Before opening a pull request, run the same chain CI runs:

```bash
make quality        # format-check, lint, type-check, coverage (>=90%)
make build           # sdist + wheel
make smoke-install     # install the built wheel into an isolated venv, exercise the CLI
make release-check      # quality + build + smoke-install
```

`make release-check` is the single command that mirrors
`.github/workflows/python-validation.yml`. See
[docs/release-process.md](docs/release-process.md) for the complete
release process this chain is part of, and [SECURITY.md](SECURITY.md)
for this project's security boundaries and vulnerability-reporting
guidance.

## Pinned GitHub Actions

Every `uses:` reference in `.github/workflows/` must be pinned to a full
40-character commit SHA with a trailing `# vX.Y.Z` comment — no tags, no
branch names. This is enforced by
`tests/unit/test_actions_pinning.py`. When bumping an action version,
update both the SHA and the version comment together.

## Branch naming

Prefix branches with the type of change:

- `feature/` — new functionality (e.g. `feature/day-2-config-runner`,
  which added typed configuration management and the safe subprocess
  runner)
- `fix/` — bug fixes
- `docs/` — documentation-only changes
- `refactor/` — internal restructuring with no behavior change
- `chore/` — tooling, dependency, or maintenance changes

## Code standards

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) for the full typing,
testing, and security policy. In short: mypy strict, no untyped public
functions, tests via `monkeypatch` rather than depending on the host
environment, no shell invocation (`shell=True`, `os.system`) anywhere,
and no import-time side effects. `core/runner.py` is the sole, narrowly
scoped module permitted to import `subprocess` at all — see
[docs/subprocess-safety.md](docs/subprocess-safety.md). Network access is
similarly scoped: `core/health_http.py` and `core/health_tcp.py` are the
only two modules permitted to import `socket`/`ssl`/`http.client` (the
`health http`/`health tcp` commands), and `core/health_runner.py` is the
only module permitted to import `concurrent.futures` — every other
module still makes no network calls of any kind, which is enforced by a
dedicated regression test
(`tests/unit/test_no_network_health_boundary.py`). See
[docs/http-health-safety.md](docs/http-health-safety.md) for the complete
network safety model.

Loopback-only integration tests for the health commands
(`tests/integration/test_health_*_loopback.py`) use real
`127.0.0.1`-bound, ephemeral-port servers/listeners via the
`http_loopback_server`/`tcp_loopback_listener` fixtures in
`tests/conftest.py` — never a public host, never a mock standing in for
a real socket at the integration level.
`tests/integration/test_workflow_health_loopback.py` reuses the same
fixtures for `health_http`/`health_tcp` workflow steps.

`report aggregate`'s report-kind detection is purely structural (a fixed,
unique key combination per supported kind) and its normalization never
blindly embeds a full input report — see
[docs/aggregated-reports.md](docs/aggregated-reports.md).
`core/workflow_runner.py` is the sole module in `core/` permitted to
import from `commands/` (its entire purpose is orchestrating across other
commands' own orchestration functions), and executes every workflow step
through those existing functions — never a shell, never a recursive
`maops-py` subprocess, never `eval`/`exec` or dynamic imports.
`workflow validate` performs no execution, network, or subprocess
activity at all, which is enforced by a dedicated regression test
(`tests/unit/test_workflow_no_network_no_subprocess.py`). See
[docs/workflows.md](docs/workflows.md) and
[docs/workflow-security.md](docs/workflow-security.md) for the complete
schema and security contracts.

## Commits and releases

This project follows Conventional Commits where practical (e.g.
`feat(day-2): add typed configuration and a safe subprocess runner`).
Commits, pushes, tags, and releases
are performed by the repository owner — automated tooling and AI
assistants must not perform these without explicit instruction.
