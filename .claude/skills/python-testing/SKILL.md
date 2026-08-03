# Python Testing

Verify:

- Coverage stays at or above the 90% gate (`--cov-fail-under=90`).
- Optional-tool presence/absence is simulated via `monkeypatch` on
  `shutil.which`, never dependent on the real host's installed tools.
- Unsupported Python version / unsupported platform paths are simulated
  via injectable parameters, not by mutating `sys.version_info` directly.
- CLI exit codes (0/1/2) are asserted explicitly for every command path,
  including unknown commands and invalid `--format` values.
- JSON output is validated for both schema shape and Python field types
  (`bool` vs `str`, no stray `None`).
- Doctor check ordering is asserted deterministic across repeated calls.
- No test depends on network access, real subprocess/shell execution, or
  produces output at import time.
