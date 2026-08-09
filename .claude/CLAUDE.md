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
        inventory.py           # inventory CLI orchestration, build_system_report()/build_filesystem_report()
        logs.py                  # logs CLI orchestration, build_log_parse_report()/build_log_analysis_report()
        health.py                  # health CLI orchestration, build_health_http_report()/build_health_tcp_report()
    core/
        models.py          # enums + frozen dataclasses (doctor, tools-inspect)
        config_models.py     # config-domain enums + frozen dataclasses
        inventory_models.py    # inventory-domain enums + frozen dataclasses
        log_models.py             # log-domain enums + frozen dataclasses
        health_models.py            # health-domain enums + frozen dataclasses
        output.py                     # text/JSON rendering, all report types
        platform.py                     # injectable platform/python inspection
        config.py                         # config path/parse/validate/precedence/init
        runner.py                           # safe subprocess execution layer
        system_inventory.py                   # injectable host/OS/CPU/memory/uptime collection
        filesystem_inventory.py                 # bounded, deterministic filesystem scanner
        log_reader.py                             # fd-safe bounded binary log reader
        log_parsers.py                              # jsonl/syslog/auto line parsers
        log_redaction.py                              # bounded regex secret redaction
        log_analysis.py                                 # streaming aggregation, signatures, buckets
        health_http.py                                    # bounded HTTP availability checks (network-capable)
        health_tcp.py                                       # bounded TCP connect checks (network-capable)
        health_runner.py                                      # bounded, ordered concurrent.futures helper
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
the full 3.11–3.14 matrix. `config`, `tools`, `inventory`, `logs`, and
`health` are two-level command groups (nested `add_subparsers`,
`required=True` on the leaf level) — `config show`, `tools inspect`,
`inventory system`, `inventory filesystem`, `logs parse`, `logs analyze`,
`health http`, `health tcp`, etc. `--version` is checked before subcommand
dispatch in `main()`, so it short-circuits whenever `parser.parse_args()`
itself succeeds — including alongside a complete subcommand path (e.g.
`maops-py --version doctor`). It does **not** short-circuit an incomplete
two-level group given with no leaf subcommand (`maops-py --version
tools`/`config`/`inventory`/`logs`/`health` alone still exit 2), because
argparse's own `required=True` validation on the nested subparser raises
a usage error during `parse_args()`, before `main()` ever inspects
`args.version`. See `docs/subprocess-safety.md`'s "Exit-code and warning
semantics across commands" section for how `warn`-level conditions map to
exit codes differently per command (`doctor` vs. `tools inspect` vs.
`inventory` vs. `health`).

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
- System-inventory tests must never depend on the real host's CPU count,
  distribution, or `/proc/meminfo`/`/proc/uptime` content — every
  `gather_*` function in `core/system_inventory.py` accepts an injectable
  override (including raw `meminfo_lines`/`uptime_line` seams) for
  exactly this reason. Filesystem-inventory tests must always scan a
  `tmp_path`-scoped fixture tree, never the real repository tree.
- Log-reader tests must never read a real system log file — every
  fixture is a `tmp_path`-scoped file, and every fd-safety adversarial
  condition (a symlink, a FIFO, a race between the safety check and the
  open, an `O_NOATIME` permission fallback) is simulated via
  `monkeypatch` rather than depending on real ownership/permission
  state. Parser and analysis tests must never depend on the real host
  clock, locale, or timezone.

## Security restrictions

No `shell=True`, `os.system`, `eval`, `exec`, `pickle`, `sudo`, service or
process mutation, environment-variable dumping, secret or token
collection, writes outside build/test temp directories, silent exception
swallowing, import-time side effects, or global logging configuration on
import. Network access is forbidden everywhere **except**
`core/health_http.py`/`core/health_tcp.py` (and their orchestration via
`core/health_runner.py`/`commands/health.py`) — see the `core/health_*.py`
paragraph below for the full, narrowly scoped exception and
`docs/http-health-safety.md` for its complete contract.

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

`core/system_inventory.py` and `core/filesystem_inventory.py` never
import `subprocess` or `socket`, and never read named environment
variables — `inventory system` collects host/OS/CPU/memory/uptime facts
via `platform`/`os` introspection only (no network or DNS resolution),
and `inventory filesystem` reads only filesystem metadata
(`os.lstat`/`os.scandir`/`entry.stat`) — never file content, never a
hash, never following a symbolic link, never crossing a mount-point
boundary, never using unrestricted `Path.rglob()` or `os.walk()`. See
`docs/inventory.md` and `docs/filesystem-inventory-safety.md` for the
full contracts.

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

