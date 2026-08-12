# Security Policy

## Supported release

Only the latest tagged release (currently **v0.7.0**, the final planned
release in this project's seven-day portfolio arc — see
[docs/roadmap.md](docs/roadmap.md)) is supported. There is no long-term
support branch and no backport policy: a fix, if one is ever needed,
would land in a new tagged release built from `main`, not a patch to an
older tag.

## Reporting a vulnerability

This is a portfolio project with no dedicated security team and no
service-level response commitment. If you find a security issue, please
open a [GitHub issue](../../issues) on this repository describing the
problem, or open a private security advisory via GitHub's "Report a
vulnerability" feature under the repository's Security tab if the finding
is sensitive enough that you would prefer it not be public immediately.
There is no separate security-contact email address for this project —
use one of the two channels above.

Please include:

- The command line or API call that reproduces the issue.
- The observed behavior versus the expected (documented) behavior.
- Which security boundary (see below) you believe is affected.

There is no bug-bounty program and no guaranteed disclosure timeline.
Given the project's scope (a local, read-only diagnostics CLI with one
narrowly scoped network feature), the realistic severity ceiling for any
finding is display/parsing-integrity or a local-filesystem-safety defect,
not remote code execution or credential theft — the architecture in this
document is deliberately built to make those latter classes structurally
unreachable rather than merely discouraged.

## Security boundaries

`maops-py` is a **read-only diagnostics and reporting toolkit**. Its
security model rests on a small number of hard architectural boundaries,
each enforced by a dedicated regression test, not only by convention:

### No shell, no arbitrary command execution

There is no `shell=True`, `os.system`, `eval`, or `exec` anywhere in
`src/`. `core/runner.py` is the **only** module permitted to import
`subprocess`, and it is only ever invoked with one of five fixed,
hardcoded argv tuples (`git`/`docker`/`kubectl`/`terraform`/`ansible`
version checks), each resolved to an absolute path via `shutil.which()`
first. No CLI flag, environment variable, or configuration key accepts an
arbitrary command at any layer of this package — see
[docs/subprocess-safety.md](docs/subprocess-safety.md).

### The workflow file is data, not code

`maops-py workflow run` executes a declarative TOML file describing a
fixed, closed set of seven step kinds. A workflow step is parsed into a
typed, frozen dataclass and dispatched to the package's own existing
`build_*_report()` functions — never a shell command, never a recursive
`maops-py` subprocess, never `eval`/`exec`, dynamic imports, templating,
loops, conditions, or scheduling. A shell-metacharacter-laden field
(`` $(...) ``, backticks, `;`, `|`, redirects, `${HOME}`, `&&`) is
preserved verbatim as inert literal text and, at most, produces a
"path not found"-style `FAIL` step result — it is never interpreted.
See [docs/workflow-security.md](docs/workflow-security.md) and
`tests/unit/test_workflow_shell_metacharacter_inertness.py` for the
regression proof.

### Network boundary

Every command in this toolkit is local-only, **except** `maops-py health
http`/`health tcp` (and their orchestration through `workflow run`'s
`health_http`/`health_tcp` step kinds and `report aggregate`'s
normalization of their output). `core/health_http.py` and
`core/health_tcp.py` are the only two modules in the package permitted to
import `socket`, `ssl`, or `http.client`; `core/health_runner.py` is the
only module permitted to import `concurrent.futures`. Every other module
— enforced by `tests/unit/test_no_network_health_boundary.py` — makes
zero network calls of any kind.

Within that boundary: HTTPS always validates certificates and hostnames
via `ssl.create_default_context()` with no attribute relaxation anywhere
— there is no `--insecure` flag and no other certificate-verification
bypass. Redirects are never followed. Only `GET`/`HEAD` are supported,
never with a request body, and there is no way to inject a custom header
or credential. Response bodies and headers are never accessed. TCP checks
are connect-only (`socket.create_connection()` + `getpeername()` +
`close()` — no `send`/`recv`). See
[docs/http-health-safety.md](docs/http-health-safety.md).

### Redaction and privacy expectations

