# Log Redaction

`core/log_redaction.py` is the sole module in this package responsible
for removing secret-shaped values from log event messages before they
reach a `logs parse`/`logs analyze` report. This document describes the
default behavior, every supported pattern, the risk of `--no-redact`,
this feature's honest limitations, and why no report field can ever
contain a complete, unredacted raw line.

## Default redaction

Redaction is **enabled by default** for both `maops-py logs parse` and
`maops-py logs analyze`. It runs once, on the `message` field only,
after that field has already been extracted from the parsed JSONL
object or syslog tail — `hostname`, `source`, and `pid` are structured
fields, out of scope for this pass, since every documented pattern below
is message-shaped free text (`key=value`, `key: value`, or a URI). Every
event carries an explicit `redacted: boolean` field recording whether
redaction actually changed that specific message.

```bash
maops-py logs parse PATH                 # redaction on (default)
maops-py logs parse PATH --no-redact     # redaction off
maops-py logs analyze PATH               # redaction on (default)
maops-py logs analyze PATH --no-redact   # redaction off
```

## Supported patterns

A fixed, ordered tuple of bounded regular expressions, applied in this
order (narrow/specific patterns first, so the broad generic pattern
last only has to catch what they didn't):

1. **Bearer tokens** — `Bearer <token>` (this also covers `Authorization:
   Bearer <token>`, since the pattern matches the word `Bearer`
   regardless of what precedes it). The word `Bearer` is preserved; the
   token is replaced.
2. **URI userinfo passwords** — `scheme://user:PASSWORD@host` style
   values. `user:` and `@` are preserved; only the password segment
   between them is replaced.
3. **Key/value secrets**, case-insensitive, covering: `password`,
   `passwd`, `pwd`, `token`, `api_key`/`api-key`/`apikey`,
   `secret`, `access_key`/`access-key`. The key name and its delimiter
   (`=` or `:`, with surrounding whitespace) are preserved; surrounding
   double-quote characters are preserved if present. Only the value is
   replaced. **A double-quoted value may contain internal whitespace and
   punctuation** — `password="correct horse battery" trailing` redacts
   the entire quoted phrase (`password="[REDACTED]" trailing`), not just
   the text up to the first space. An unquoted value still stops at the
   first whitespace, comma, semicolon, or ampersand, as before.

Every matched value is replaced with the literal text `[REDACTED]`.
Multiple secrets in the same message are each redacted independently.
Every character class used is bounded (never an unbounded `.+`), and
every message reaching this module has already been capped at
`--max-line-bytes` by the bounded reader — so this module's regex work
has a bounded worst case regardless of adversarial input shape.

## `--no-redact` risk

Passing `--no-redact` disables this pass entirely for that invocation.
**Any secret-shaped value present in the log file's messages will then
appear verbatim in the command's text or JSON output**, and in
`redact_message`'s absence, `redacted` is always `false` for that run.
Use `--no-redact` only when you understand and accept that risk — e.g.
against a synthetic fixture you control, never against a log file that
might contain real credentials, and never in an environment where the
resulting output could be captured, logged, or transmitted somewhere
you haven't reviewed.

## Limitations

**Default redaction is a best-effort mitigation for the documented
patterns above — it is not a guarantee that every secret-shaped value
in an arbitrary log message is found and removed.** In particular:

- Only the six key-name families listed above are matched. A
  differently-named secret field (e.g. `session_cookie=...`, a raw
  private key block, a credit-card number) is not redacted by this
  pass.
- Redaction operates on plain text patterns, not on structural
  understanding of the log format — a secret embedded in an unusual
  shape this module's regexes don't anticipate will not be caught.
- Redaction only ever touches the `message` field. If a secret ends up
  in `hostname`/`source` (a highly unusual but not impossible shape for
  a hand-crafted log line), it is not redacted.
- This module never claims to be a complete data-loss-prevention (DLP)
  tool. It exists specifically so a `logs parse`/`logs analyze` run
  against a real log file doesn't trivially leak the handful of most
  common credential-shaped values into a report by default.

## Why reports never contain a complete unredacted raw line

Redaction is only one of three layers that keep unredacted raw content
out of a report:

1. **The bounded reader never yields overlong-line content at all** —
   a line skipped for being longer than `--max-line-bytes` is reported
   only as a count and an issue code, never its bytes.
2. **Malformed-line and malformed-JSON issue details never echo the
   triggering line** — they describe the failure (`"no recognizable
   timestamp"`, `"invalid JSON"`) without reproducing the input.
3. **Redaction runs on `message` before an event is ever constructed**,
   when `--no-redact` is not passed — so the frozen `LogEvent` object
   itself, not just its later JSON serialization, already holds the
   redacted text.

Together, these mean a default (redacted) `logs parse`/`logs analyze`
JSON or text output can never contain the complete original line of a
secret-bearing log entry, only the fields this toolkit explicitly
documents — and even those fields have already had the documented
redaction patterns applied to their message text.
