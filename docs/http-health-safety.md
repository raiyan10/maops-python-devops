# HTTP Health-Check Safety

`src/maops_pydevops/core/health_http.py` and
`src/maops_pydevops/core/health_tcp.py` are the only two modules in this
package permitted to import `socket`, `ssl`, or `http.client`. This
document describes their full safety contract. `maops-py health http`/
`health tcp` are **availability checkers, not vulnerability scanners**:
they report whether an explicitly named endpoint is reachable and, for
HTTP, whether it returns an expected status — nothing about the target's
software, configuration, or security posture is inspected or inferred.

## `http.client`, never `urllib.request`

HTTP requests are made with `http.client.HTTPConnection`/`HTTPSConnection`
directly. `urllib.request` is deliberately never used: it consults
`HTTP_PROXY`/`HTTPS_PROXY` environment variables and can be configured to
follow redirects, neither of which this feature wants. There is exactly
one HTTP call site in the whole package.

## `http`/`https` only

Any other URL scheme (`ftp`, `ws`, `file`, `gopher`, ...) is rejected at
validation time as a usage error (exit `2`), before any connection is
attempted.

## GET/HEAD only, no request bodies

`--method` accepts exactly `GET` or `HEAD` — argparse `choices=` rejects
anything else before any network code runs. `conn.request(...)` is never
called with a `body=` argument anywhere in this package; there is no CLI
flag or code path that could supply one. No POST, PUT, PATCH, or DELETE
support exists.

## No custom headers, no credentials

The only header this package ever sends is a fixed, stable
`User-Agent: maops-py/<version>` string. There is no CLI flag, environment
variable, or configuration key that lets a caller inject an arbitrary
header — in particular, no `Authorization` header can ever be set. URL
userinfo (`http://user:password@host/`) is rejected outright as a usage
error at validation time, before any connection is attempted — the
package never sends HTTP Basic credentials derived from a URL.

## Redirects are never followed

A `3xx` response is reported exactly as received (its status code, and
whether that code falls inside `--expect-status`) — the retry loop only
ever retries the **same** target again; there is no code path that reads
a `Location` header or issues a request to a different URL. A redirect
loop, an open-redirect target, or a redirect to an internal-only address
can never cause this tool to make an unexpected second request.

## TLS verification is always enabled

`ssl.create_default_context()` is called with **zero attribute
mutation** anywhere in `core/health_http.py` — no `check_hostname =
False`, no `verify_mode = ssl.CERT_NONE`, no
`ssl._create_unverified_context()`. Certificate-chain validation and
hostname verification are both on by default and are never relaxed.
**There is no `--insecure` flag and no other way to bypass certificate
verification in this release.** A source-scan unit test
(`tests/unit/test_health_http_attempt.py`) guards against this invariant
ever regressing.

## No response-body retention

`response.read()`, `.readinto()`, and iteration over an `HTTPResponse` are
never called anywhere in this package. Only the status line and the
connection's peer address are ever extracted. This is a structural
guarantee, not a policy: there is no field on any attempt/result model
capable of holding response-body content, so there is no code path that
could accidentally leak one into a report.

## No response-header collection

`response.getheaders()`, `.headers`, and `.getheader(...)` are likewise
never called. No header value — including `Server`, `Set-Cookie`, or any
custom header a target returns — is ever read, stored, or serialized.

## No server-controlled reason-phrase serialization

`response.reason` (the human-readable text after the HTTP status code,
fully controlled by the remote server) is never read. Every `detail`
string in a report is a fixed, package-generated string from a closed
set — never text sourced from the server's response.

## No proxy-environment use

Because HTTP requests go through `http.client` directly (never
`urllib.request`), `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` and friends are
never consulted. A connection always goes directly to the resolved
address of the target host.

## URL privacy

Every report field derived from a URL is built once, at validation time,
from the *validated* target — the original raw command-line string is
never retained on any internal object at all.

- **Userinfo** is rejected outright (see above) — there is no stripping
  logic needed in the display builder, since a target containing userinfo
  never reaches it.
- **Fragment** is parsed and then discarded — it is never included in the
  actual HTTP request and never appears in any report field.
