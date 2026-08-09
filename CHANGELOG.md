# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-08-08

Adds bounded HTTP and TCP availability ("health") checks — the toolkit's
first feature permitted to make network connections. Network access is
isolated to two new modules (`core/health_http.py`, `core/health_tcp.py`)
plus a bounded-concurrency helper (`core/health_runner.py`); every existing
module (`doctor`, `config`, `tools`, `runner` outside its established
subprocess use, `inventory`, `logs`) retains its existing network
prohibition, verified by a dedicated regression test. `health http` and
`health tcp` check only explicitly supplied endpoints — no CIDR expansion,
subnet/host discovery, port ranges, URL globbing, arbitrary port lists, raw
packets, ICMP, SYN scanning, or banner grabbing. This is an availability
checker, not a vulnerability scanner. The toolkit remains
standard-library-only at runtime. Also resolves the ten Day 4
carry-forward findings deferred to this release.

### Added

- `maops-py health http URL [URL ...] [--method GET|HEAD]
  [--expect-status STATUS|STATUS-STATUS] [--timeout SECONDS] [--retries N]
  [--retry-delay SECONDS] [--workers N] [--format text|json]` — bounded HTTP
  availability checks via `http.client` (never `urllib.request`, avoiding
  implicit proxy/redirect behavior). HTTPS always validates certificates
  and hostnames via `ssl.create_default_context()` with no relaxation and
  no `--insecure` option; redirects are never followed; only GET/HEAD are
  supported with no request body; response bodies and headers are never
  read or serialized. URL userinfo is rejected as a usage error; query
  parameter values are redacted in reports while key order is preserved
  (see `docs/http-health-safety.md`).
- `maops-py health tcp TARGET [TARGET ...] [--timeout SECONDS]
  [--retries N] [--retry-delay SECONDS] [--workers N] [--format
  text|json]` — bounded, connect-only TCP checks (`hostname:port`,
  `IPv4:port`, `[IPv6]:port`). No application data is sent, no banner is
  read, and no TLS handshake is performed.
- Deterministic per-target retry policy: `attempts = retries + 1`, a fixed
  (non-jittered) retry delay, and explicit PASS (succeeds on first
  attempt) / WARN (fails then recovers on retry) / FAIL (never recovers)
  classification, rolling up to a report-level `overall` and CLI exit code
  (`0` for pass/warn, `1` for fail, `2` for usage/target-validation
  errors). A service that recovers during retries is treated as degraded
  but available.
- Bounded concurrency via `concurrent.futures.ThreadPoolExecutor` (1-32
  workers, 1-100 targets per invocation): one worker per target, retries
  run sequentially inside that worker, and report ordering always matches
  original CLI target order regardless of completion order.
- New typed models in `core/health_models.py` (`HealthProtocol`,
  `HttpMethod`, `HttpFailureReason`, `TcpFailureReason`, and their
  supporting frozen dataclasses/reports), with a closed, deterministic
  failure taxonomy (`dns_error`, `timeout`, `connection_refused`,
  `connection_error`, `tls_error`, `http_protocol_error`,
  `unexpected_status`, `invalid_target_encoding`) — arbitrary exception
  text is never copied into a report; unexpected programming exceptions
  are never silently converted into a network failure. A malformed-label
  hostname (e.g. a stray double dot) or a non-ASCII URL path/query
  character now degrades to `invalid_target_encoding` instead of crashing
  the whole multi-target run with an uncaught `UnicodeError`/
  `UnicodeEncodeError` (found and fixed during pre-release review; see
  `docs/engineering-reviews/day-05-release-readiness-followup.md`).
- `docs/health-checks.md` and `docs/http-health-safety.md` documenting
  HTTP/TCP target syntax, retry/concurrency semantics, exit codes, the
  retryable-status set, peer-IP behavior, loopback/private-endpoint
  support, and the safety model in full.

### Fixed

Resolves the following findings deferred from the Day 4 engineering
reviews:

- Quoted `key="value with spaces"`-style secrets are now fully redacted
  end-to-end instead of stopping at the first embedded whitespace
  character (Day 4 finding).
- A log line truncated mid-line by `--max-bytes` is now marked as a
  distinct, structured truncation fragment and skipped, rather than being
  silently decoded as if it were a complete short line (Day 4 finding).
- `make smoke-install` now asserts the log fixture's synthetic secret is
  absent from `logs parse`/`logs analyze` JSON output, rather than only
  validating JSON syntax (Day 4 finding).
- RFC 3339 timestamps with a lowercase trailing `z` (in addition to the
  already-supported lowercase `t` date/time separator) now parse and
  normalize correctly instead of being rejected (Day 4 finding).