`core/log_reader.py` is the first module in this package to open and
read file *content* rather than only metadata. It is the sole module
permitted to `os.open()` a user-supplied path: it validates with
`os.lstat()` first (rejecting nonexistent paths, directories, symlinks,
and FIFOs/sockets/block/character devices), opens with
`O_NOFOLLOW`/`O_CLOEXEC`/`O_NOATIME` where available, and verifies the
opened descriptor via `os.fstat()` against a `(st_dev, st_ino)`
comparison to the pre-open `lstat()` result (detecting a path replaced
between the check and the open). It reads bounded, sequential binary
chunks only — never `mmap`, never a whole-file read — and never writes
to, or changes the mode/ownership/access/modification times of, the
input file. `core/log_models.py`, `core/log_parsers.py`,
`core/log_redaction.py`, and `core/log_analysis.py` never import
`subprocess` or `socket`, never read named environment variables, never
accept stdin input, never expand a glob, and never extract or
decompress an archive. `logs parse`/`logs analyze` never serialize a
complete raw line into any report field — an overlong line's content is
dropped before it is ever buffered, and malformed-line issue details
describe the failure without echoing the triggering line. Secret
redaction (`core/log_redaction.py`) is enabled by default on the
`message` field and is a best-effort mitigation for a fixed, documented
pattern set, not a completeness guarantee — see `docs/log-parsing.md`,
`docs/log-analysis.md`, and `docs/log-redaction.md` for the full
contracts.

`core/health_http.py` and `core/health_tcp.py` are the only two modules
in this package permitted to make network connections, and the only two
permitted to import `socket`, `ssl`, or `http.client`;
`core/health_runner.py` is the only module permitted to import
`concurrent.futures`. Every other module in the package — including
`core/runner.py` outside its established subprocess use — retains its
existing "no network" invariant unchanged, verified by
`tests/unit/test_no_network_health_boundary.py`. HTTP requests use
`http.client` directly, never `urllib.request` (which would consult
proxy environment variables and could follow redirects implicitly).
HTTPS always validates certificates and hostnames via
`ssl.create_default_context()` with zero attribute relaxation anywhere —
there is no `--insecure` flag and no other certificate-verification
bypass in this package. Redirects are never followed: a `3xx` response
is reported as received, using ordinary expected-status logic. Only
`GET` and `HEAD` are supported, never with a request body; there is no
CLI flag, environment variable, or configuration key that can inject a
custom header or credential — URL userinfo is rejected outright as a
usage error. Response bodies (`.read()`/`.readinto()`/iteration) and
response headers (`.getheaders()`/`.headers`) are never accessed
anywhere, and a response's `reason` phrase is never serialized — every
report `detail` is a fixed, package-generated string from a closed
failure-reason enum, never arbitrary exception or server-controlled
text. TCP checks are connect-only: `socket.create_connection(...)`
followed by `getpeername()` and `close()`, with no `send`/`recv` call
anywhere. Target syntax accepts exactly one explicit host+port (or URL)
per string — no CIDR expansion, port ranges, comma-separated ports, or
host/subnet discovery of any kind. A validated target's URL report field
has its query *values* redacted (keys and order preserved) and its
fragment/userinfo permanently stripped; the original raw command-line
string is never retained on any object. See `docs/health-checks.md` and
`docs/http-health-safety.md` for the complete CLI/report/safety
contracts.

## Exit-code convention

- `0` — success
- `1` — operational or required-check failure
- `2` — CLI usage error (unknown command, invalid option value, no
  subcommand given)

What counts as a `1` varies by command — see `docs/subprocess-safety.md`
for the full breakdown. `inventory system`/`inventory filesystem`
deliberately decouple their `overall` report field from their exit code:
both always exit `0` for a successfully-produced report regardless of
`overall` being `pass` or `warn` — only a report that could not be built
at all (an inaccessible/nonexistent filesystem root) exits `1`.
`logs parse`/`logs analyze` follow the same convention, with one
addition: a non-empty input that yields zero parseable events also
exits `1`, in addition to the file itself being unreadable.
`health http`/`health tcp` use a three-way per-target
`pass`/`warn`/`fail` status (`warn` means a target recovered during
retries): report `overall` of `pass` or `warn` exits `0`, `fail` exits
`1`, and a target-count/syntax/privacy validation failure — checked
before any connection is attempted — exits `2`. See
`docs/health-checks.md` for the complete semantics.

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
