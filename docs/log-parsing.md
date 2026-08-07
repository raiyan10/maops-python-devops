# Log Parsing

`maops-py logs parse` turns a single JSONL or syslog log file into a
structured report of typed events and per-line parse issues. This
document describes accepted formats, JSONL field aliases, the syslog
grammar and its limitations, timestamp handling, severity normalization,
file limits, empty/malformed-file behavior, the output schema, and exit
codes. For the streaming aggregation performed by `maops-py logs
analyze`, see [docs/log-analysis.md](log-analysis.md). For redaction
specifics, see [docs/log-redaction.md](log-redaction.md).

This command performs deterministic parsing only — it makes no machine
learning, artificial intelligence, behavioral detection, or general
anomaly-detection claim.

```bash
maops-py logs parse PATH
maops-py logs parse PATH --input-format auto|jsonl|syslog
maops-py logs parse PATH --format text|json
maops-py logs parse PATH --max-lines INTEGER
maops-py logs parse PATH --max-bytes INTEGER
maops-py logs parse PATH --max-line-bytes INTEGER
maops-py logs parse PATH --max-events INTEGER
maops-py logs parse PATH --no-redact
python -m maops_pydevops logs parse PATH --format json
```

`PATH` is a required positional and is always treated as a literal
filesystem path — shell metacharacters, quotes, spaces, Unicode, dollar
signs, brackets, semicolons, and backticks in it remain inert text; they
are never interpreted, expanded, or executed. Exactly one path may be
given.

## Accepted formats

Exactly three `--input-format` values are supported: `auto` (default),
`jsonl`, and `syslog`. `auto` inspects each nonblank line independently
— if the first non-whitespace byte is `{`, JSONL parsing is attempted;
otherwise syslog parsing is attempted. Detection is per-line, not sticky
across the file, so a file mixing JSONL and syslog lines is parsed
correctly line by line, and a malformed `{`-prefixed line stays a JSON
parse issue rather than silently falling back to syslog parsing. Each
parsed event records which of `jsonl`/`syslog` it was actually parsed
as, even under `auto`.

## JSONL

Every nonblank line must contain exactly one JSON object. Arrays,
strings, numbers, booleans, and `null` are rejected as top-level log
events (`malformed_json` issue, no event). Only the documented
allowlisted fields below are ever read; no other JSON key is copied into
output, however large or numerous the object.

Alias resolution picks the first key present, by name, in this fixed
precedence order — a key with a `null` value still wins over a lower-
precedence key that happens to be populated:

| Canonical field | Alias precedence |
|---|---|
| `timestamp` | `timestamp` → `time` → `ts` |
| `severity` | `severity` → `level` → `log_level` |
| `hostname` | `hostname` → `host` |
| `source` | `source` → `service` → `app` → `logger` |
| `message` | `message` → `msg` → `event` |
| `pid` | `pid` → `process_id` |

- `message` must resolve to a string. If it is missing or not a string,
  the line produces no event, only an `invalid_field_type` issue.
- `hostname`/`source` must be strings when present; a non-string value
  becomes `null` in the event plus an `invalid_field_type` issue — the
  event is still emitted.
- `pid` must be a non-negative integer or absent/`null`. A boolean is
  explicitly rejected even though Python's `bool` is technically an
  `int` subtype; a string, float, or negative integer is also rejected.
  An invalid `pid` becomes `null` plus an `invalid_field_type` issue,
  the event is still emitted.
- `severity` follows the same normalization as syslog — see "Severity
  normalization" below.
- Extra keys are read only through the alias lookups above; nothing
  else in the parsed object is ever touched or serialized.

## Syslog

A staged, deterministic grammar (not one large regular expression),
supporting:

- An optional `<PRI>` prefix, `<0>` through `<191>`.
- An RFC3339/ISO-8601 timestamp, or a BSD-style `MMM DD HH:MM:SS`
  timestamp.
- A hostname (the next whitespace-delimited token).
- A `source[pid]: message` tail — `source` is read up to an optional
  `[pid]` (numeric only) and the first colon; everything after that
  colon, including further colons, is the message verbatim.

PRI severity mapping (`severity = PRI % 8`, facility bits are ignored —
this release does not model syslog facilities):

| PRI % 8 | Severity |
|---|---|
| 0 | `emergency` |
| 1 | `alert` |
| 2 | `critical` |
| 3 | `error` |
| 4 | `warning` |
| 5 | `notice` |
| 6 | `info` |
| 7 | `debug` |

When no `<PRI>` prefix is present, severity is `unknown`. Any structural
grammar violation (no recognizable timestamp, no hostname, no
`source[pid]: message` separator, a non-numeric `[pid]`, or a PRI value
above 191) produces a `malformed_line` issue and no event.

**No multiline or stack-trace continuation support.** Each physical line
is parsed independently; a stack trace or multi-line message spanning
several lines is parsed as several separate (and likely malformed)
lines, not reassembled into one event.

## Timestamp handling

Uses only standard-library `datetime` functionality (`fromisoformat`,
`astimezone`) — no third-party date-parsing library.

- Timezone-aware ISO-8601/RFC3339 strings are accepted, including a
  trailing `Z`, and normalized to UTC (`timestamp`). The original string
  is always preserved verbatim in `timestamp_raw`.
