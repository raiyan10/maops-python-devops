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
`.github/workflows/python-validation.yml`.

## Pinned GitHub Actions

Every `uses:` reference in `.github/workflows/` must be pinned to a full
40-character commit SHA with a trailing `# vX.Y.Z` comment — no tags, no
branch names. This is enforced by
`tests/unit/test_actions_pinning.py`. When bumping an action version,
update both the SHA and the version comment together.

## Branch naming

Prefix branches with the type of change:

- `feature/` — new functionality (e.g. `feature/day-2-config-command`)
- `fix/` — bug fixes
- `docs/` — documentation-only changes
- `refactor/` — internal restructuring with no behavior change
- `chore/` — tooling, dependency, or maintenance changes

## Code standards

See [`.claude/CLAUDE.md`](.claude/CLAUDE.md) for the full typing,
testing, and security policy. In short: mypy strict, no untyped public
functions, tests via `monkeypatch` rather than depending on the host
environment, and no shell execution, network access, or import-time side
effects anywhere in the package.

## Commits and releases

This project follows Conventional Commits where practical (e.g.
`feat(day-2): add config command`). Commits, pushes, tags, and releases
are performed by the repository owner — automated tooling and AI
assistants must not perform these without explicit instruction.