- Purely decimal 8+-digit tokens (e.g. an order ID) in log message
  signatures now normalize to `<num>` instead of being misclassified as
  `<hex>` (Day 4 finding).
- JSONL and syslog `pid` values are now bounded to `0-2147483647`; an
  out-of-range value degrades to a structured invalid-field issue instead
  of being serialized verbatim (Day 4 finding).
- `logs parse`'s text output now renders the already-modeled `hostname`
  field per event (Day 4 finding).
- `docs/inventory.md`'s example output no longer shows a stale `0.3.0`
  version value (Day 4 finding).
- Test-quality cleanup: replaced infrastructure-load-dependent wall-clock
  assertions in the redaction bounded-behavior tests with deterministic
  correctness assertions; added a live `AF_UNIX` special-file rejection
  test for the log reader (previously only mocked); centralized the
  duplicated `_isolated_config_env` test fixture into a shared
  `tests/conftest.py` (Day 4 finding).

### Changed

- `docs/subprocess-safety.md`'s "Exit-code and warning semantics across
  commands" table gains rows for `health http`/`health tcp`.

## [0.4.0] - 2026-08-06

Adds bounded, typed, structured log parsing and deterministic operational
event analysis, complementing `inventory` (host/filesystem facts) with
read-only insight into log file content. `logs parse` turns a JSONL or
syslog file into typed, redacted events with a per-line issue trail;
`logs analyze` streams the same input into deterministic severity/source
counts, normalized message signatures, fixed-duration time-bucket peaks,
and threshold-based findings. This performs deterministic parsing,
aggregation, and threshold comparisons only — it makes no machine
learning, artificial intelligence, behavioral detection, or general
anomaly detection claim. The toolkit remains standard-library-only at
runtime.

### Added

- `maops-py logs parse PATH [--input-format auto|jsonl|syslog] [--format
  text|json] [--max-lines N] [--max-bytes N] [--max-line-bytes N]
  [--max-events N] [--no-redact]` — parses a single log file into a
  structured report of typed events and parse issues. `core/log_reader.py`
  opens the file with `O_NOFOLLOW`/`O_CLOEXEC` where available, verifies
  the descriptor with `os.fstat()` against the pre-open `os.lstat()`
  result (rejecting symlinks, directories, and non-regular files, and
  detecting a path replaced between check and open), and reads bounded,
  sequential binary chunks — never `mmap`, never a whole-file read.
  Overlong lines are skipped without retaining their content. Secret
  values (bearer tokens, `password`/`token`/`api_key`-style fields, URI
  userinfo passwords) are redacted from event messages by default; report
  fields never contain a complete unredacted raw line (see
  `docs/log-redaction.md`).
- `maops-py logs analyze PATH [--input-format ...] [--format ...] [--top
  N] [--bucket-seconds N] [--repeat-threshold N] [--error-threshold N]
  [--no-redact]` — streams the same bounded input into severity counts,
  source counts, normalized top message signatures, a peak fixed-duration
  UTC time bucket, and deterministic advisory findings (repeated
  signatures, error-volume, unknown severities, out-of-order timestamps,
  truncation). Individual events are never retained for analysis; only
  small per-distinct-value aggregates are kept in memory (see
  `docs/log-analysis.md`).
- New typed models in `core/log_models.py` (`LogSeverity`,
  `LogInputFormat`, `LogParseIssueCode`, `LogAnalysisFindingCode`,
  `LogEvent`, `LogParseReport`, `LogAnalysisReport`, and their supporting
  frozen dataclasses), parsing in `core/log_parsers.py` (JSONL field-alias
  resolution, a staged syslog grammar with PRI/RFC3339/BSD-timestamp
  handling, and per-line `auto` format detection), and bounded regex
  redaction in `core/log_redaction.py`.
- `docs/log-parsing.md`, `docs/log-analysis.md`, and
  `docs/log-redaction.md` documenting accepted formats, JSONL aliases,
  syslog limitations, timestamp handling, severity normalization,
  file limits, redaction patterns, output schemas, and exit codes.

### Changed

- `docs/subprocess-safety.md`'s "Exit-code and warning semantics across
  commands" table gains rows for `logs parse`/`logs analyze`.

## [0.3.0] - 2026-08-05

Adds typed, structured, read-only system and filesystem inventory,
complementing `doctor` (environment usability) and `tools inspect` (fixed
external-tool version checks). Inventory collection is pure local
introspection: no subprocess execution, no network or socket use, and no
environment-variable reads. Also resolves the majority of the Day 2
engineering-review findings. The toolkit remains standard-library-only at
runtime.

### Added

