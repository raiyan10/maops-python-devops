# Python Best Practices

Verify:

- Ruff-clean formatting and linting (PEP 8 conventions).
- Stdlib-only runtime dependencies for v0.1.0 — no third-party imports
  outside the `dev` optional-dependency group.
- Enums and dataclasses used for structured data instead of raw dicts or
  tuples passed around ad hoc.
- Functions kept small and single-purpose; no premature abstraction for
  hypothetical future commands.
- No unnecessarily narrow version pins in `pyproject.toml`.