`logs parse`/`logs analyze` apply best-effort secret redaction to the
`message` field by default (disableable via `--no-redact`) against a
fixed, documented pattern set — this is a mitigation, not a completeness
guarantee; do not rely on it as the sole control over sensitive log
content. See [docs/log-redaction.md](docs/log-redaction.md).

`health http` redacts query-string *values* (never keys or ordering) in
every report representation, while the real, unredacted value still
reaches the target server on the wire — the redaction is a reporting-
output property, not a request-modification one. `workflow run`'s
`health_http` step goes further: its normalized report never includes the
target URL at all, only pass/warn/fail counts, so there is no redacted
field to leak in the first place. See
[docs/http-health-safety.md](docs/http-health-safety.md) and
`tests/integration/test_workflow_health_loopback.py`.

Every text and Markdown report renderer passes externally sourced strings
(a file path, a workflow name, a step id, a log message, a hostname)
through a shared sanitization boundary that escapes control characters,
Unicode bidi-override/zero-width formatting characters, and (Markdown
only) Markdown-syntax-significant characters — preventing forged report
lines or injected Markdown/HTML. JSON output is intentionally unaffected
(`json.dumps` already escapes correctly). See
[docs/aggregated-reports.md](docs/aggregated-reports.md#markdown-escaping-rationale).

### Filesystem and symlink protections

Every module that reads file *content* (`core/log_reader.py`,
`core/report_reader.py`) follows the same fd-safety pattern: `os.lstat()`
pre-check (rejecting a nonexistent path, directory, symlink, or special
file outright), an `O_NOFOLLOW`/`O_CLOEXEC` open, and an `os.fstat()`
verification against the pre-open `lstat()` result (`(st_dev, st_ino)`
comparison) to detect a path replaced between the check and the open.
Reads are bounded and sequential — never `mmap`, never a whole-file read.

`inventory filesystem` never follows a symbolic link, never crosses a
mount-point boundary, and never reads file content or computes a hash —
metadata only (`os.lstat`/`os.scandir`/`entry.stat`). See
[docs/filesystem-inventory-safety.md](docs/filesystem-inventory-safety.md).

Every code path that writes a file outside a build/test temp directory
(`core/config.py`'s `config init`, `commands/report.py`'s
`write_report_output()` for `report aggregate --output`/`workflow run
--output`) writes to a sibling temporary file first, then installs it
atomically via `os.replace()` — whose underlying `rename(2)` semantics
never dereference the destination path's final component, structurally
defeating the symlink-race class of TOCTOU attack rather than merely
narrowing its window. A symbolic link at the target path is always
refused, even with `--force`.

### Dependency philosophy

The runtime dependency list in `pyproject.toml` is empty and has been
empty across all seven releases (v0.1.0 through v0.7.0) — everything is
Python standard library. This is a deliberate security and supply-chain
posture, not an oversight: fewer runtime dependencies means fewer
transitive vulnerabilities, fewer version-pinning decisions, and no
third-party package to compromise or typosquat. The `dev` optional-
dependency group (`pytest`, `ruff`, `mypy`, `build`) is development/CI
tooling only and is never installed at runtime by an end user of the
published wheel.

## What this project does **not** guarantee

- **Not a hardened multi-tenant service.** `maops-py` is a single-user
  CLI tool, not a daemon, server, or API. There is no authentication,
  authorization, or multi-tenancy model, because there is no persistent
  service to protect.
- **Not a substitute for a real secret scanner.** The redaction described
  above is best-effort against a fixed pattern set; a determined secret
  format outside that set will not be caught.
- **Not a sandbox.** `tools inspect`'s five allowlisted version-check
  invocations run with the same privileges as the invoking user, subject
  to a bounded timeout and truncated output — this is process isolation
  appropriate to a version-check command, not a security sandbox.
- **No protection against a compromised Python interpreter or an
  already-compromised host.** This toolkit assumes it runs on a host and
  interpreter you already trust; it defends the boundaries it creates
  (subprocess, network, filesystem writes), not the underlying platform.
- **No update or vulnerability-scanning mechanism.** There is no
  auto-update, telemetry, or phone-home behavior of any kind — installing
  a new version is always a manual, explicit action by the user.