- `maops-py inventory system [--format text|json]` — host, OS,
  distribution, Python, CPU, memory, and uptime facts collected via
  `platform`/`os` introspection only. Optional data (Linux distribution
  metadata, CPU load averages, `/proc/meminfo`, `/proc/uptime`) degrades to
  an explicit `null` plus a structured warning issue when unavailable or
  malformed, rather than being fabricated or omitted; the command's exit
  code reflects only whether a report could be produced at all, never
  individual optional-field warnings (see `docs/inventory.md`).
- `maops-py inventory filesystem [PATH] [--format text|json] [--max-depth
  N] [--max-entries N] [--top N]` — a bounded, deterministic, read-only
  filesystem tree summary. Never follows symbolic links, never crosses
  mount points (`st_dev` boundary), never reads file content or computes
  hashes, and never invokes an external command. Defaults: current working
  directory, max depth `2`, max entries `10000`, top `10` largest files.
  Per-entry race conditions (`FileNotFoundError`, `PermissionError`,
  `NotADirectoryError`) become structured issues rather than aborting the
  scan; only a nonexistent or unreadable root is an operational failure
  (see `docs/filesystem-inventory-safety.md`).
- New typed models in `core/inventory_models.py` (`InventoryIssue`,
  `HostInfo`, `DistributionInfo`, `SystemPythonInfo`, `CpuInfo`,
  `MemoryInfo`, `UptimeInfo`, `SystemInventoryReport`,
  `FilesystemScanOptions`, `FilesystemScanSummary`, `LargestFileEntry`,
  `FilesystemInventoryReport`), following the existing frozen-dataclass,
  explicit-serialization, tuple-collection conventions.
- New documentation: `docs/inventory.md`, `docs/filesystem-inventory-safety.md`.

### Changed

- `docs/subprocess-safety.md` now documents exit-code and warning
  semantics across every command: `doctor`'s optional-tool warnings never
  affect its exit code; `tools inspect`'s warnings do (a single missing
  requested tool fails the whole invocation, by original design);
  `inventory system`/`inventory filesystem` warnings never affect their
  exit code (only a failure that prevents a meaningful report at all
  does). This clarifies a previously undocumented divergence between
  `doctor` and `tools inspect` (Day 2 finding).
- `--version`'s documented short-circuit behavior is narrowed to describe
  its actual, always-true contract precisely: it short-circuits whenever
  `parser.parse_args()` succeeds; an incomplete two-level command group
  given with no leaf subcommand (`config`, `tools`, or the new
  `inventory`) is a usage error argparse raises during parsing itself,
  before `--version` is ever inspected, and always exits `2` regardless of
  `--version`'s position on the command line. Previous release notes and
  docs stated an unconditional short-circuit without this exception (Day 2
  finding).
