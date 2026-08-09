# Day 5 v0.5.0 HTTP/TCP Health-Check Architecture and Security Review

**Project:** MAOps Python DevOps Automation Toolkit (`maops_pydevops`,
console command `maops-py`)
**Reviewer:** Independent engineering review, direct hands-on verification.
Every command, test run, and adversarial input in this document was
executed by the reviewing session itself against the real source on this
branch (Python 3.12.3, package built and installed into an isolated
scratch virtualenv), including live loopback-only network exercises
against real, ephemeral `127.0.0.1`/`::1` servers spun up for this review
— no public internet host was ever contacted, and no finding here is
inferred, estimated, or taken from the implementing session's own claims
or docstrings.
**Date:** 2026-08-09
**Branch reviewed:** `feature/day-5-health-checks`
**Scope:** The Day 5 delta only — `core/health_http.py`, `core/health_tcp.py`,
`core/health_runner.py`, `core/health_models.py`, `commands/health.py`, the
`health` CLI surface in `cli.py`, the `render_health_*` additions to
`core/output.py`, `docs/health-checks.md`, `docs/http-health-safety.md`,
and `scripts/smoke/health_smoke_check.py`. Day 1–4 functionality is treated
as regression-protected (full suite re-run below confirms no regression)
and was not re-audited from scratch.
**Review only. No implementation file was modified.** No commit, push,
tag, or publish was performed as part of this review.

---

## Commands and live checks run

```
python -m pytest tests/unit tests/integration -q \
    --cov=src/maops_pydevops --cov-report=term-missing
python -m mypy src/maops_pydevops --strict
grep -n "import subprocess|import socket|import ssl|urllib.request|requests|httpx" \
    src/maops_pydevops/core/health_*.py src/maops_pydevops/commands/health.py
```

