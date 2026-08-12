# Inventory

`maops-py inventory system` and `maops-py inventory filesystem` collect
typed, structured, read-only host and filesystem metadata. This document
describes both commands: their fields, degraded/unavailable-field
semantics, exit-code behavior, and their relationship to `doctor` and
`tools inspect`. For the filesystem scanner's traversal, symlink, and
same-filesystem safety contract, see
[docs/filesystem-inventory-safety.md](filesystem-inventory-safety.md).

## `doctor` vs. `tools inspect` vs. `inventory`

Three commands answer three different questions, and none of them
subsumes another:

| Command | Question it answers | How |
|---|---|---|
| `doctor` | Is this environment usable for the toolkit itself? | Fixed pass/fail/warn checks (Python version, package import, OS family, temp directory, ...) |
| `tools inspect` | What version of a specific, allowlisted external tool is installed? | Runs one of five fixed, hardcoded version-check argv tuples via the safe subprocess runner |
| `inventory system` / `inventory filesystem` | What does this host or filesystem tree actually look like right now? | Pure local introspection (`platform`, `os`) — structured facts, not pass/fail checks |

`inventory` never runs a subprocess and never touches the network or a
socket — it is architecturally closer to `doctor`'s environment
inspection than to `tools inspect`'s subprocess-based version checks. See
`docs/subprocess-safety.md`'s "Exit-code and warning semantics across
commands" section for how this affects exit-code behavior specifically.

## `inventory system`

```bash
maops-py inventory system
maops-py inventory system --format text
maops-py inventory system --format json
python -m maops_pydevops inventory system --format json
```

Collects, without any subprocess, network, or socket use:

- **Host**: hostname (`platform.node()` — local metadata only, never a
  DNS lookup or `socket.gethostname()`), OS family/release/version
  (`platform.uname()`), machine architecture.
- **Distribution**: Linux distribution ID/name/version, via
  `platform.freedesktop_os_release()` (standard library since Python
  3.10). Absent or unsupported on non-Linux platforms — this degrades to
  a `null` block plus a warning issue, never a fatal error.
- **Python**: version, implementation, and executable path.
- **CPU**: logical count (`os.cpu_count()`) and 1/5/15-minute load
  averages (`os.getloadavg()`, unsupported on Windows).
- **Memory** (Linux only): `MemTotal`/`MemAvailable` from
  `/proc/meminfo`, used bytes and a bounded used-percent.
- **Uptime** (Linux only): seconds, from `/proc/uptime`.

No timestamp field is collected in this release.

### Optional/unavailable fields

Every optional field that cannot be collected becomes an explicit JSON
`null` — never omitted, never fabricated, never silently substituted with
a different metric. Each degraded field is also recorded once in the
report's `issues` array, with a `component` name, a `status` of `"warn"`,
and a human-readable `detail`. Two design decisions worth calling out
explicitly:

- **No `MemFree` fallback**: if `/proc/meminfo` lacks a parseable
  `MemAvailable` line, `used_bytes`/`used_percent` become `null` with a
  warning — `MemFree` is never read as a substitute. `total_bytes` can
  still be populated independently if it parsed cleanly, so a single
  `memory` block can have some fields populated and others `null`
  simultaneously; this is intentional (see "Memory validation" below),
  unlike `distribution`/`uptime`, which are all-or-nothing blocks.
- **CPU count vs. load averages**: `cpu.logical_count` being `null` is a
  distinctly represented, non-warning condition (a genuinely
  indeterminate count is normal on some platforms) — only a load-average
  collection failure produces an `issues` entry.

### Memory validation (`/proc/meminfo`)

`MemTotal` and `MemAvailable` (both in kB in the source file) are parsed
independently. Any of the following renders the corresponding value
`null` and adds one folded warning detail to the `memory` issue (never
raises, never aborts the report):

- A line that isn't exactly `<key>: <integer> kB`.
- A negative value.
- `MemAvailable` numerically exceeding `MemTotal` (rejected as
  internally inconsistent, not silently clamped).
- `MemTotal` itself being `0` (guards the used-percent division; `0` is
  still reported verbatim in `total_bytes`, since it's a real observed
  value, not fabricated).

`used_bytes = total_bytes - available_bytes` and `used_percent =
round(used_bytes / total_bytes * 100, 2)`, clamped to `[0.0, 100.0]`, are
computed only when both source values parsed cleanly.

