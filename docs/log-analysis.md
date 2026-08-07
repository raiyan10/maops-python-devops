# Log Analysis

`maops-py logs analyze` streams a JSONL/syslog log file (the same
accepted formats, timestamp handling, and severity normalization as
`maops-py logs parse` — see [docs/log-parsing.md](log-parsing.md)) into
deterministic operational aggregates: severity and source counts,
normalized message signatures, a peak fixed-duration time bucket, and
threshold-based advisory findings. For redaction specifics, see
[docs/log-redaction.md](log-redaction.md).

This command performs deterministic aggregation and threshold
comparisons only. It makes **no machine learning, artificial
intelligence, behavioral-detection, or general anomaly-detection
claim** — every number in its output is a plain count, ratio, or
fixed-window bucket, and every finding is a fixed `count >= threshold`
comparison stated in its own `detail` text.

```bash
maops-py logs analyze PATH
maops-py logs analyze PATH --input-format auto|jsonl|syslog
maops-py logs analyze PATH --format text|json
maops-py logs analyze PATH --max-lines INTEGER
maops-py logs analyze PATH --max-bytes INTEGER
maops-py logs analyze PATH --max-line-bytes INTEGER
maops-py logs analyze PATH --top INTEGER
maops-py logs analyze PATH --bucket-seconds INTEGER
maops-py logs analyze PATH --repeat-threshold INTEGER
maops-py logs analyze PATH --error-threshold INTEGER
maops-py logs analyze PATH --no-redact
python -m maops_pydevops logs analyze PATH --format json
```

`--max-events` does not exist on this command — analysis never retains
individual events for output, so there is nothing for it to bound (see
"Deterministic aggregation" below).

## Deterministic aggregation (streaming, bounded memory)

