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
        config.py           # config CLI orchestration: build_show_report(), etc.
        tools.py              # allowlisted tool inspection, build_inspect_report()
    core/
        models.py           # enums + frozen dataclasses (doctor, tools-inspect)
        config_models.py      # config-domain enums + frozen dataclasses
        output.py               # text/JSON rendering, all report types
        platform.py               # injectable platform/python inspection
        config.py                   # config path/parse/validate/precedence/init
        runner.py                     # safe subprocess execution layer
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
(`run_version()`, `run_doctor()`, `run_config_*()`, `run_tools_inspect()`
— do the actual work and return an exit code). `main()` parses arguments,
then dispatches through a small `dict[str, Callable]` command table keyed
by subcommand name. Argparse's own behavior (not custom code) handles
`-h/--help` and invalid-choice errors for every `choices=`-backed option
and subcommand. The one exception is `tools inspect`'s `tool` positional:
tool-name validation happens in `run_tools_inspect()` itself, not via
argparse `choices=`, because that combination proved to have
version-dependent behavior between Python 3.11 and 3.12 (see
`CHANGELOG.md`'s `[0.2.0]` "Fixed" entry). It still produces exit `2` for
an unsupported name.

`config` and `tools` are two-level command groups (`config show`, `tools
inspect`, etc.) — the first nested subparsers in this codebase. Each
group has its own `add_subparsers(dest="<group>_command", required=True)`
and its own flat dispatch dict (`_CONFIG_COMMANDS`, `_TOOLS_COMMANDS`),
collected under `_COMMAND_GROUPS`. A bare `maops-py config` (no leaf
subcommand) is rejected by argparse itself via `required=True`, exit 2.

`--version` is checked first in `main()`, before subcommand dispatch, so
it always short-circuits — `maops-py --version doctor` prints only the
version and exits 0, regardless of what subcommand follows. `maops-py
doctor --version` is a separate case: `--version` is a top-level-only
flag, never added to any subparser, so this is an argparse "unrecognized
arguments" usage error (exit 2).

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

## 4a. Data flow: configuration

```
core/config.py:resolve_config_path()        # MAOPS_PY_CONFIG_FILE > XDG_CONFIG_HOME > HOME
core/config.py:parse_toml_file()            # tomllib.load(), missing vs malformed distinguished
core/config.py:validate_config_schema()     # unknown keys, bool-as-numeric, range checks
core/config.py:resolve_effective_config()   # CLI > environment > file > default, per field
    -> core/config_models.py:ConfigResolution (config, sources, or a typed error)

commands/config.py:build_show_report()
    -> core/config_models.py:ConfigShowReport
cli.py:run_config_show()
    core/output.py:render_config_show_text() or render_config_show_json()
```

An invalid file or an invalid `MAOPS_PY_*` environment variable never
produces a partial or misleading report: `resolve_effective_config()`
returns `config=None` with a human-readable `error`, and every `config`
subcommand that depends on it fails operationally (exit 1) instead of
silently falling back to a lower-precedence source.

## 4b. Data flow: tool inspection

```
commands/tools.py:TOOL_ALLOWLIST                # fixed (name, argv) pairs, 5 tools only
commands/tools.py:build_inspect_report()
    shutil.which(name)                          # resolve absolute executable path
    core/runner.py:run_command(CommandSpec)     # shell=False, timeout, truncation
    -> core/models.py:ToolInspectionResult (per tool)
    -> core/models.py:ToolsInspectReport (overall)

cli.py:run_tools_inspect()
    core/output.py:render_tools_inspect_text() or render_tools_inspect_json()
```

`run_command()` is the only function in this package that imports
`subprocess`; see `docs/subprocess-safety.md` for its full contract.

## 5. Typed models

`core/models.py` defines `CheckStatus` and `OutputFormat` as
`StrEnum`, and `PythonInfo`, `PlatformInfo`, `DoctorCheck`, `DoctorReport`,
`ToolInspectionResult`, `ToolsRunConfiguration`, `ToolsInspectReport` as
`frozen=True` dataclasses with explicit `to_dict()`/`to_json()` methods.
`core/config_models.py` follows the identical convention for the
configuration domain: `ConfigSource`, `ConfigFileStatus`, `ConfigInitStatus`
as `StrEnum`; `EffectiveConfig`, `EffectiveConfigSources`, `ConfigResolution`,
`ConfigShowReport`, `ValidatedConfigValues`, `TomlParseResult`,
`SchemaValidationResult`, `ConfigInitResult` as `frozen=True` dataclasses.
Serialization never uses `dataclasses.asdict()` or dict spreading — every
field is written out explicitly so the JSON schema is traceable directly
from the code. No custom exception classes are introduced anywhere: every
public function in `core/config.py` and `core/runner.py` returns a typed
result dataclass instead of raising past its own boundary, extending the
same pattern `DoctorCheck.status` already established in Day 1.

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
is checked with `shutil.which()` only. `core/runner.py` is the sole,
narrowly scoped exception to "no subprocess": it never sets `shell=True`,
never invokes a shell, always uses `stdin=subprocess.DEVNULL`, and is only
ever called by `commands/tools.py` with one of five fixed, hardcoded argv
tuples (`git`/`docker`/`kubectl`/`terraform`/`ansible` version checks) —
Day 2 does not expose an arbitrary command-execution CLI. `core/config.py`
is the sole module permitted to read named environment variables
(`MAOPS_PY_*`, `XDG_CONFIG_HOME`, `HOME`) and to write outside a
test/build temporary directory, and only under the user's own
configuration directory. No module performs network I/O or dumps the
full environment. See `.claude/CLAUDE.md` for the full restriction list
and `docs/subprocess-safety.md` / `docs/configuration.md` for the two new
modules' complete contracts.

## 9. Tests

`tests/unit/` exercises models, platform logic, doctor checks, config
resolution/validation/init, the subprocess runner, tool inspection, and
CLI dispatch in-process with `monkeypatch` for anything host-dependent
(tool presence, Python version, OS family, environment variables, HOME).
No config test ever reads or writes the real invoking user's HOME — every
test isolates `HOME`/`XDG_CONFIG_HOME`/`MAOPS_PY_CONFIG_FILE` via
`monkeypatch.setenv` or an injected `env=` mapping. `tests/integration/`
exercises the actual entry points as subprocesses (`python -m
maops_pydevops`, the `maops-py` console script) to verify the two
invocation paths are truly equivalent, that import produces no output,
and — for `tools inspect` — using a deterministic stub executable
(`scripts/smoke/fake-git`) rather than a real, host-installed tool.