### Uptime validation (`/proc/uptime`)

The first whitespace-separated token is parsed as a float. Malformed
text, a negative value, NaN, or infinite all reject the value (`null` +
warning) rather than reporting nonsensical data.

### Exit-code behavior

`inventory system` always exits `0` for a successfully-produced report,
whether its `overall` field is `"pass"` or `"warn"` — partial optional
data being unavailable is never a reason to fail the invocation. This is
a deliberate divergence from `tools inspect` (where a single missing
requested tool is `warn` and *does* cause exit `1`) and is documented in
full, alongside `doctor`'s equivalent-but-differently-scoped behavior, in
`docs/subprocess-safety.md`.

### JSON example

```json
{
  "version": "0.7.0",
  "host": {
    "hostname": "myhost",
    "os_family": "Linux",
    "os_release": "6.8.0",
    "os_version": "#1 SMP ...",
    "machine": "x86_64"
  },
  "distribution": {
    "id": "ubuntu",
    "name": "Ubuntu",
    "version_id": "24.04",
    "available": true
  },
  "python": {
    "version": "3.12.3",
    "implementation": "CPython",
    "executable": "/home/user/.venv/bin/python"
  },
  "cpu": {
    "logical_count": 8,
    "load_average_1m": 0.12,
    "load_average_5m": 0.08,
    "load_average_15m": 0.04
  },
  "memory": {
    "available": true,
    "total_bytes": 17179869184,
    "available_bytes": 8589934592,
    "used_bytes": 8589934592,
    "used_percent": 50.0
  },
  "uptime": {
    "available": true,
    "seconds": 12345.67
  },
  "issues": [],
  "overall": "pass"
}
```

### Text example

```
$ maops-py inventory system
MAOps Python DevOps Toolkit - System Inventory
Version:               0.7.0
Hostname:              myhost
OS:                    Linux 6.8.0
OS version:            #1 SMP ...
Machine:               x86_64
Distribution:          Ubuntu 24.04
Python:                3.12.3 (CPython)
Python executable:     /home/user/.venv/bin/python
CPU logical count:     8
Load average (1/5/15): 0.12 0.08 0.04
Memory used:           50.0% of 17179869184 bytes
Uptime:                12345.67s

Issues:

Overall status: PASS
```

## `inventory filesystem`

```bash
maops-py inventory filesystem
maops-py inventory filesystem PATH
maops-py inventory filesystem PATH --format text
maops-py inventory filesystem PATH --format json
maops-py inventory filesystem PATH --max-depth INTEGER
maops-py inventory filesystem PATH --max-entries INTEGER
maops-py inventory filesystem PATH --top INTEGER
```

`PATH` is optional (defaults to the current working directory); at most
one path may be given, since the CLI accepts a single optional
positional. See `docs/filesystem-inventory-safety.md` for the complete
traversal, symlink, and same-filesystem contract, and for the meaning of
every summary field.

### Exit-code behavior

`0` for a successfully-produced report, regardless of any per-entry
issues encountered (a permission-denied subdirectory, a raced-away file,
etc. — these become `issues` entries and set `overall` to `"warn"`, but
never affect the exit code). `1` only when the root path itself cannot be
classified at all — it doesn't exist, or it isn't accessible. `2` for a
CLI usage error: an out-of-range or unparseable `--max-depth`/
`--max-entries`/`--top`, or more than one path argument.

## No subprocess/network boundary

Neither `inventory system` nor `inventory filesystem` imports
`subprocess` or `socket`. Collection is pure `platform`/`os`/`pathlib`
introspection — see `.claude/CLAUDE.md` and `docs/best-practices.md` for
the repository-wide safety restrictions this satisfies.

## Limitations

- No timestamp is attached to a report in this release.
- `inventory system`'s distribution/memory/uptime fields are Linux-only
  by nature of their data sources (`/etc/os-release`, `/proc/meminfo`,
  `/proc/uptime`); other platforms report these blocks as unavailable
  rather than fabricating equivalent data.
- `inventory filesystem` reports apparent file sizes (`st_size`), not
  allocated disk blocks — see `docs/filesystem-inventory-safety.md`.
- Neither command reads the toolkit's own configuration file: `--format`
  always defaults to `text` (like `doctor`), never the configured
  `output_format` — a broken configuration file must never affect either
  command's exit code.
