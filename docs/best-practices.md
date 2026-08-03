# Best Practices

## 1. Strict typing

mypy runs in `strict` mode against `src/`. Public functions are fully
typed; `Any` is avoided; mutable default arguments are not used.
Untyped `argparse.Namespace` access is confined to `cli.py`'s small
dispatch functions and never leaks into `commands/` or `core/`.

## 2. Immutability

`core/models.py` dataclasses are `frozen=True`. `DoctorReport.checks` is
a `tuple`, not a `list`, reinforcing that a report is a fixed snapshot
once built.

## 3. Explicit serialization

Every model has a `to_dict()` built from a literal dict per field.
`dataclasses.asdict()` and other blind-spreading approaches are avoided
so the JSON schema stays traceable directly from the code, and enum
fields serialize via `.value` rather than the enum object.

## 4. Stdlib-only runtime

v0.1.0 has zero runtime dependencies — only `argparse`, `dataclasses`,
`enum`, `importlib.metadata`, `json`, `pathlib`, `platform`, `shutil`,
`sys`, and `tempfile`. Development tooling (`pytest`, `ruff`, `mypy`,
`build`) lives in the `dev` optional-dependency group, never in runtime
`dependencies`.

## 5. Deterministic, isolated tests

Required and optional checks run in a fixed order every time. Anything
host-dependent (installed Python version, OS family, presence of
git/docker/kubectl/terraform/ansible) is simulated via dependency
injection or `monkeypatch` rather than relying on what happens to be
installed on the machine running the tests.

## 6. No premature abstraction

The package implements exactly one command (`doctor`) plus version
reporting. There is no plugin system, no command registry beyond the
small dispatch table in `cli.py`, and no configuration file support —
none of that is needed yet, and speculative infrastructure for
hypothetical future commands is deferred until those commands exist.

## 7. Ruff-clean formatting and linting

`ruff format --check` and `ruff check` both run as part of `make
quality`. Line length is capped at 100 columns; import sorting,
pyupgrade-style modernization (e.g. `StrEnum` over `str, Enum` on
Python 3.11+), and common bug-pattern rules are enabled.

## 8. Safety restrictions

No `shell=True`, `os.system`, `eval`, `exec`, `pickle`, `sudo`, service
or process mutation, network requests, environment-variable dumping,
secret collection, writes outside build/test temp directories, silent
exception swallowing, import-time side effects, or global logging
configuration on import. See `.claude/CLAUDE.md` for the authoritative
list.
