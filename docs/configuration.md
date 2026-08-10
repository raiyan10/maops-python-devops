# Configuration

## Path selection

`maops-py` reads at most one TOML configuration file, resolved in this
order:

1. `MAOPS_PY_CONFIG_FILE` — an explicit path override, if set and
   non-empty.
2. `$XDG_CONFIG_HOME/maops-py/config.toml` — if `XDG_CONFIG_HOME` is set
   and non-empty.
3. `$HOME/.config/maops-py/config.toml` — the fallback.

Run `maops-py config path` to print the path that will actually be used,
without creating or reading anything.

This configuration file is consumed by `tools inspect` (for
`command_timeout_seconds`, `max_output_bytes`, and a default
`--format`), `logs parse`/`logs analyze` and `health http`/`health tcp`
(for a default `--format` only — neither reads `command_timeout_seconds`
or `max_output_bytes`), and `config show` (which reports it back).
`doctor` and both `inventory` commands (`inventory system`, `inventory
filesystem`) never read it: their `--format` always defaults to `text`,
so an invalid or malformed configuration file never affects their exit
code. See `docs/inventory.md` for why this was deliberately chosen for
`inventory` specifically.

`health http`/`health tcp`'s other flags (`--timeout`, `--retries`,
`--retry-delay`, `--workers`, `--method`, `--expect-status`) are
**command defaults only** — Day 5 deliberately introduces no new
persistent configuration keys for them. `--format` is the only
`health`-related value this configuration file can influence, resolved
via the identical CLI > environment > file > default precedence used
everywhere else in this document.

`report aggregate` and `workflow validate`/`workflow run` never read this
configuration file at all — like `doctor` and `inventory`, their
`--format` always defaults to `text` (with `markdown` as a third explicit
choice neither `doctor` nor `inventory` support), so a broken or missing
configuration file never affects either command's behavior or exit code.
Day 6 introduces no new persistent configuration keys.

## Supported keys

| Key | Type | Default | Constraints |
|---|---|---|---|
| `output_format` | string | `"text"` | must be `"text"` or `"json"` |
| `command_timeout_seconds` | number | `10.0` | `> 0`, `<= 300`; a boolean value is rejected, not silently accepted as numeric |
| `max_output_bytes` | integer | `65536` | `>= 1024`, `<= 1048576`; a boolean value is rejected, not silently accepted as an integer |

Any key outside this set is rejected — the file is treated as invalid,
not silently ignored. There are no secret, token, or credential fields,
and none will ever be added; `maops-py` never stores or reads
credentials.

## Example

```toml
output_format = "json"
command_timeout_seconds = 15.0
max_output_bytes = 131072
```

## Precedence

For each of `output_format` and `command_timeout_seconds`, the effective
value comes from the first source that supplies one:

```
explicit CLI argument
  -> MAOPS_PY_* environment variable
  -> configuration file
  -> built-in default
```

`max_output_bytes` has no CLI flag; its precedence chain is environment
-> file -> default. `maops-py config show` prints the effective value **and**
its source (`cli` / `environment` / `file` / `default`) for every key.

`config show`'s own `--format` flag, and `tools inspect`'s `--format`
flag, are rendering directives only — they choose how the report is
printed, and never feed back into the reported `output_format` value or
source. `tools inspect`'s `--timeout` flag *does* set the effective
`command_timeout_seconds` value for that invocation, with source `cli`.

## Environment variables

| Variable | Overrides |
|---|---|
| `MAOPS_PY_CONFIG_FILE` | the configuration file path itself |
| `MAOPS_PY_OUTPUT_FORMAT` | `output_format` (must be `text` or `json`) |
| `MAOPS_PY_COMMAND_TIMEOUT_SECONDS` | `command_timeout_seconds` |
| `MAOPS_PY_MAX_OUTPUT_BYTES` | `max_output_bytes` |

An invalid environment variable value (wrong type, out of range,
unparseable) is a clear operational error — the affected command fails
(exit `1`) with a message on stderr. It never silently falls back to the
configuration file or the built-in default.

## Validation behavior

- A **missing** configuration file is not an error: `maops-py` falls
  back to the environment/default for every key.
- A **malformed** file (invalid TOML syntax, or duplicate keys — rejected
  natively by the standard-library TOML parser) is invalid.
- A file containing an **unknown key** is invalid.
- A file with a key of the **wrong type or out of range** (including a
  boolean where a number or integer is expected) is invalid.

`maops-py config validate [PATH]` reports which of these applies and
exits `0` only when the file is genuinely valid. `maops-py config show`
never silently ignores an invalid file: if the file exists but is
invalid, `config show` fails operationally (exit `1`, an `Error: ...`
message on stderr) rather than printing a report with fabricated or
default-substituted values.

## Secure initialization

`maops-py config init` writes a documented template — every key present
as a commented-out example of its default, so a freshly initialized file
changes nothing until you deliberately edit it.

Guarantees:

- The parent directory is created if needed, but an *existing* parent
  directory's permissions are never modified.
- The file is written via a temporary file in the same parent directory,
  flushed and fsynced, then installed with `os.replace` — an atomic
  rename, so a concurrent reader never observes a partially written file,
  and any failure during the write leaves no temporary file behind.
- The file is created with mode `0600` (owner read/write only),
  independent of the caller's umask.
- An **existing regular file** is left untouched unless `--force` is
  given, in which case it — and only it — is replaced.
- A **symbolic link** at the target path is always refused, with or
  without `--force`. The link is never followed, and nothing is ever
  written through it.
- A **directory or other non-regular file** at the target path is always
  refused, regardless of `--force`.
- `config init` never removes files other than its own temporary file on
  a failure path, and never runs with elevated privileges.

There is a narrow window between checking the target path and installing
the new file (`os.replace` itself is atomic, but the check that precedes
it is not). This tool never opens or writes through the target path
directly — it always writes to a fresh temporary file first — so the
practical risk is limited to `os.replace` overwriting a file that
appeared at the target path after the check ran. This is accepted as a
single-user, no-`sudo`, locally-invoked CLI tool's usual threat model
(the same class of risk as `~/.gitconfig` or `~/.npmrc`), not a
guarantee against a co-resident adversary.
