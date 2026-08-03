# Python Review

Focus on when reviewing `src/maops_pydevops/` code:

- mypy strict compliance — no untyped public functions, no bare `Any`.
- Dataclass immutability — `frozen=True` where practical, no mutable
  default arguments.
- Explicit serialization — literal `to_dict()` construction, never
  `dataclasses.asdict()` blind-spreading or untyped dict merges.
- Parser/execution separation in `cli.py` — no command logic inside
  `build_parser()`.
- No duplicated command logic between the console-script entry point and
  `python -m maops_pydevops`.
- Exception handling — no bare `except: pass`, no silent swallowing.
- No import-time side effects (no computation, I/O, or logging config at
  module scope).