- A **naive** ISO timestamp (no offset, no `Z`) parses successfully as a
  string but produces `timestamp: null` — never an issue, since this is
  documented, expected behavior, not degraded data.
- A **BSD-style** timestamp (`Aug  6 10:30:00`) has no year and no
  timezone in its own text, so it is *never* normalized: `timestamp` is
  always `null` for these lines, with the original text preserved in
  `timestamp_raw`, and no issue is raised — this is correct, expected
  behavior, not a sign the tool is broken. No year, date, or timezone is
  ever inferred, and the current clock is never used to "repair" a
  timestamp.
- A syntactically invalid timestamp string (one that matches neither
  branch, or fails to parse as an actual calendar date/time) produces an
  `invalid_timestamp` issue; the event is still emitted with
  `timestamp: null`.

## Severity normalization

Ten canonical values: `trace`, `debug`, `info`, `notice`, `warning`,
`error`, `critical`, `alert`, `emergency`, `unknown`. A fixed alias table
is checked (case-folded) before falling back to the canonical set:
`warn → warning`, `err → error`, `crit → critical`, `fatal → critical`,
`emerg → emergency`, `information → info`. Any string not recognized as
canonical or aliased becomes `unknown` — this is never treated as a
parse failure.

## File limits

A dedicated, bounded, fd-safe reader enforces every limit below —
see [docs/subprocess-safety.md](subprocess-safety.md)'s exit-code table
for how a truncated report still maps to a successful exit.

| Flag | Default | Minimum | Maximum |
|---|---|---|---|
| `--max-lines` | 10000 | 1 | 1000000 |
| `--max-bytes` | 10485760 | 1024 | 104857600 |
| `--max-line-bytes` | 65536 | 256 | 1048576 |
| `--max-events` | 1000 | 0 | 10000 |

`--max-events` bounds how many parsed events are **retained in the
report**, not how many lines are parsed — `summary.events_parsed` can
exceed `summary.events_emitted`. `--max-events 0` produces a
summary-only report (no `events` at all, still counting
`events_parsed`). Lines longer than `--max-line-bytes` are skipped
without ever buffering or serializing their content; they are counted
in `summary.overlong_lines` and reported as one `overlong_line` issue
per occurrence. `line_limit_reached`/`byte_limit_reached` are `true`
only when more data genuinely existed beyond the configured cap — never
merely because a file happened to end exactly at the limit.

## Empty and malformed files

- A genuinely empty regular file (0 bytes) produces an empty report
  (`events: []`, `issues: []`) with `overall: "pass"` and exit `0`.
- A file containing only blank/whitespace lines behaves the same way.
- A **non-empty** file (at least one non-blank line) that yields **zero
  parseable events** is `overall: "fail"` and exits `1` — this is the
  only failure mode besides the file itself being unreadable.
- Any other combination of successfully-parsed events plus issues
  and/or truncation is `overall: "warn"`, exit `0`.

## Output schema

```json
{
  "version": "0.4.0",
  "path": "/tmp/demo.log",
  "options": {
    "input_format": "auto",
    "max_lines": 10000,
    "max_bytes": 10485760,
    "max_line_bytes": 65536,
    "max_events": 1000,
    "redact": true
  },
  "summary": {
    "bytes_read": 686,
    "lines_read": 5,
    "blank_lines": 0,
    "events_parsed": 4,
    "events_emitted": 4,
    "malformed_lines": 1,
    "overlong_lines": 0
  },
  "events": [
    {
      "line_number": 1,
      "input_format": "jsonl",
      "timestamp": "2026-08-06T04:00:00+00:00",
      "timestamp_raw": "2026-08-06T04:00:00Z",
      "hostname": "smoke-host",
      "source": "smoke-api",
      "pid": 1001,
      "severity": "error",
      "message": "database connection failed to 10.0.0.5",
      "redacted": false
    }
  ],
  "issues": [
    {
      "line_number": 5,
      "code": "malformed_line",
      "status": "warn",
      "detail": "no recognizable timestamp"
    }
  ],
  "line_limit_reached": false,
  "byte_limit_reached": false,
  "truncated": false,
  "overall": "warn"
}
```

Events are emitted in input order; issues are emitted in deterministic
input order. An issue's `detail` never echoes a complete raw line —
malformed content is described, not reproduced. Every field is
explicit: unavailable values are JSON `null`, never omitted.

## Exit codes

- `0` — a meaningful report was produced, `overall` is `"pass"` or
  `"warn"` (including a truncated or partially-malformed input).
- `1` — the file itself could not be opened at all (missing, a
  directory, a symlink, a special file, a permission error, or a race
  detected between the safety check and the open), or the file is
  non-empty but yielded zero parseable events.
- `2` — a CLI usage error (an invalid `--input-format`/`--format`, an
  out-of-range or unparseable bounded flag, a missing or extra `PATH`).

## No stdin, no compressed-log support

`logs parse` only ever opens the one literal `PATH` argument as a
regular file. There is no stdin mode in this release, no automatic
decompression of `.gz`/`.zip`/other compressed logs, and no archive
extraction — a compressed file is read as opaque binary content and
will not parse as JSONL or syslog.
