# Health Checks

`maops-py health http` and `maops-py health tcp` run bounded HTTP and TCP
availability checks against explicitly supplied endpoints. This is the
first feature in this package permitted to make network connections — see
[docs/http-health-safety.md](http-health-safety.md) for the complete
safety model (TLS, redirects, request scope, response handling) and the
network-boundary contract with every other command.

This is an **availability checker, not a vulnerability scanner or a
network discovery tool**. It checks only the targets you name, exactly
once per attempt, with no follow-up requests of any kind.

```bash
maops-py health http URL [URL ...]
maops-py health http URL --method GET|HEAD
maops-py health http URL --expect-status 200 | --expect-status 200-299
maops-py health http URL --timeout SECONDS
maops-py health http URL --retries INTEGER
maops-py health http URL --retry-delay SECONDS
maops-py health http URL --workers INTEGER
maops-py health http URL --format text|json

maops-py health tcp TARGET [TARGET ...]
maops-py health tcp TARGET --timeout SECONDS
maops-py health tcp TARGET --retries INTEGER
maops-py health tcp TARGET --retry-delay SECONDS
maops-py health tcp TARGET --workers INTEGER
maops-py health tcp TARGET --format text|json

python -m maops_pydevops health http URL --format json
python -m maops_pydevops health tcp TARGET --format json
```

## HTTP target syntax

A URL with scheme `http` or `https`, a non-empty host, and an optional
explicit port. Query parameters are allowed and are actually sent on the
wire — see [docs/http-health-safety.md](http-health-safety.md#url-privacy)
for how they're redacted in *reports*. Userinfo (`user:pass@host`) is
rejected as a usage error (exit `2`); fragments are accepted but silently
dropped (never sent, never appear in output). Raw C0 control characters
and raw whitespace anywhere in the URL are rejected; percent-encoded
sequences are unaffected.

## TCP target syntax

```
hostname:port
IPv4:port
[IPv6]:port
```

Port must be `1`-`65535`. Unbracketed IPv6 (`::1:8080`, ambiguous which
colon is the port separator), CIDR notation, port ranges (`80-90`), and
comma-separated ports (`80,443`) are all rejected as invalid target syntax
— none of these are scanning/discovery affordances.

## PASS / WARN / FAIL and retries

`attempts = --retries + 1` (default `--retries` is `1`, so 2 attempts by
default). A fixed (non-jittered) `--retry-delay` (default `0.25` seconds)
separates attempts; there is never a sleep after the final attempt.

| Status | Meaning |
|---|---|
| `pass` | The target succeeded on its first attempt. |
| `warn` | The target initially failed but succeeded on a later attempt — degraded, but available. |
| `fail` | The target never reached a healthy state across all attempts. |

Report `overall`: `pass` if every target is `pass`; `warn` if at least one
target is `warn` and none is `fail`; `fail` if at least one target is
`fail`.

### Retryable conditions

**HTTP** retries on: DNS/connection failures, socket timeout, TLS
transport failure, HTTP protocol failure, and HTTP status `408`, `429`, or
`500`-`599`. A response already inside `--expect-status` never reaches
the retry decision. Any other status outside `--expect-status` (e.g.
`400`, `401`, `403`, `404`, or a `3xx` outside a custom range) is **not**
retried — it fails immediately on the first attempt.

**TCP** retries on any failed connect attempt (DNS failure, connection
refused, timeout, or other connection error).

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | Report `overall` is `pass` or `warn`. |
| `1` | Report `overall` is `fail`, or an operational network failure is represented in an otherwise valid report. |
| `2` | CLI usage error: invalid flag value, invalid target syntax, userinfo present, unsupported scheme, or more than 100 (or fewer than 1) targets. |

A target-validation failure (exit `2`) is checked for **every** target,
and the target-count bound is checked first — an invalid invocation never
opens a single socket.

## Timeout semantics

`--timeout` (default `3.0`, range `>0`-`60.0` seconds) bounds each
*attempt*, applied to the underlying socket. It is not a hard wall-clock
bound on DNS resolution specifically — platform resolver behavior can, in
rare cases, exceed the configured socket timeout before the OS itself
gives up. This is a standard-library/OS-level limitation, not specific to
this implementation.

## Concurrency and deterministic ordering

`--workers` (default `4`, range `1`-`32`) bounds a
`concurrent.futures.ThreadPoolExecutor` — never more than `min(--workers,
target count)` checks run concurrently, and never more than 100 targets
per invocation. One worker handles one target end-to-end, including all
of that target's retries (retries are always sequential within a target,
never parallelized). **Report ordering always matches the order targets
were given on the command line**, regardless of which target's checks
complete first — this is a structural property of the result-assembly
mechanism (each result is written into a pre-sized, index-addressed slot,
never appended in completion order), not a sort applied afterward. Target
`index` fields in the report start at `1`.

