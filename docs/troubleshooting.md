# Troubleshooting

## 1. `maops-py: command not found`

The console script is only on `PATH` inside the virtual environment it
was installed into. Activate it first: `source .venv/bin/activate`. As a
workaround, `python -m maops_pydevops` always works once the package is
installed, activated or not (as long as the interpreter you invoke is
the one with the package installed).

## 2. `pip install -e ".[dev]"` fails to find the package

Make sure you're running the command from the repository root (where
`pyproject.toml` lives) and that `src/maops_pydevops/__init__.py`
exists — `src`-layout packages are not discoverable if run from the
wrong working directory.

## 3. `doctor` reports `overall: fail`

Check the `checks` array (JSON) or the "Required checks" section (text)
for the specific check with `status: fail` — likely an unsupported
Python version, an unsupported OS family, or an unavailable temp
directory. Optional tool absence (git/docker/kubectl/terraform/ansible)
only ever produces a `warn`, never a `fail`.

## 4. `make coverage` fails below 90%

Run `pytest --cov=maops_pydevops --cov-report=term-missing` directly to
see exactly which lines/branches are uncovered, then add a targeted test
(prefer `monkeypatch` over depending on host state) rather than lowering
the threshold.

## 5. `make smoke-install` fails with "cannot access 'dist/*.whl'"

`smoke-install` expects a wheel to already exist in `dist/`. Run `make
build` first, or use `make release-check`, which runs `build` before
`smoke-install` automatically.

## 6. mypy strict errors on `argparse.Namespace` attribute access

Namespace attribute access is intentionally confined to `cli.py`'s small
`_dispatch_*` functions and `main()`. If you're seeing strict-mode
complaints elsewhere, it likely means `Namespace` (or raw parsed args)
leaked into `commands/` or `core/` — convert to a typed value at the
CLI boundary instead.

## 7. GitHub Actions failures on the pinned-action test

`tests/unit/test_actions_pinning.py` rejects any `uses:` reference that
isn't a full 40-character commit SHA with a trailing `# vX.Y.Z` comment.
If you bumped an action version, update the SHA (not just the comment)
to match the new release's actual commit.
