# Aggregated Reports

`maops-py report aggregate` reads one or more `maops-py` JSON report
files and produces a single, normalized summary — for stitching together
the output of several separate `maops-py` invocations (e.g. a CI job that
ran `doctor`, `inventory system`, and `health http` separately) into one
combined pass/warn/fail view.

```bash
maops-py report aggregate REPORT [REPORT ...]
maops-py report aggregate REPORT [REPORT ...] --format text|json|markdown
maops-py report aggregate REPORT [REPORT ...] --output PATH
maops-py report aggregate REPORT [REPORT ...] --output PATH --force
```

## Supported report types

Exactly eight, detected **structurally** (a fixed set of distinguishing
JSON keys per type, checked in `core/report_aggregate.py`) — never
heuristically ("any object with an `overall` field is accepted"):

| Kind | Produced by |
|---|---|
| `doctor` | `maops-py doctor --format json` |
| `tools_inspect` | `maops-py tools inspect --format json` |
| `inventory_system` | `maops-py inventory system --format json` |
| `inventory_filesystem` | `maops-py inventory filesystem --format json` |
| `logs_parse` | `maops-py logs parse --format json` |
| `logs_analyze` | `maops-py logs analyze --format json` |
| `health_http` | `maops-py health http --format json` |
| `health_tcp` | `maops-py health tcp --format json` |

A JSON document that doesn't match any of these eight shapes is a
controlled validation failure (exit `2`) — `report aggregate` never
guesses, and never accepts an arbitrary JSON object just because it looks
report-shaped.

## Normalization: never a blind copy

Each detected report is normalized into a small, explicitly typed
`NormalizedReport` (`core/report_models.py`) before it ever reaches the
aggregate:

```json
{
  "source_path": "doctor.json",
  "kind": "doctor",
  "source_version": "0.6.0",
  "status": "pass",
  "headline": "11 check(s): 9 pass, 2 warn, 0 fail",
  "metrics": [
    {"label": "checks_total", "value": "11"},
    {"label": "checks_pass", "value": "9"},
    {"label": "checks_warn", "value": "2"},
    {"label": "checks_fail", "value": "0"}
  ]
}
```

The full input document (every individual check, tool, log event, or
health-check attempt) is **never** copied into the aggregate — only a
`status`, a one-line `headline`, and a small, fixed set of typed
`metrics` per report kind (counts, a hostname/root/path where that's the
report's own natural small identifier, never a captured stdout blob, a
per-line issue detail, or a log message). This keeps the aggregate's own
schema stable and bounded regardless of how large any single input report
is.

## Overall status

```
FAIL  if any normalized report is FAIL
WARN  if none FAIL and at least one WARNs
PASS  otherwise
```

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | Aggregate `overall` is `pass` or `warn`. |
| `1` | Aggregate `overall` is `fail`, or writing `--output` failed. |
| `2` | Usage/validation error — see below. |

Every one of the following is a `2` (checked, and short-circuiting,
report-by-report in the exact order given — the whole invocation fails on
the first problem found, never partially aggregating):

- Fewer than 1 or more than 50 report files supplied.
- A report file does not exist, is a directory, is a symbolic link
  (always refused, never followed), or is a non-regular file (FIFO,
  socket, device).
- A report file exceeds the maximum size (5 MiB by default).
- A report file is not valid UTF-8, not valid JSON, or its top-level JSON
  value is not an object.
- A report file's JSON is structurally recognized as none of the eight
  supported kinds, or is missing/mistyped a field that kind requires.

A malformed or hostile input file is always a controlled, typed failure —
this command never emits a Python traceback for malformed report input,
and never silently swallows a genuine programming error either (only the
specific, anticipated failure modes above are caught).

## Input safety