`core/log_analysis.py`'s `LogAnalysisState` folds one event at a time
into a small set of running aggregates and then discards the event — no
`list` of parsed events is ever held in memory for analysis, regardless
of how many lines the file contains. This does **not** mean the
severity/source/signature counters are capped early: computing an exact
top-K by count requires an exact count for every distinct value before
sorting, so the signature and source dictionaries grow with the number
of **distinct** values seen, not the number of events. In realistic log
data (a small number of repeated message templates), this is a tiny
fraction of a per-event list's memory; in the pathological worst case
(every line's normalized signature is unique), it is bounded above by
`--max-lines`, which is itself capped at 1,000,000. This is stated here
explicitly so it is never mistaken for an oversight.

## Severity counts

All ten canonical severities are always present in the output, each
with an explicit integer count (`0` when none occurred) — never
omitted. Ordering is **fixed** (`trace, debug, info, notice, warning,
error, critical, alert, emergency, unknown`), matching the enum's own
declaration order. Severity counts are never sorted by count: a small,
closed set reads more predictably in a stable canonical order than one
that could reorder itself between two very similar runs.

## Source counts

One entry per distinct `source` value seen, ordered **count descending,
then source name ascending for ties**. An absent or empty `source`
displays as the literal string `<unknown>`.

## Message signatures

Redacted messages (see [docs/log-redaction.md](log-redaction.md) — a
signature is only ever derived from an already-redacted message, never
an unredacted one) are normalized into a signature via a fixed,
ordered sequence of transformations:

1. Replace UUID values with `<uuid>`.
2. Replace IPv4 addresses with `<ip>`.
3. Replace long (8+ character) hexadecimal identifiers with `<hex>`
   (this step runs after UUID replacement specifically because a UUID's
   dash-broken hex runs would otherwise partially match this rule on
   their own).
4. Replace decimal integer tokens with `<num>`.
5. Collapse repeated whitespace to a single space, and trim.
6. Apply Unicode-preserving case folding (`str.casefold()`, not
   `str.lower()` — this correctly maps e.g. German `"ß"` to `"ss"` as
   part of full Unicode case folding, not a lossy transliteration).
7. Truncate to 256 characters.

`--top` (default `10`, range `0`–`100`) bounds only the **displayed**
`top_signatures` list — it never limits which signatures are scanned
for the repeated-signature finding below, so a small `--top` cannot
hide a real repeat. The displayed list is ordered **count descending,
then signature ascending for ties**; each entry reports `signature`,
`count`, `first_line`, `last_line` (input-order line numbers), and a
`severity_counts` object listing only the severities that actually
occurred for that signature.

## Time buckets

Computed only from events with a normalized (UTC, timezone-aware)
`timestamp` — naive-timestamp and BSD-syslog events (which are always
`timestamp: null`, per [docs/log-parsing.md](log-parsing.md)) are
excluded from bucket math entirely; no year or timezone is ever
invented for them.

Bucket boundaries use **Unix-epoch integer arithmetic** exclusively:
`bucket_start = (epoch_seconds // bucket_seconds) * bucket_seconds`,
where `bucket_seconds` is `--bucket-seconds` (default `300`, range `1`–
`86400`). This has no local-time dependence and no daylight-saving
dependence — buckets are computed purely from UTC epoch seconds. The
peak bucket is selected by walking buckets in ascending epoch order
with a strict "greater than" comparison, so the **earliest** bucket
wins any count tie. When no event has a normalized timestamp,
`peak_bucket_start` is `null` and `peak_bucket_count` is `0`.

`out_of_order_events` counts how many events, in input-stream order,
had an epoch earlier than the running maximum seen so far —
`first_timestamp`/`last_timestamp` are the first-seen/last-seen
timestamps in input order, not the minimum/maximum by value, precisely
because a separate out-of-order count already exists to describe
ordering anomalies.

## Findings

All findings are advisory (`status: "warn"`) and are emitted in a
**fixed order** so the `findings` array is byte-stable across repeated
runs on the same input: truncated input, malformed lines, overlong
lines, error volume, unknown severity, out-of-order timestamps, then one
entry per qualifying repeated signature (in the same count-descending,
signature-ascending order as the signature list).

| Finding | Fires when |
|---|---|
| `truncated_input` | Any hard limit was hit, or any line was skipped as overlong |
| `malformed_lines` | At least one line produced no event |
| `overlong_lines` | At least one line exceeded `--max-line-bytes` |
| `error_volume` | The combined count of `error`/`critical`/`alert`/`emergency` events is at or above `--error-threshold` |
| `unknown_severity` | At least one event had an unrecognized severity |
| `out_of_order_timestamps` | At least one event's timestamp was out of order |
| `repeated_signature` | A message signature's count is at or above `--repeat-threshold` (one finding per qualifying signature) |

## Threshold behavior

| Flag | Default | Minimum | Maximum |
|---|---|---|---|
| `--top` | 10 | 0 | 100 |
| `--bucket-seconds` | 300 | 1 | 86400 |
| `--repeat-threshold` | 5 | 2 | 1000000 |
| `--error-threshold` | 1 | 1 | 1000000 |

## Warning-versus-exit semantics

A report with findings is still a **meaningful** report: `overall:
"warn"` and every finding present still exits `0`. Only two conditions
exit `1`: the input file itself could not be opened at all, or the file
is non-empty but yielded zero parseable events — identical to `logs
parse`'s exit semantics (see
[docs/log-parsing.md](log-parsing.md#exit-codes)).

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
    "top": 10,
    "bucket_seconds": 300,
    "repeat_threshold": 5,
    "error_threshold": 1,
    "redact": true
  },
  "summary": {
    "bytes_read": 686,
    "lines_read": 5,
    "events_parsed": 4,
    "malformed_lines": 1,
    "overlong_lines": 0
  },
  "severity_counts": {
    "trace": 0, "debug": 0, "info": 0, "notice": 0, "warning": 1,
    "error": 3, "critical": 0, "alert": 0, "emergency": 0, "unknown": 0
  },
  "source_counts": [
    {"source": "smoke-api", "count": 3},
    {"source": "smoke-svc", "count": 1}
  ],
  "top_signatures": [
    {
      "signature": "database connection failed to <ip>",
      "count": 3,
      "first_line": 1,
      "last_line": 4,
      "severity_counts": {"error": 3}
    }
  ],
  "time": {
    "timestamped_events": 4,
    "first_timestamp": "2026-08-06T04:00:00+00:00",
    "last_timestamp": "2026-08-06T04:00:15+00:00",
    "out_of_order_events": 0,
    "bucket_seconds": 300,
    "peak_bucket_start": "2026-08-06T04:00:00+00:00",
    "peak_bucket_count": 4
  },
  "findings": [
    {"code": "malformed_lines", "status": "warn", "detail": "1 line(s) could not be parsed"},
    {"code": "error_volume", "status": "warn", "detail": "3 error-level event(s) at or above threshold 1"}
  ],
  "issues": [
    {"line_number": 5, "code": "malformed_line", "status": "warn", "detail": "no recognizable timestamp"}
  ],
  "line_limit_reached": false,
  "byte_limit_reached": false,
  "truncated": false,
  "overall": "warn"
}
```

## Limitations

- **Not anomaly detection.** Findings are fixed threshold comparisons
  the operator configures (`--repeat-threshold`, `--error-threshold`),
  not a learned or statistical baseline. Nothing here models "normal"
  behavior or flags deviation from it.
- **Signature/source memory scales with distinct values, not events**,
  as described above — an intentional consequence of exact top-K
  counting, not a bug.
- **No multiline/stack-trace correlation** — each physical line is
  analyzed independently, matching `logs parse`'s grammar limitation.
- **BSD-syslog-only input has no time-bucket signal**: without a year
  in the source timestamp, every event's `timestamp` is `null`, so
  `time.timestamped_events` is `0` and the peak bucket is always empty
  — this is correct behavior given the input, not a defect.