## Peer IP

A successful (or protocol-level, i.e. HTTP-status-classified) attempt
reports the actual peer IP address the connection was made to, via
`getpeername()`. This is the resolved address actually connected to, not
the full DNS resolver result set. `peer_ip` is `null` when no connection
was ever established (DNS failure, connection refused, timeout).

## Loopback and private endpoints

Loopback (`127.0.0.1`, `::1`) and private/internal addresses are
intentionally, fully supported — internal DevOps health checking against
services on a private network or localhost is a core use case, not an
edge case to work around.

## No scanning or discovery support

This command checks only the endpoints you explicitly name. It does not
and will not support: CIDR expansion, subnet or host discovery, port
ranges, URL globbing, arbitrary port lists, raw packets, ICMP, SYN
scanning, or banner grabbing. See
[docs/http-health-safety.md](http-health-safety.md) for the complete list
of excluded capabilities and why.

## HTTP report schema

```json
{
  "version": "0.7.0",
  "protocol": "http",
  "options": {
    "method": "GET",
    "expected_status_min": 200,
    "expected_status_max": 399,
    "timeout_seconds": 3.0,
    "retries": 1,
    "retry_delay_seconds": 0.25,
    "workers": 4,
    "follow_redirects": false,
    "tls_verify": true
  },
  "summary": {
    "targets": 2,
    "passed": 1,
    "warned": 1,
    "failed": 0,
    "attempts": 3
  },
  "results": [
    {
      "index": 1,
      "target": "http://127.0.0.1:8000/health",
      "status": "pass",
      "attempts_used": 1,
      "total_duration_ms": 5,
      "final_http_status": 200,
      "peer_ip": "127.0.0.1",
      "attempts": [
        {
          "attempt": 1,
          "duration_ms": 5,
          "http_status": 200,
          "peer_ip": "127.0.0.1",
          "failure_reason": null,
          "detail": null
        }
      ]
    }
  ],
  "overall": "warn"
}
```

`target` is the redacted, sanitized display form of the URL — see
[docs/http-health-safety.md](http-health-safety.md#url-privacy). `attempts`
lists every attempt actually made, in order (not just the final one), so
retry/failure diagnosis never requires re-running the check.

### HTTP failure reasons

`dns_error`, `timeout`, `connection_refused`, `connection_error`,
`tls_error`, `http_protocol_error`, `unexpected_status`,
`invalid_target_encoding`. Every reason is one of this fixed, closed set
— never arbitrary exception text. See
[docs/http-health-safety.md](http-health-safety.md#failure-classification)
for the exact condition each one represents.

## TCP report schema

```json
{
  "version": "0.7.0",
  "protocol": "tcp",
  "options": {
    "timeout_seconds": 3.0,
    "retries": 1,
    "retry_delay_seconds": 0.25,
    "workers": 4
  },
  "summary": {
    "targets": 2,
    "passed": 2,
    "warned": 0,
    "failed": 0,
    "attempts": 2
  },
  "results": [
    {
      "index": 1,
      "target": "127.0.0.1:3306",
      "host": "127.0.0.1",
      "port": 3306,
      "status": "pass",
      "attempts_used": 1,
      "total_duration_ms": 2,
      "peer_ip": "127.0.0.1",
      "attempts": [
        {
          "attempt": 1,
          "duration_ms": 2,
          "peer_ip": "127.0.0.1",
          "failure_reason": null,
          "detail": null
        }
      ]
    }
  ],
  "overall": "pass"
}
```

### TCP failure reasons

`dns_error`, `timeout`, `connection_refused`, `connection_error`,
`invalid_target_encoding` — the same fixed set as HTTP, minus the three
HTTP-protocol-specific reasons (`tls_error`, `http_protocol_error`,
`unexpected_status`) that don't apply to a connect-only check.

## Text output

Both commands render: toolkit version, protocol, effective options
(method/expected-status for HTTP; timeout/retries/workers for both), one
row per target (redacted target, PASS/WARN/FAIL, attempts used, final
status, peer IP, duration, final detail), a summary line, and the overall
status. Every target/detail string is passed through the project's text
sanitization boundary before being interpolated into a report line — see
`core/output.py`'s `_sanitize_for_text`. No ANSI escape codes are ever
emitted.

## Limitations

- **HTTPS is not exercised in the loopback integration test suite.**
  TLS-path behavior (certificate validation, hostname verification,
  `tls_error` classification) is covered deterministically at the unit
  level via injected fakes and a source-scan proving TLS verification
  defaults are never relaxed; a real self-signed-certificate loopback
  HTTPS integration test was judged not worth the added complexity for
  this release.
- **DNS timeout is not a hard wall-clock guarantee** — see "Timeout
  semantics" above.
- **`--expect-status` supports exactly one value or one range** — no
  comma-separated lists in this release.
