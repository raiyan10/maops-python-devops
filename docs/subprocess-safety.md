# Subprocess Safety

`src/maops_pydevops/core/runner.py` is the only module in this package
permitted to import `subprocess`. This document describes its full
contract, and the boundary of what Day 2 does and does not do.

## Argv, never a shell string

`run_command()` accepts a `CommandSpec` whose `argv` field is a
`tuple[str, ...]` — a pre-split argument vector. There is no code path
anywhere in this package that builds a command by string concatenation
or interpolation, and no function accepts a single shell-style command
string. `argv` is rejected outright (a typed `INVALID_SPEC` failure, no
`subprocess` call made) if it is empty or if any element contains a NUL
byte.

## `shell=False`, always

The single `subprocess.run(...)` call site in this package always passes
`shell=False` explicitly. No shell is ever invoked; shell metacharacters
in an argument (`;`, `|`, `` ` ``, `$(...)`, etc.) are passed to the
child process as literal, inert text — they are never interpreted.

## No arbitrary command-execution CLI in Day 2

`run_command()` is a reusable internal primitive, not a CLI surface.
The only command that reaches it is `maops-py tools inspect`, and only
with one of five **fixed, hardcoded** argv tuples:

| Tool | Fixed argv |
|---|---|
| `git` | `git --version` |
| `docker` | `docker --version` |
| `kubectl` | `kubectl version --client=true` |
| `terraform` | `terraform version` |
| `ansible` | `ansible --version` |

`tools inspect` resolves the tool name to an absolute executable path via
`shutil.which()` first, then substitutes only `argv[0]` (the executable)
with that absolute path — the rest of the fixed argv is never altered.
There is no flag, environment variable, or configuration key anywhere in
this package that lets a caller supply an arbitrary command, arbitrary
arguments, or a different tool than these five. Unsupported tool names are
rejected in `run_tools_inspect()` against the fixed allowlist, before any
tool resolution or execution is attempted (exit `2`). This check is
ordinary Python code rather than argparse `choices=` validation, because
`choices=` on the tool positional interacted with `nargs="*"`'s
implicit-`required` behavior in a way that differed between Python 3.11
and 3.12 — see `CHANGELOG.md`'s `[0.2.0]` "Fixed" entry for the full
root-cause explanation.

## Timeout behavior

Every invocation has a configurable timeout (`command_timeout_seconds`,
resolved via the usual CLI/environment/file/default precedence, or
`--timeout` for `tools inspect`). `subprocess.run(..., timeout=...)`
enforces it; `subprocess.TimeoutExpired` is caught and mapped to a
distinct `RunFailureReason.TIMEOUT`, with `timed_out=True` and any output
captured before the timeout preserved (truncated the same way as a
normal completion). Duration is measured with `time.monotonic()`, so it
is immune to wall-clock adjustments, and is reported even when the
command times out.

## stdout/stderr separation

stdout and stderr are captured independently and are never merged. A
`CommandResult` always has separate `stdout` and `stderr` fields; there
is no mode that combines them.

## Output truncation

Captured output is truncated to `max_output_bytes` **before** UTF-8
decoding, on the raw bytes — not after decoding to a string. Truncating
after decoding would measure characters, not bytes, and could silently
exceed the configured byte limit for non-ASCII output. A truncation that
lands mid-way through a multi-byte UTF-8 sequence decodes deterministically
via `errors="replace"` (a single U+FFFD at the cut point). `stdout_truncated`
and `stderr_truncated` are independent booleans, since either stream can
be truncated without the other being.

## Environment handling

Version-check invocations run with a fixed, noninteractive environment
overlay: `LC_ALL=C`, `LANG=C`, `NO_COLOR=1`, `PAGER=cat`, `GIT_PAGER=cat`,
`TERM=dumb`, `CHECKPOINT_DISABLE=1` — so tool version output is
locale-stable, never triggers an interactive pager, and never makes an
outbound network call. The last one specifically stops Terraform's CLI
from performing its default "checkpoint" call on `terraform version`;
without it, a real `terraform` binary on `PATH` would make a live network
request even though no code in this package ever touches a socket. The
rest of the parent process's environment is
inherited by the child (so `PATH`, `HOME`, etc. behave normally), but the
full environment is never included in a `CommandResult`, never logged,
and never printed — `run_command()` builds the child environment as a
local variable that is discarded after the call.

## Working-directory validation

An explicit working directory (when supplied) is validated with
`Path.is_dir()` before any subprocess is started; a missing or
non-directory path is a distinct, typed failure
(`INVALID_WORKING_DIRECTORY`) and never silently falls back to the
current directory.

## No logging, no network

`run_command()` never calls `print()` or configures logging — it is a
pure function from `CommandSpec` to `CommandResult`. It never imports
`socket` and makes no network calls of any kind.

## Limitations

- **Timeout scope**: `subprocess.run(..., timeout=...)` terminates the
  direct child process on timeout. It does not attempt to track or kill
  grandchild processes the child may have spawned (e.g. via its own
  shell fork) — this is a known, general limitation of process-group-
  unaware timeout handling in the standard library, not specific to this
  implementation.
- **`config init`'s TOCTOU window**: see `docs/configuration.md` for the
  narrow race between checking a target path and atomically installing a
  new file there.
- **This module does not make arbitrary subprocess execution "safe" in
  the abstract.** It makes the five fixed, read-only, allowlisted version
  checks that `tools inspect` performs safe to run without a shell, with
  bounded time and output, and without leaking environment data. A
  future feature that accepted user-supplied commands would need its own
  design and review — `core/runner.py`'s guarantees do not extend to
  commands this package does not itself choose.