Reading each report file (`core/report_reader.py`) follows the same
fd-safety pattern `core/log_reader.py` established for reading log file
content: `os.lstat()` first (rejecting a nonexistent path, a directory, a
symlink, or a special file outright), then an `O_NOFOLLOW`/`O_CLOEXEC`
open, then `os.fstat()` verified against the pre-open `lstat()` result
(`(st_dev, st_ino)` comparison) to detect a path replaced between the
check and the open. Input order is always the exact order given on the
command line — never sorted, never reordered.

## Output formats

`--format text` (default), `--format json`, or `--format markdown`. Text
and Markdown both pass every externally sourced string (a report's path,
hostname, root, or log path) through the same sanitization boundary
`core/output.py` already uses for `logs`/`health` text rendering: control
characters, Unicode bidi-override/zero-width formatting characters (see
`docs/workflow-security.md` for why), and — Markdown only — Markdown
table/emphasis-breaking characters are all escaped before being
interpolated into a line. JSON output is unaffected (`json.dumps` already
escapes control characters correctly, and Unicode formatting characters
are valid JSON string content).

### Markdown escaping rationale

`_sanitize_for_markdown()` (`core/output.py`) runs every externally
sourced string through `_sanitize_for_text()` first (the control-
character/bidi-override/zero-width escaping above), then translates nine
additional characters that are significant to GitHub-flavored Markdown:

| Character | Escaped to | Why |
|---|---|---|
| `\` | `\\` | The escape character itself — must be escaped first, or a later escape (e.g. an already-escaped `\*`) could be reinterpreted by the renderer. |
| `` ` `` | `` \` `` | Opens inline code / fenced code blocks; unescaped, external text could break out of the surrounding line or start a fake code span. |
| `*` | `\*` | Opens emphasis/strong-emphasis runs; unescaped, external text could bold/italicize adjacent report content or leave a run unterminated. |
| `_` | `\_` | Same emphasis-run risk as `*`, GFM's other emphasis delimiter. |
| `\|` | `\\|` | A raw pipe inside a table cell (every `report aggregate`/`workflow run` metric is rendered as a table) would silently insert an extra column, corrupting the table structure rather than just the cell's content. |
| `[` | `\[` | Opens a Markdown link/reference; unescaped, external text combined with a later `]( ... )` could forge a link. |
| `]` | `\]` | Closes a Markdown link/reference — escaped together with `[` since either half alone can still combine with attacker-controlled text elsewhere on the line to form a link. |
| `<` | `\<` | Starts a raw HTML tag or autolink (`<https://...>`) in GFM; unescaped, external text could inject arbitrary HTML into a rendered report (e.g. on GitHub) or forge a clickable autolink. |
| `>` | `\>` | Closes a raw HTML tag/autolink, and on its own starts a blockquote at the beginning of a line; escaped alongside `<` for the same injection reason. |

This table is applied via a single `str.translate()` call
(`_MARKDOWN_SPECIAL_CHARS`) after control-character escaping, so a
Markdown-significant character can never reach the renderer un-escaped
regardless of where in an externally sourced field it appears — there is
no separate "safe" subset of Markdown syntax this boundary intentionally
allows through.

## Secure `--output` export

`--output PATH` writes the rendered content to a file instead of stdout,
using the exact same atomic-write primitive `maops-py config init`
established in v0.2.0 (shared verbatim with `workflow run --output` via
`commands/report.py:write_report_output()`):

- The output file is created at mode `0600`.
- Installation is atomic: content is written to a sibling temporary file
  in the same directory, `fsync`ed, then moved into place with
  `os.replace()` — a reader never observes a partially written file.
- An existing target is refused unless `--force` is given.
- A symbolic link at the target path is **always** refused, even with
  `--force` — `report aggregate` never writes through a symlink.
- The parent directory must already exist — `--output` never creates one.
- On any failure, the temporary file is removed; no partial or orphaned
  temp file is ever left behind.

## Example

```bash
maops-py doctor --format json > doctor.json
maops-py health http https://example.com/health --format json > health.json
maops-py report aggregate doctor.json health.json --format markdown --output summary.md
```
