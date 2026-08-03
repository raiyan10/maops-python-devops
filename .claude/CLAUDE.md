# MAOps Python DevOps Automation Toolkit

## Mission

Project 2 of the MAOps DevOps portfolio. A Python-based CLI toolkit for
structured, read-only DevOps diagnostics and automation. Project 1
(`maops-linux-devops-toolkit`) is a Bash implementation; this project is a
fresh, independent implementation in Python — it shares portfolio house
style (docs, CI conventions, agent structure) but no code or architecture.

## Package and CLI names

- Repository: `maops-python-devops`
- Import package: `maops_pydevops`
- Console script: `maops-py`
- `python -m maops_pydevops` must invoke the exact same CLI as `maops-py`
  (both call `maops_pydevops.cli:main`) — never duplicate command logic
  between the two entry points.

## Architecture

`src/` layout:

```
src/maops_pydevops/
    __init__.py
    __main__.py
    cli.py           # argparse construction + dispatch only
    version.py        # lazy importlib.metadata lookup, never at import time
    commands/
        doctor.py      # required + optional checks, build_report()
    core/
        models.py      # enums + frozen dataclasses
        output.py      # text/JSON rendering
        platform.py    # injectable platform/python inspection
```

Parser construction (`build_parser()`) must never contain command logic;
execution lives in separate `run_*` functions. Argparse's own behavior
(not custom code) handles `-h/--help` and invalid-choice errors.

## Typing policy

- mypy strict mode, no exceptions without explicit justification.
- Public functions are fully typed; no bare `Any`.
- Dataclasses are `frozen=True` where practical; no mutable default
  arguments.
- Serialization is explicit (`to_dict()`/`to_json()` methods with literal
  dict construction) — never blind dict-spreading (`**dataclasses.asdict()`).
- Untyped `argparse.Namespace` values are converted to a typed shape at the
  CLI boundary and must not leak further into the codebase.

## Testing policy

- pytest, with `tests/unit/` and `tests/integration/` split by scope.
- Coverage must stay at or above 90% (`--cov-fail-under=90`).
- Simulate unsupported Python versions, unsupported platforms, and
  optional-tool presence/absence via dependency injection or
  `monkeypatch` — never depend on the real host's installed toolchain.
- Tests must be deterministic: no reliance on real network state, host
  environment variables, or non-fixed check ordering.

## Security restrictions

No `shell=True`, `os.system`, `eval`, `exec`, `pickle`, `sudo`, service or
process mutation, network requests, environment-variable dumping, secret
or token collection, writes outside build/test temp directories, silent
exception swallowing, import-time side effects, or global logging
configuration on import. Optional external tool checks use
`shutil.which()` only — never subprocess execution.

## Exit-code convention

- `0` — success
- `1` — operational or required-check failure
- `2` — CLI usage error (unknown command, invalid option value, no
  subcommand given)

## Versioning policy

Single authoritative version source: `pyproject.toml`'s `[project]
version`. `version.py::get_version()` reads it back via
`importlib.metadata.version(...)` at call time — never a second version
string, never computed at import time.

## Git workflow

- Branch naming: `feature/`, `fix/`, `docs/`, `refactor/`, `chore/`
  prefixes.
- Conventional Commits preferred (`feat(day-N): ...`, `docs(day-N): ...`).
- **Do not commit, push, tag, or release without explicit instruction from
  the user in that conversation.** A prior approval does not carry over to
  future turns or sessions.
