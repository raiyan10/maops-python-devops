# DevOps Review

Focus on when reviewing the Makefile and local dev workflow:

- `quality` runs exactly `format-check lint type-check coverage`.
- `release-check` runs exactly `quality build smoke-install`.
- `smoke-install` uses an isolated `mktemp` directory and a separate
  virtual environment, installs the built wheel (not an editable install),
  and cleans up only its own temp directory.
- `clean` removes only known generated artifacts — never a user-supplied
  or unbounded path.
- No target uses `sudo` or performs unrestricted deletion.