- **Query values are redacted, query key text and order are preserved.**
  `https://example.com/health?token=abc&region=ap` is reported as
  `https://example.com/health?token=[REDACTED]&region=[REDACTED]`. The
  *actual* outbound request still uses the real, unredacted query string
  (redaction is a report-serialization concern only) — an availability
  check against a token-authenticated endpoint still works correctly;
  only what appears in the JSON/text output is redacted.
- **No explicit port is ever synthesized.** If a target didn't specify a
  port, none appears in the reported URL either — the report never
  invents information the caller didn't provide.

## Failure classification

Only known, expected transport exceptions are converted into a structured
`failure_reason`. Every other exception (a genuine programming error)
propagates uncaught rather than being silently folded into a
network-failure result — this is verified by a dedicated unit test
asserting neither `core/health_http.py` nor `core/health_tcp.py` contains
a bare `except Exception`/`except BaseException` clause.

| Exception | HTTP `failure_reason` | TCP `failure_reason` |
|---|---|---|
| `socket.gaierror` | `dns_error` | `dns_error` |
| `UnicodeError` (incl. `UnicodeEncodeError`) | `invalid_target_encoding` | `invalid_target_encoding` |
| `TimeoutError` | `timeout` | `timeout` |
| `ConnectionRefusedError` | `connection_refused` | `connection_refused` |
| `ssl.SSLError` (incl. `SSLCertVerificationError`) | `tls_error` | *(n/a — TCP never negotiates TLS)* |
| `http.client.HTTPException` (incl. `BadStatusLine`, `RemoteDisconnected`) | `http_protocol_error` | *(n/a)* |
| `OSError` (catch-all) | `connection_error` | `connection_error` |
| *(status received but outside `--expect-status`)* | `unexpected_status` | *(n/a — TCP is connect-only)* |

`UnicodeError` is deliberately not treated as "a programming error" the
way an arbitrary unlisted exception is: `socket.getaddrinfo()` always
runs a `str` hostname through the `idna` codec, even for purely-ASCII
input, so a malformed DNS label (an empty segment from a stray double
dot, an over-length label) raises `UnicodeError` for ordinary operator
input — not just deliberately crafted or non-ASCII hostnames. On the HTTP
path, a literal non-ASCII character anywhere in the URL path or query
(not just the hostname) separately raises `UnicodeEncodeError` from
`http.client`'s ASCII-only request-line encoding. Both are caught
explicitly and mapped to `invalid_target_encoding`, the same as any other
transport-layer failure — see
`docs/engineering-reviews/day-05-network-review.md` (Critical C1) for the
adversarial history behind this entry.

No arbitrary exception `repr()`/`str()` value is ever copied into a
report — every `detail` string is one of a fixed, deterministic,
package-generated set.

## No banner grabbing, no application data (TCP)

`maops-py health tcp` performs `socket.create_connection(...)` followed
immediately by `getpeername()` and `close()` — no `send`/`sendall`/`recv`
call exists anywhere in the TCP attempt path. No generic TCP target ever
has a TLS handshake performed against it; TLS is exclusively an HTTP-path
concept, gated by the `https` scheme.

## No scanning or discovery affordances

The target grammar for both protocols accepts exactly one explicit
host+port (or URL) per target string. There is no CIDR-notation parsing,
no port-range syntax, no comma-separated port list, and no code path that
iterates a subnet or a port range — `ipaddress.ip_network()` is never
used to expand anything. Every check this tool performs is exactly one
connection attempt (or `retries + 1` sequential attempts to the *same*
explicitly named endpoint), never more.

## DNS resolution timeout limitation

`--timeout` is applied as the socket-level connect/read timeout. Platform
DNS resolvers do not always honor that exact bound — a resolver-level
hang can, in rare cases on some platforms, take longer than the
configured `--timeout` before the OS itself gives up. This is a
standard-library/OS limitation shared by any Python networking code, not
specific to this implementation.

## Limitations

- **This is an availability checker, not a vulnerability scanner.** It
  makes no claim about a target's security posture, software version, or
  configuration correctness — only whether it is reachable and (for HTTP)
  returns an expected status.
- **A future feature accepting user-supplied headers, request bodies, or
  redirect-following would need its own design and review** — this
  module's guarantees describe what `health http`/`health tcp` do today,
  not a general-purpose HTTP client.
- See [docs/health-checks.md](health-checks.md) for the full CLI/report
  contract this safety model supports.
