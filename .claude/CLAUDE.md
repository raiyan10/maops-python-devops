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
    cli.py             # argparse construction + dispatch only
    version.py          # lazy importlib.metadata lookup, never at import time
    commands/
        doctor.py        # required + optional checks, build_report()
        config.py          # config CLI orchestration, build_show_report()
        tools.py             # allowlisted tool inspection, build_inspect_report()
    core/
        models.py          # enums + frozen dataclasses (doctor, tools-inspect)
        config_models.py     # config-domain enums + frozen dataclasses
        output.py               # text/JSON rendering, all report types
        platform.py                # injectable platform/python inspection
        config.py                    # config path/parse/validate/precedence/init
        runner.py                      # safe subprocess execution layer
```

Parser construction (`build_parser()`) must never contain command logic;
execution lives in separate `run_*` functions. Argparse's own behavior
(not custom code) handles `-h/--help` and invalid-choice errors for every
`choices=`-backed argument, with one deliberate exception: `tools
inspect`'s `tool` positional validates against the allowlist in
`run_tools_inspect()` rather than via argparse `choices=`, because that
combination (`nargs="*"` + `choices=` + no explicit `default=`) had
version-dependent behavior between Python 3.11 and 3.12 — do not
reintroduce `choices=` on that positional without re-verifying against
the full 3.11–3.14 matrix. `config` and `tools` are two-level command
groups (nested `add_subparsers`, `required=True` on the leaf level) —
`config show`, `tools inspect`, etc. `--version` is checked before
subcommand dispatch in `main()`, so it always short-circuits even
alongside a subcommand.

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
- Config tests must never read or write the real invoking user's `HOME`
  — isolate `HOME`/`XDG_CONFIG_HOME`/`MAOPS_PY_CONFIG_FILE` via
  `monkeypatch.setenv` or an injected `env=` mapping in every test.
- Tool-inspection tests must never depend on real git/docker/kubectl/
  terraform/ansible availability — monkeypatch `shutil.which()` and the
  runner, or use the deterministic `scripts/smoke/fake-git` stub for
  subprocess-boundary tests.

## Security restrictions

No `shell=True`, `os.system`, `eval`, `exec`, `pickle`, `sudo`, service or
process mutation, network requests, environment-variable dumping, secret
or token collection, writes outside build/test temp directories, silent
exception swallowing, import-time side effects, or global logging
configuration on import.

`commands/doctor.py`'s optional tool checks use `shutil.which()` only —
never subprocess execution. `core/runner.py` is the sole, narrowly
scoped exception: it is the only module permitted to import
`subprocess`, always with `shell=False`, `stdin=subprocess.DEVNULL`, and
a configurable timeout, and it is only ever invoked by
`commands/tools.py` with one of five fixed, hardcoded argv tuples
(`git`/`docker`/`kubectl`/`terraform`/`ansible` version checks) resolved
to an absolute path via `shutil.which()` first. No CLI flag, environment
variable, or configuration key accepts an arbitrary command — Day 2 does
not expose a general command-execution surface. See
`docs/subprocess-safety.md` for the full contract.

`core/config.py` is the sole module permitted to read named
`MAOPS_PY_*`/`XDG_CONFIG_HOME`/`HOME` environment variables or write
outside a build/test temp directory, and only ever under the resolved
configuration path (`$XDG_CONFIG_HOME/maops-py/config.toml`, falling back
to `$HOME/.config/maops-py/config.toml`, overridable via
`MAOPS_PY_CONFIG_FILE`). No configuration key may hold a secret, token,
or credential value — an unrecognized key makes the file invalid, never
silently ignored. `config init` never follows a symbolic link at its
target path, with or without `--force`, and never modifies an existing
parent directory's permissions. See `docs/configuration.md` for the full
contract.

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