Result: **998 passed**, **99.05% overall coverage** (`core/health_http.py`
94%, `core/health_tcp.py` 97%, `core/health_runner.py` 100%,
`core/health_models.py` 100%, `commands/health.py` 97% — the handful of
uncovered lines are minor defensive branches, listed under "What holds up
well"), **mypy --strict: no issues in 30 source files**, **zero**
subprocess/third-party-HTTP-library references anywhere in the `health`
command tree (also independently confirmed by the existing
`test_health_no_forbidden_tokens.py`/`test_no_network_health_boundary.py`
suites, both re-run and re-read line by line).

Plus a from-scratch, hand-written live-exercise script (not a re-run of
the existing test suite) that started real ephemeral servers bound to
`127.0.0.1`/`::1` only — a plain HTTP 200 server, a 302-redirecting
server, a self-signed-certificate HTTPS server, a slow/timeout server, a
flaky-then-recovers server, a 404 server, and a raw TCP listener — and
drove the installed `maops-py` executable against them as real
subprocesses, inspecting stdout/stderr/exit codes/timing. All of the
following were independently verified to work as documented: query-value
redaction in reports vs. the real (unredacted) query actually sent on the
wire; userinfo rejection; control-character rejection; unsupported-scheme
rejection; redirects never followed (the redirect handler was hit exactly
once); `HTTP_PROXY`/`http_proxy` environment variables fully ignored;
self-signed HTTPS correctly classified as `tls_error`; WARN-on-recovery
retry semantics with a fixed (non-jittered) retry delay; timeout
classification; deterministic result ordering under concurrency (a
slow first target's result still appeared first in the report); a `404`
response never retried; TCP connect-only behavior with no banner/body
read; every CIDR/port-range/comma-port/unbracketed-IPv6 TCP scanning
affordance rejected; bracketed-IPv6-loopback (`[::1]:PORT`) accepted and
connected; and the 1–100 target-count bound enforced before any socket
opens.

**Headline result: three independent, live-reproduced crash vectors were
found, all in the same class — an unencoded non-ASCII/malformed-label
string anywhere in a target's hostname, URL path, or URL query crashes
the entire `health http`/`health tcp` invocation with an unhandled Python
traceback, discarding the results of every other target in the same
invocation (even ones that already succeeded) and producing no report at
all.** This is the identical failure pattern flagged as Critical in the
Day 4 review of `core/log_parsers.py` (crafted-but-ordinary content
defeating a module's own "never raises on malformed input" contract) —
here it recurs one release later, in a different module, against
attacker- or simply careless-operator-supplied network targets instead of
log lines.

---

## Critical

### C1 — Uncaught `UnicodeError`/`UnicodeEncodeError` from non-ASCII or malformed-label targets crash the entire `health http`/`health tcp` run, discarding every target's result, not just the offending one

`docs/http-health-safety.md`'s "Failure classification" section states:
*"Only known, expected transport exceptions are converted into a
structured `failure_reason`. Every other exception (a programming error)
propagates uncaught rather than being silently folded into a
network-failure result."* The listed exception table covers
`socket.gaierror`, `TimeoutError`, `ConnectionRefusedError`,
`ssl.SSLError`, `http.client.HTTPException`, and a generic `OSError`
catch-all — `_perform_http_attempt` (`core/health_http.py:208-295`) and
`_perform_tcp_attempt` (`core/health_tcp.py:127-161`) catch exactly this
set and nothing else, matching the doc precisely.

The problem is the framing, not the code: describing "every other
exception" as *"a programming error"* is false for at least three
distinct, independently live-reproduced inputs — all syntactically valid
per this package's own target grammar (they pass `validate_http_target`/
`validate_tcp_target`'s control-character and structural checks cleanly)
and all plausible *operator* input, not deliberate attacks or interpreter
bugs:

**PoC 1 — a hostname with an empty DNS label (a stray double dot, e.g. a
templating bug producing `internal..svc.cluster.local`) →
uncaught `UnicodeError` from the stdlib `idna` codec, for *both*
protocols:**

```
$ maops-py health http "http://example..com/" --retries 0 --format json
Traceback (most recent call last):
  ...
  File ".../core/health_http.py", line 244, in _perform_http_attempt
    conn.connect()
  File ".../http/client.py", line 1030, in connect
    self.sock = self._create_connection(...)
  File ".../socket.py", line 828, in create_connection
    for res in getaddrinfo(host, port, 0, SOCK_STREAM):
  File ".../encodings/idna.py", line 173, in encode
    raise UnicodeError("label empty or too long")
UnicodeError: label empty or too long
encoding with 'idna' codec failed

$ maops-py health tcp "example..com:80" --retries 0 --format json
Traceback (most recent call last):
  ...
  File ".../core/health_tcp.py", line 141, in _perform_tcp_attempt
    sock = socket.create_connection((target.host, target.port), timeout=timeout_seconds)
  ...
  File ".../encodings/idna.py", line 173, in encode
    raise UnicodeError("label empty or too long")
```

`socket.getaddrinfo()` always runs a `str` hostname through the `idna`
codec (RFC 3490 `ToASCII`), even for a purely-ASCII string — this is not
specific to genuinely non-ASCII input. Neither `validate_http_target` nor
`validate_tcp_target` rejects an empty label, an over-length label
(64+ octets), or any of the other conditions `encodings.idna.ToASCII`
enforces, so this is reachable through the package's normal, documented
CLI surface with zero exotic characters.

**PoC 2 — a literal non-ASCII character anywhere in the URL *path or
query* (not just the hostname) → uncaught `UnicodeEncodeError`, entirely
independent of DNS/IDNA, and reachable even against a target that is
otherwise reachable and healthy:**

```
$ maops-py health http "http://127.0.0.1:<port>/‮abc" --retries 0 --format text
Traceback (most recent call last):
  ...
  File ".../http/client.py", line 1294, in _encode_request
    return request.encode('ascii')
UnicodeEncodeError: 'ascii' codec can't encode character '‮' in position 5: ordinal not in range(128)
```

`http.client.HTTPConnection._encode_request()` requires the full request
line to be pure ASCII; `validate_http_target` never rejects or
percent-encodes a non-ASCII path/query character, so a plainly plausible
real-world value (an accented character, CJK text, an emoji, or a copy-
pasted bidi-control character in a query parameter) triggers this on a
server that is otherwise up and would have returned `200`.

**PoC 3 — one bad target discards every other target's already-obtained
result in the same invocation**, live-verified against a two-target
invocation (one healthy server, one `example..com`):

```
$ maops-py health http "http://127.0.0.1:<healthy-port>/" "http://example..com/" \
      --retries 0 --format json
# returncode: 1, stdout: '' (empty — no JSON, no partial report at all)
```

`run_bounded_parallel` (`core/health_runner.py:41-42`) iterates
`concurrent.futures.as_completed(...)` and calls `future.result()`
directly inside the loop; the first future whose worker raised propagates
that exception immediately out of `run_bounded_parallel`, out of
`build_health_http_report`, and out of `run_health_http`, with no
`except` clause anywhere on that path (confirmed by direct trace of
`commands/health.py:94-97` and `cli.py:812-824` — neither wraps the call).
The `ThreadPoolExecutor` context manager still waits for every submitted
future to finish before the exception is re-raised (so a slow healthy
target's socket work is not abandoned mid-flight), but its result is
discarded — the operator gets a raw Python traceback on stderr and empty
stdout instead of a report where 99 good targets `pass` and one bad
target reports a structured `dns_error`/`fail`.

**Why this is Critical:** this is a network-facing health-check tool
whose whole purpose is to be pointed at operator-supplied lists of
endpoints — a typo'd hostname, a copy-pasted URL with a stray double dot,
or one non-ASCII character anywhere in a batch of otherwise-valid targets
is exactly the kind of everyday operator error this class of tool exists
to report *gracefully* (a `fail` row for the bad target), not to
DoS-crash on. In an automated pipeline (`maops-py health http $(cat
targets.txt) --format json`, piped into `jq`), a single malformed line in
`targets.txt` currently means the entire health-check run for every other
target silently produces no output and a bare exit code, which is a worse
failure mode than the documented `overall: "fail"`/exit-1 path and
directly undermines the "bounded, deterministic, ordered" guarantees this
module's own docstrings and `docs/health-checks.md` make about *every*
target always getting a result slot.

**Recommendation:** Add `UnicodeError` (which covers both
`UnicodeDecodeError` and `UnicodeEncodeError`, since IDNA and ASCII
request-line encoding both raise subclasses of it) as an explicitly
caught, narrow exception class in both `_perform_http_attempt` and
`_perform_tcp_attempt`, mapped to a new or existing `failure_reason`
(`dns_error` is a reasonable fit for the IDNA case; a new
`invalid_target`/`encoding_error` reason may fit the path/query case
better, since it isn't really a transport failure — it never got as far
as opening a socket for PoC 2). Separately, consider tightening
`validate_http_target`/`validate_tcp_target` to reject the specific
malformed-label conditions IDNA would reject (empty label, over-length
label/hostname) and non-ASCII path/query characters *at validation time*
(exit `2`, before any target list is accepted at all) rather than only
catching the exception post hoc — matching this package's existing
pattern of front-loading validation so "an invalid invocation never opens
a single socket." Whichever fix is chosen, add a regression test
exercising all three PoCs above through the real CLI (not just the
internal `_perform_*_attempt` functions), and update
`docs/http-health-safety.md`'s failure-classification table and its
"every other exception... is a programming error" framing to reflect
that this class of input is ordinary user error, not a programming bug.

---

## Medium

### M1 — Text-mode target/host sanitization strips ASCII C0/DEL control characters but not Unicode bidi-override or zero-width formatting characters

`_sanitize_for_text()` (`core/output.py:54-65`) and the pre-validation
`_CONTROL_OR_WHITESPACE` regex in both `core/health_http.py:42` and
`core/health_tcp.py:32` cover exactly `\x00`-`\x1f`, `\x7f`, and ASCII
whitespace. Neither covers Unicode formatting characters such as
`U+202E RIGHT-TO-LEFT OVERRIDE`, `U+200B ZERO WIDTH SPACE`, or other
bidi-control code points. In the live PoC 2 case above, the crash happens
before a report is ever produced — but the underlying gap is broader than
that one crash: any *successfully connecting* target whose URL path or
query contains such a character (for instance, a percent-encoded bidi
character that only gets decoded server-side, or a future fix to C1 that
makes non-ASCII path/query characters survive instead of crashing) would
carry that character straight into `display_url`/`.display` and from
there into a text-mode report line completely unescaped — JSON output is
incidentally safe today only because `json.dumps()`'s default
`ensure_ascii=True` (never overridden anywhere in `core/health_models.py`)
escapes every non-ASCII code point to `\uXXXX`, not because of any
deliberate design decision documented for this case the way
`_sanitize_for_text()` is documented for control characters.

**Recommendation:** Either broaden `_sanitize_for_text()` (or a
network-specific equivalent) to also escape Unicode bidi-control and
zero-width code points, or explicitly document today's ASCII-only scope
as a deliberate limitation. This is Medium rather than Critical/High
because the most direct way to reach it today is blocked by C1's crash
first — but it should be closed in the same change that fixes C1, since a
narrower fix to C1 (e.g., only rejecting the specific IDNA-error
conditions) would reopen exactly this path for successfully-encoding
Unicode content.

---

## Low

### L1 — `--retry-delay` is fixed and non-jittered across all workers, which is a documented, deliberate simplicity choice but has a real synchronized-retry-storm implication at the top of the allowed target/worker range

`docs/health-checks.md` explicitly documents "a fixed (non-jittered)
`--retry-delay`," and this was live-verified to behave exactly as
documented (a flaky-then-recovers target's total run time tracked the
configured delay closely). At the top of the allowed range — 100 targets,
32 workers, many failing simultaneously (e.g. a whole subnet's worth of
services down during an incident, which is precisely when this tool is
most likely to be run) — every worker's failed attempts wake up and retry
at the same fixed offset, producing a synchronized burst rather than a
smoothly staggered one. This is a minor, load-shape-only concern (bounded
to 100 targets, not thousands) and is explicitly a documented design
choice rather than an oversight, so it is recorded here for completeness
rather than as an action item.

### L2 — A handful of legitimate defensive branches are unexercised by the test suite

Coverage is 94–100% across every `health` module; the specific gaps
(`core/health_http.py` lines 96, 133–134, 145–146, 175, 178–179; the
`WARN`-overall branch and one line in `core/health_tcp.py`/
`commands/health.py`) are all genuinely-defensive, hard-to-trigger paths
(an empty query segment, `urlsplit()` raising `ValueError` on pathological
input, the `.hostname`/`.port` properties raising `ValueError`,
`getpeername()` raising `OSError` after a connection races closed,
and a TCP-only run producing an overall `WARN`). None were found to be
incorrect by direct code reading; this is a completeness note, not a
correctness finding — the codebase's own 90% coverage floor is
comfortably met (99.05% overall).

---

## Future

- **A `health` fuzz/property-based test module** (Hypothesis-driven,
  generating arbitrary Unicode/control-character/edge-case strings for
  the URL and `host:port` grammars) would have caught C1's three PoCs
  directly and is the same recommendation made in the Day 4 review for
  `core/log_parsers.py` — the fact that an equivalent "hostile content,
  not just hostile transport" gap has now been found in a second,
  independently-implemented module suggests this class of gap (any
  stdlib call with narrower input assumptions than this package's own
  validation layer) is worth a standing test-authoring policy across the
  whole CLI, not a one-off fix per module.
- **IDNA/Unicode-domain support is currently all-or-nothing and
  accidental** — a genuinely valid internationalized domain name that
  happens to encode successfully today works by IDNA-codec coincidence,
  not by design (there is no test or doc coverage of intentional IDN
  support). Worth an explicit decision in a future release: either
  document IDN as supported and add real coverage for it, or normalize/
  reject non-ASCII hostnames deliberately at validation time.

---

## What holds up well

Documented for balance, since a findings-only report understates what was
verified and passed — all of the following were confirmed by a
combination of direct code reading and live loopback exercises, not
assumed from documentation or docstrings:

- **Explicit endpoint-only design, no scanning/range affordances**: live-
  verified that CIDR notation, port ranges, comma-separated ports, and
  unbracketed IPv6 are all rejected as syntax errors (exit `2`) for TCP
  targets, and that `ipaddress.ip_network()`/subnet iteration appears
  nowhere in the module. Every check is exactly one connection attempt
  (or `retries + 1` sequential attempts to the *same* target).
- **Userinfo rejection and query redaction**: live-verified
  `http://user:pass@host/` is rejected before any connection is attempted,
  and that a query string with real secret-shaped values is redacted in
  both the JSON and text report's `target` field while the *actual*
  outbound request (confirmed via the test server's own access log) still
  used the real, unredacted query.
- **Redirects genuinely never followed**: live-verified against a real
  302-emitting server — the redirect handler was hit exactly once despite
  the client reporting `final_http_status: 302` and `overall: "fail"`;
  no second request to the `Location` target was ever made.
- **TLS verification is never relaxed**: live-verified against a real
  self-signed-certificate HTTPS loopback server — the attempt correctly
  fails with `failure_reason: "tls_error"` rather than silently
  succeeding, with no `--insecure` flag or other bypass present anywhere
  in the CLI surface (confirmed by `build_parser()` inspection) or in
  `core/health_http.py`'s `ssl.create_default_context()` call (zero
  attribute mutation, matching `test_health_http_attempt.py`'s existing
  source-scan guard).
- **No proxy-environment consultation**: live-verified — pointing
  `HTTP_PROXY`/`http_proxy` at an address nothing listens on had zero
  effect on a request that otherwise succeeds against the real loopback
  target, consistent with `http.client` (never `urllib.request`) being
  the sole HTTP call site.
- **No response-body or header retention, no banner reading**: live-
  verified against a server returning a custom `Server: SECRET-BANNER/9.9`
  header and a two-byte body — neither the header value nor the body
  content appears anywhere in the JSON report. Confirmed structurally by
  code reading that no model field exists that could hold either. TCP
  connect-only behavior (`create_connection` → `getpeername` → `close`,
  no `send`/`recv`) was independently confirmed against a real raw TCP
  listener.
- **DNS/connect failure classification and retry policy**: live-verified
  `timeout`, `tls_error`, and the WARN-on-recovery path (a target that
  fails once then succeeds is reported `warn` with `attempts_used: 2`,
  not `pass`); a `404` (outside the default expected-status range) fails
  immediately on the first attempt with no retries spent, matching the
  documented non-retryable-status list.
- **Fixed retry delay timing**: live-verified — one retry at a configured
  0.5s delay produced a total run time consistent with exactly one fixed
  delay, not exponential backoff or jitter.
- **Concurrency bound and deterministic result ordering**: live-verified
  with a two-target run where the *first* CLI argument was the slower
  target (artificially delayed past its timeout) — its result still
  appeared first in the JSON `results` array despite finishing after the
  second, faster target, confirming index-addressed slot assignment
  rather than completion-order appending.
- **Peer-IP handling**: live-verified `peer_ip` is populated from the real
  connection's `getpeername()` on both a successful HTTP check and a TCP
  check, and correctly `null` on a timeout/DNS-failure attempt where no
  connection was ever established.
- **Network boundary isolation and no forbidden primitives**: confirmed
  by direct grep and by re-running `test_no_network_health_boundary.py`/
  `test_health_no_forbidden_tokens.py` that `socket`/`ssl` are imported
  only by `core/health_http.py`/`core/health_tcp.py`,
  `concurrent.futures` only by `core/health_runner.py`, and that no
  `subprocess`, `urllib.request`, `requests`, `httpx`, or `aiohttp`
  reference exists anywhere in the `health` command tree.
- **Full regression suite**: 998 tests pass, 99.05% coverage, mypy
  `--strict` clean across all 30 source files, no Day 1–4 regression.
