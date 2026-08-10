# Best Practices

## 1. Strict typing

mypy runs in `strict` mode against `src/`. Public functions are fully
typed; `Any` is avoided; mutable default arguments are not used.
Untyped `argparse.Namespace` access is confined to `cli.py`'s small
dispatch functions and never leaks into `commands/` or `core/`.

## 2. Immutability

`core/models.py` dataclasses are `frozen=True`. `DoctorReport.checks` is
a `tuple`, not a `list`, reinforcing that a report is a fixed snapshot
once built. `core/inventory_models.py` follows the identical pattern —
`SystemInventoryReport.issues` and `FilesystemInventoryReport.issues`/
`largest_files` are all `tuple`s, never `list`s, even though the
filesystem scanner builds them up incrementally with mutable local lists
internally (`core/filesystem_inventory.py`'s private `_ScanState`) before
freezing them into the returned report.

## 3. Explicit serialization

Every model has a `to_dict()` built from a literal dict per field.
`dataclasses.asdict()` and other blind-spreading approaches are avoided
so the JSON schema stays traceable directly from the code, and enum
fields serialize via `.value` rather than the enum object.

## 4. Stdlib-only runtime

v0.6.0 still has zero runtime dependencies — `argparse`, `contextlib`,
`dataclasses`, `datetime`, `enum`, `errno`, `importlib.metadata`, `json`,
`math`, `os`, `pathlib`, `platform`, `re`, `shutil`, `stat`, `subprocess`
(confined to `core/runner.py` only), `sys`, `tempfile`, `time`, and
`tomllib` (standard library since Python 3.11, matching this project's
floor). `inventory system`/`inventory filesystem` add no new runtime
dependency — `platform.freedesktop_os_release()` and `os.getloadavg()`
are both plain stdlib, and `math` (for uptime's NaN/infinite rejection)
is stdlib too. `logs parse`/`logs analyze` add no new runtime dependency
either: `core/log_reader.py` uses only `os`/`stat`/`errno`;
`core/log_parsers.py` and `core/log_analysis.py` use only `re` and
`datetime` (no third-party date-parsing or regex library); `datetime.UTC`
(the alias used for timezone normalization) is available since Python
3.11, matching this project's floor. `health http`/`health tcp` add no
new runtime dependency either: `http.client`, `ssl`, `socket`,
`ipaddress`, `urllib.parse`, and `concurrent.futures` are all standard
library — no `requests`, `httpx`, or `aiohttp`. `report aggregate`/
`workflow` add no new runtime dependency either: `core/report_reader.py`
and `core/workflow_parser.py` reuse `os`/`stat`/`errno`/`json`/`tomllib`,
already used elsewhere in the package; `commands/report.py`'s atomic
`--output` writer reuses the identical `tempfile`/`contextlib` pattern
`core/config.py`'s `init_config_file()` established in v0.2.0 — no new
module, dependency, or novel I/O pattern was introduced for it.
Development tooling (`pytest`, `ruff`, `mypy`, `build`) lives in the
`dev` optional-dependency group, never in runtime `dependencies`.

## 5. Deterministic, isolated tests

Required and optional checks run in a fixed order every time. Anything
host-dependent (installed Python version, OS family, presence of
git/docker/kubectl/terraform/ansible, real `/proc/meminfo`/`/proc/uptime`
content, real CPU count, real filesystem race conditions) is simulated
via dependency injection or `monkeypatch` rather than relying on what
happens to be installed on, or racing against, the machine running the
tests. `core/system_inventory.py`'s `gather_*` functions accept
injectable overrides for every data source (including a raw
`meminfo_lines`/`uptime_line` seam so tests can supply fabricated procfs
content directly, never a real file); `core/filesystem_inventory.py`'s
tests always scan a `tmp_path`-scoped fixture tree, never the real
repository tree. Log-reader tests simulate every adversarial condition
(a symlink, a FIFO, a race between the safety check and the open, an
`O_NOATIME` permission fallback) via `monkeypatch` rather than depending
on real ownership/permission state, and always scan a `tmp_path`-scoped
log file, never a real system log.

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
under the resolved configuration path. `core/system_inventory.py` and
`core/filesystem_inventory.py` never import `subprocess` or `socket`,
never read named environment variables, and the filesystem scanner never
reads file content, computes a hash, follows a symbolic link, or crosses
a mount-point boundary — see `docs/filesystem-inventory-safety.md` for
the complete traversal contract. `core/log_reader.py`,
`core/log_parsers.py`, `core/log_redaction.py`, and
`core/log_analysis.py` never import `subprocess` or `socket`, never read
named environment variables, never accept stdin input, never expand a
glob, and never follow a symbolic link — `logs parse`/`logs analyze`
open exactly the one literal path given, reject symlinks and special
files outright, and never serialize a complete raw line into a report;
see `docs/log-parsing.md`, `docs/log-analysis.md`, and
`docs/log-redaction.md` for the complete contracts. `core/health_http.py`
and `core/health_tcp.py` are the only two modules permitted to import
`socket`/`ssl`/`http.client` — this package's first intentional network
access, isolated to these two modules plus `core/health_runner.py`
(permitted to import `concurrent.futures`) and `commands/health.py`
(orchestration only). HTTPS always validates certificates and hostnames
(`ssl.create_default_context()` with zero attribute relaxation, no
`--insecure` option); no request bodies, response-body retention,
response-header collection, or redirect-following anywhere; URL userinfo
is rejected outright; TCP checks are connect-only (no application data
sent, no banner read). Every other module's existing network prohibition
is unchanged and regression-tested — see `docs/http-health-safety.md` and
`docs/health-checks.md` for the complete contracts. `core/report_reader.py`
mirrors `core/log_reader.py`'s fd-safety pattern for JSON report input
(regular files only, symlinks and non-regular files always rejected,
bounded read, TOCTOU-verified); `core/report_aggregate.py` detects a
report's kind purely structurally and never blindly embeds a full input
report into an aggregate. `core/workflow_parser.py` never imports
`subprocess`/`socket`/`ssl`/`http.client` and performs no execution of
any kind — `workflow validate` never resolves a tool executable or opens
a connection. `core/workflow_runner.py` is the sole `core/` module
permitted to import from `commands/`, and executes a step only through
the package's own existing `commands/*.py` functions — never a shell,
never a recursive `maops-py` subprocess, never `eval`/`exec` or dynamic
imports. See `docs/aggregated-reports.md`, `docs/workflows.md`, and
`docs/workflow-security.md` for the complete contracts. See
`.claude/CLAUDE.md` for the authoritative list.
