# Architecture

## 1. Package layout

`src`-layout, so the installed package can never accidentally import
from the working directory instead of the installed distribution:

```
src/maops_pydevops/
    __init__.py     # imports get_version reference only; no import-time side effects
    __main__.py      # python -m maops_pydevops
    cli.py            # argparse construction + dispatch
    version.py         # authoritative version lookup (importlib.metadata, lazy)
    commands/
        doctor.py         # required + optional checks, build_report()
    core/
        models.py           # enums + frozen dataclasses
        output.py             # text/JSON rendering
        platform.py             # injectable platform/python inspection
```

## 2. Entry points

Both invocation paths call the identical function:

- Console script: `pyproject.toml` `[project.scripts]` maps `maops-py` to
  `maops_pydevops.cli:main`.
- Module invocation: `__main__.py` does `sys.exit(main())`, importing
  `main` from `cli.py`.

There is exactly one `main()` implementation. Neither entry point
contains its own command logic.

## 3. CLI construction vs. execution

`cli.py` separates **parser construction** (`build_parser()` — wires
flags and subcommands, runs no logic) from **execution**
(`run_version()`, `run_doctor()` — do the actual work and return an exit
code). `main()` parses arguments, then dispatches through a small
`dict[str, Callable]` command table keyed by subcommand name. Argparse's
own behavior (not custom code) handles `-h/--help` and invalid-choice
errors.

## 4. Data flow: doctor

```
commands/doctor.py:build_report()
    core/platform.py:gather_python_info()/gather_platform_info()
    commands/doctor.py: run required checks (fixed order)
    commands/doctor.py: run optional tool checks (fixed order, shutil.which only)
    -> core/models.py:DoctorReport (frozen dataclass)

cli.py:run_doctor()
    core/output.py:render_text() or render_json()
    -> print once, return exit code from DoctorReport.overall
```

Optional tool checks never affect `overall` — only required-check
failures do, per the exit-code convention below.

## 5. Typed models

`core/models.py` defines `CheckStatus` and `OutputFormat` as
`StrEnum`, and `PythonInfo`, `PlatformInfo`, `DoctorCheck`, `DoctorReport`
as `frozen=True` dataclasses with explicit `to_dict()`/`to_json()`
methods. Serialization never uses `dataclasses.asdict()` or dict
spreading — every field is written out explicitly so the JSON schema is
traceable directly from the code.

## 6. Exit-code convention

- `0` — success
- `1` — operational or required-check failure (doctor's `overall` is
  `fail`)
- `2` — CLI usage error (unknown command, invalid `--format`, no
  subcommand)

## 7. Versioning

`pyproject.toml`'s `[project] version` is the only place the version
number is written. `version.py::get_version()` reads it back via
`importlib.metadata.version(...)` at call time, never at import time.

## 8. Safety boundaries

`commands/doctor.py` never imports `subprocess`; optional tool presence
is checked with `shutil.which()` only. No module in this package performs
network I/O, reads/dumps environment variables, or writes outside a
test/build temporary directory. See `.claude/CLAUDE.md` for the full
restriction list and where each is enforced/tested.

## 9. Tests

`tests/unit/` exercises models, platform logic, doctor checks, and CLI
dispatch in-process with `monkeypatch` for anything host-dependent (tool
presence, Python version, OS family). `tests/integration/` exercises the
actual entry points as subprocesses (`python -m maops_pydevops`, the
`maops-py` console script) to verify the two invocation paths are truly
equivalent and that import produces no output.
