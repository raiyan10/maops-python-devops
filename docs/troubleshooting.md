# Troubleshooting

## 1. `maops-py: command not found`

The console script is only on `PATH` inside the virtual environment it
was installed into. Activate it first: `source .venv/bin/activate`. As a
workaround, `python -m maops_pydevops` always works once the package is
installed, activated or not (as long as the interpreter you invoke is
the one with the package installed).

## 2. `pip install -e ".[dev]"` fails to find the package

Make sure you're running the command from the repository root (where
`pyproject.toml` lives) and that `src/maops_pydevops/__init__.py`
exists — `src`-layout packages are not discoverable if run from the
wrong working directory.

## 3. `doctor` reports `overall: fail`

Check the `checks` array (JSON) or the "Required checks" section (text)
for the specific check with `status: fail` — likely an unsupported
Python version, an unsupported OS family, or an unavailable temp
directory. Optional tool absence (git/docker/kubectl/terraform/ansible)
only ever produces a `warn`, never a `fail`.

## 4. `make coverage` fails below 90%

Run `pytest --cov=maops_pydevops --cov-report=term-missing` directly to
see exactly which lines/branches are uncovered, then add a targeted test
(prefer `monkeypatch` over depending on host state) rather than lowering
the threshold.

## 5. `make smoke-install` fails with "cannot access 'dist/*.whl'"

`smoke-install` expects a wheel to already exist in `dist/`. Run `make
build` first, or use `make release-check`, which runs `build` before
`smoke-install` automatically.

## 6. mypy strict errors on `argparse.Namespace` attribute access

Namespace attribute access is intentionally confined to `cli.py`'s small
`_dispatch_*` functions and `main()`. If you're seeing strict-mode
complaints elsewhere, it likely means `Namespace` (or raw parsed args)
leaked into `commands/` or `core/` — convert to a typed value at the
CLI boundary instead.

## 7. GitHub Actions failures on the pinned-action test

`tests/unit/test_actions_pinning.py` rejects any `uses:` reference that
isn't a full 40-character commit SHA with a trailing `# vX.Y.Z` comment.
If you bumped an action version, update the SHA (not just the comment)
to match the new release's actual commit.

## 8. `maops-py config show` / `config validate` reports the config file as missing

This is expected, not an error, the first time you run `maops-py` on a
machine: no configuration file exists yet, and every value falls back to
its built-in default. Run `maops-py config init` to create one, or check
`maops-py config path` to confirm which path is being checked
(`MAOPS_PY_CONFIG_FILE` > `$XDG_CONFIG_HOME/maops-py/config.toml` >
`$HOME/.config/maops-py/config.toml`).

## 9. `maops-py config show` / `config validate` exits 1 with an existing file

The file exists but failed validation — malformed TOML, a duplicate key,
an unknown key, or a value with the wrong type or out of range (see
`docs/configuration.md` for the full key reference). `config validate`
prints the specific reason; `config show` deliberately does not print a
report at all in this case, to avoid ever showing values that don't
correspond to a genuinely valid file.

## 10. `maops-py config init` refuses to write

`config init` refuses an existing regular file unless `--force` is
given, and always refuses a symbolic link or a directory at the target
path — `--force` never overrides those last two. This is intentional:
see `docs/configuration.md`'s "Secure initialization" section.

## 11. `maops-py tools inspect` shows a tool as `warn` instead of `pass`/`fail`

`warn` means the tool's executable was not found on `PATH` via
`shutil.which()` — no command was ever attempted for that tool. Install
the tool or adjust `PATH`; a missing tool never causes the overall result
to be `fail`, only `warn`, unless another selected tool actually failed
or timed out.

## 12. `maops-py tools inspect` shows a tool as `fail`

Either the tool's version command exited non-zero, timed out (see
`--timeout` and `command_timeout_seconds` in `docs/configuration.md`), or
the executable could not be run due to a permission error. Check the
`detail` field (or the text-format detail column) for which of these
applies; `stdout`/`stderr` (when not `null`) contain the tool's own
output for further diagnosis.

## 13. `maops-py inventory system`'s `distribution`/`memory`/`uptime` fields are `null`

`distribution` is only available where `platform.freedesktop_os_release()`
succeeds — typically Linux with a `/etc/os-release` file; it's `null`
(with `available: false`) on macOS, Windows, and minimal Linux images
without that file. `memory` and `uptime` are Linux-only by nature of
their data sources (`/proc/meminfo`, `/proc/uptime`) and are `null` on
every other platform. In every case, check the report's `issues` array
for the matching `component` and its `detail` for the specific reason —
this is expected, degraded-but-valid behavior, never an error, and never
affects the command's exit code (always `0` for a successfully-produced
report). See `docs/inventory.md` for the complete field-level contract.

## 14. `maops-py inventory filesystem` exits `1`

This means the scan **root** itself could not be classified at all — it
doesn't exist, or the invoking user cannot access it (check the printed
`Error:` message, which preserves the path you supplied exactly as
typed). This is the *only* condition that causes `inventory filesystem`
to exit non-zero: a permission-denied subdirectory, a file that
disappeared mid-scan, or any other per-entry issue *inside* an otherwise
valid tree is recorded in the report's `issues` array and sets `overall`
to `"warn"`, but never changes the exit code. See
`docs/filesystem-inventory-safety.md` for the full race-handling
contract.

## 15. `maops-py logs parse`/`logs analyze` exits `1`

Two distinct causes, both reported via the printed `Error:` message
(which preserves the path you supplied exactly as typed):

- The file itself could not be opened at all — it doesn't exist, is a
  directory, is a symbolic link (refused, never followed), is a FIFO/
  socket/block/character device, is not accessible, or was replaced
  between the safety check and the open (a detected race).
- The file **is** accessible and non-empty, but contained **zero
  parseable events** — every line was malformed under the selected
  `--input-format`. Try `--input-format auto` if you passed an explicit
  format that doesn't match the file's actual content.

A malformed/overlong line, an invalid timestamp, truncation, or any
`logs analyze` finding is **not** a reason for a non-zero exit — those
appear in `issues`/`findings` with `overall: "warn"` while still exiting
`0`. See `docs/log-parsing.md` and `docs/log-analysis.md` for the
complete exit-code semantics.

## 16. `maops-py logs parse`/`logs analyze` output still contains a value that looks like a secret

Default redaction (see `docs/log-redaction.md`) only matches the
documented key names (`password`, `passwd`, `pwd`, `token`,
`api_key`/`api-key`/`apikey`, `secret`, `access_key`/`access-key`,
`Bearer` tokens, and URI userinfo passwords) inside the `message` field.
A differently-named secret field, a value embedded in `hostname`/
`source`, or a secret shape this fixed pattern set doesn't recognize
will not be redacted — this is a documented, best-effort limitation, not
a bug. Confirm you did not pass `--no-redact`, which disables this pass
entirely for that invocation.

## 17. `maops-py logs parse` reports a BSD-style syslog event's `timestamp` as `null`

This is expected: a BSD-style timestamp (`Aug  6 10:30:00`) carries no
year or timezone in its own text, and this toolkit never infers either —
`timestamp` stays `null` with the original text preserved verbatim in
`timestamp_raw`, and no issue is raised, since this is documented,
correct behavior rather than degraded data. A `logs analyze` run over a
BSD-only file will show `time.timestamped_events: 0` and an empty peak
bucket for the same reason — see `docs/log-parsing.md` and
`docs/log-analysis.md`.