- Configuration validation error messages for `command_timeout_seconds`
  and `max_output_bytes` now name the actual received type (e.g. "not
  string", "not a list", "not a float") instead of always saying "not
  boolean," which was misleading for non-boolean wrong-type values. The
  message for genuinely boolean values is unchanged. Exit codes and valid
  behavior are unaffected (Day 2 finding).

### Fixed

- `tests/integration/test_release_permissions.py` and
  `test_release_artifacts.py` no longer build into the shared repository
  `dist/` directory (which `make build` empties via `rm -rf` on every
  invocation); both now build into an isolated, `tmp_path`-scoped output
  directory via `python -m build --outdir`, eliminating a race under any
  concurrent build/test run against the same working tree. `make build`
  and CI's `make release-check` are unaffected (Day 2 finding).
- JSON field-type coverage for `tools inspect` and `config show` is now
  exhaustive: every field of `ToolInspectionResult`, its `configuration`
  block, and `ConfigShowReport`'s `values`/`sources` blocks is now
  asserted for type (previously several fields, including `status`,
  `stderr`, `stdout_truncated`, and `sources.command_timeout_seconds`,
  were unchecked). The two new inventory report types ship with the same
  completeness standard from day one (Day 2 finding).
- `tests/unit/test_no_network_runner.py`'s
  `test_tools_inspect_makes_no_network_calls` now resolves a real,
  on-disk stub executable so the real `run_command()` subprocess path
  genuinely executes under the socket guard, rather than short-circuiting
  on a missing-executable branch that never reached subprocess execution
  at all (Day 2 finding).
- Added `MANIFEST.in` (`prune src/*.egg-info`), removing five of the seven
  `src/maops_pydevops.egg-info/` entries that previously leaked into the
  sdist (`PKG-INFO`, `dependency_links.txt`, `entry_points.txt`,
  `requires.txt`, `top_level.txt`). The remaining `SOURCES.txt` (and its
  containing directory) is unconditionally force-included by setuptools'
  own sdist/egg_info integration — verified empirically to survive even
  an explicit `MANIFEST.in` `exclude` directive targeting it directly — and
  is standard, required metadata for every setuptools-built sdist, not a
  defect (Day 2 finding, carried forward two releases; now closed).

## [0.2.0] - 2026-08-04

Adds typed configuration management and a reusable, safe subprocess execution
layer, demonstrated through an allowlisted, read-only tool-inspection
command. The toolkit remains standard-library-only at runtime.

### Added

- TOML configuration support (`tomllib`, stdlib) with a default path of
  `$XDG_CONFIG_HOME/maops-py/config.toml`, falling back to
  `$HOME/.config/maops-py/config.toml`, overridable via
  `MAOPS_PY_CONFIG_FILE`. Supported keys: `output_format`,
  `command_timeout_seconds`, `max_output_bytes`, with strict schema
  validation (unknown keys, malformed TOML, duplicate keys, and
  bool-as-numeric values are all rejected).
- `maops-py config path` / `config init [--force]` / `config validate
  [PATH]` / `config show [--format text|json]` — secure, atomic
  configuration file management (mode `0600`, symlink/directory refusal,
  `os.replace`-based atomic installation) and effective-configuration
  introspection with full source attribution (`cli` / `environment` /
  `file` / `default`).
- Typed CLI/environment/file/default configuration precedence resolution,
  with invalid environment values failing operationally rather than
  silently falling back to a lower-precedence source.
- `src/maops_pydevops/core/runner.py` — a reusable, safe subprocess
  execution layer (`shell=False`, `stdin=DEVNULL`, separate stdout/stderr
  capture, configurable timeout, monotonic-clock duration, UTF-8-with-
  replacement decoding, byte-based output truncation, fixed noninteractive
  child environment). No arbitrary command-execution CLI is exposed.
- `maops-py tools inspect [TOOL...] [--format text|json] [--timeout
  SECONDS]` — allowlisted, read-only version checks for `git`, `docker`,
  `kubectl`, `terraform`, and `ansible`, using fixed argv definitions
  executed via the safe runner.
- New documentation: `docs/configuration.md`, `docs/subprocess-safety.md`.

### Changed

- `--version` now always short-circuits, even when a subcommand is also
  supplied (e.g. `maops-py --version doctor` prints only the version and
  exits `0`; `doctor` never runs). Previously `--version` was silently
  ignored once a subcommand was present. `maops-py doctor --version`
  remains an unrecognized-argument usage error (exit `2`), unchanged.

### Fixed

- `maops-py tools inspect` with no explicit tool names (and thus no
  positional arguments at all) raised `argparse.ArgumentError: invalid
  choice: []` under Python 3.11's argparse, while working correctly under
  3.12 — a version-dependent interaction between `nargs="*"`, `choices=`,
  and an implicitly-`None` default on a required-by-default positional.
  Tool-name validation is now performed explicitly in
  `run_tools_inspect()` instead of via argparse `choices=`, which sidesteps
  the cross-version inconsistency entirely; unsupported tool names still
  exit `2` with a clear error message.

## [0.1.0] - 2026-08-03

Initial release of the MAOps Python DevOps Automation Toolkit. Establishes
the packaging, CLI, and diagnostics foundation for Project 2 of the MAOps
DevOps portfolio.

### Added

- `src`-layout package `maops_pydevops`, installable with `pip install -e ".[dev]"`,
  targeting Python 3.11+, with a CI matrix configured to validate 3.11,
  3.12, 3.13, and 3.14 on every push (locally exercised on 3.12 so far;
  see the CI workflow run history for actual multi-version results).
- Console script `maops-py`, with `python -m maops_pydevops` invoking the
  identical CLI through a single shared entry point.
- `maops-py doctor` — a read-only, network-free environment diagnostic
  command with `text` (default) and `json` output formats, covering
  supported Python version, package import, supported OS family,
  temporary-directory availability, filesystem encoding, and Python
  executable resolution as required checks, and git/docker/kubectl/
  terraform/ansible presence as optional (warn-only) checks.
- `maops-py version` / `maops-py --version` for toolkit version reporting,
  backed by a single authoritative version source in `pyproject.toml`.
- Exit-code convention: `0` success, `1` operational/required-check
  failure, `2` CLI usage error.
- Typed, immutable core models (`CheckStatus`, `OutputFormat`,
  `PythonInfo`, `PlatformInfo`, `DoctorCheck`, `DoctorReport`) with
  explicit serialization.
- Full local quality gate via `Makefile` (`format`, `lint`, `type-check`,
  `test`, `coverage`, `build`, `smoke-install`, `quality`,
  `release-check`).
- GitHub Actions workflow `Python Validation`, running `make
  release-check` across the full Python support matrix with pinned,
  read-only-permission Actions.
