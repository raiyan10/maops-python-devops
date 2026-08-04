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

v0.2.0 still has zero runtime dependencies — `argparse`, `contextlib`,
`dataclasses`, `enum`, `importlib.metadata`, `json`, `os`, `pathlib`,
`platform`, `shutil`, `stat`, `subprocess` (confined to `core/runner.py`
only), `sys`, `tempfile`, `time`, and `tomllib` (standard library since
Python 3.11, matching this project's floor). Development tooling
(`pytest`, `ruff`, `mypy`, `build`) lives in the `dev` optional-dependency
group, never in runtime `dependencies`.

## 5. Deterministic, isolated tests

Required and optional checks run in a fixed order every time. Anything
host-dependent (installed Python version, OS family, presence of
git/docker/kubectl/terraform/ansible) is simulated via dependency
injection or `monkeypatch` rather than relying on what happens to be
installed on the machine running the tests.

## 6. No premature abstraction

v0.1.0 deliberately shipped without configuration file support: "none of
that is needed yet." v0.2.0 adds it because a concrete need finally
existed — `tools inspect` needs a per-invocation timeout and output
limit, and both `doctor` and `tools inspect` benefit from a default
output format — not because configurability is a virtue on its own. The
configuration surface stays exactly as large as those needs: three keys,
no plugin system, no nested tables, no arbitrary key namespace. The same reasoning applies to `core/runner.py`: it exists because `tools
inspect` needed to execute a process safely, not because subprocess
execution is a generally useful capability to expose.

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
configuration on import. `core/runner.py` is the only module permitted to
import `subprocess`, and only ever runs one of five fixed, hardcoded argv
tuples selected by `commands/tools.py` — Day 2 does not expose an
arbitrary command-execution CLI. `core/config.py` is the only module
permitted to read named `MAOPS_PY_*`/`XDG_CONFIG_HOME`/`HOME` environment
variables or write outside a build/test temp directory, and only ever
under the resolved configuration path. See `.claude/CLAUDE.md` for the
authoritative list.
