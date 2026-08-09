"""Bounded, deterministic, best-effort secret redaction for log messages.

Applies only to already-extracted ``message`` text (never to raw lines,
never to structured fields like ``hostname``/``source``/``pid``). Every
pattern uses a bounded, non-catastrophic-backtracking character class, and
every message reaching this module has already been capped at
``max_line_bytes`` by ``core/log_reader.py``, so worst-case regex cost is
bounded regardless of input. This is a best-effort mitigation, not a
guarantee that every secret-shaped value is removed -- see
``docs/log-redaction.md``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_KEY_NAMES = r"(?:api[_-]?key|access[_-]?key|password|passwd|pwd|token|secret)"

#: Fixed, ordered redaction rules. Order matters: the two narrow/specific
#: patterns (Bearer tokens, URI userinfo passwords) run first so the
#: broader generic key=value rule -- which runs last -- only has to catch
#: whatever those two didn't already handle in the same message.
_REDACTION_RULES: tuple[re.Pattern[str], ...] = (
    # 1. "Bearer <token>" (covers "Authorization: Bearer ..." too, since
    #    the word "Bearer" is matched regardless of what precedes it).
    re.compile(r"(?i)\b(?P<key>Bearer)(?P<delim>\s+)[A-Za-z0-9._~+/=-]+"),
    # 2. URI userinfo password: scheme://user:PASSWORD@host -- keep
    #    "user:" and "@", redact only the password segment.
    re.compile(r"(?P<key>://[^:/@\s]+:)(?P<delim>)[^@\s]+(?=@)"),
    # 3. key=value / key: value style secrets -- keep the key name and
    #    delimiter, and the surrounding double quotes if present. A
    #    quoted value may contain whitespace/punctuation up to the closing
    #    quote; an unquoted value stops at the first delimiter-like
    #    character. Python's ``re`` forbids reusing a group name across
    #    alternatives, so the two branches use distinct names and a
    #    replacement callback picks the right one.
    re.compile(
        rf"(?i)\b(?P<key>{_KEY_NAMES})\b(?P<delim>\s*[:=]\s*)"
        r'(?:"(?P<qvalue>[^"]+)"|(?P<value>[^"\s,;&]+))'
    ),
)


def _replace_rule3(match: re.Match[str]) -> str:
    key = match.group("key")
    delim = match.group("delim")
    if match.group("qvalue") is not None:
        return f'{key}{delim}"[REDACTED]"'
    return f"{key}{delim}[REDACTED]"


_REPLACEMENTS: tuple[str | Callable[[re.Match[str]], str], ...] = (
    r"\g<key>\g<delim>[REDACTED]",
    r"\g<key>\g<delim>[REDACTED]",
    _replace_rule3,
)


def redact_message(message: str) -> tuple[str, bool]:
    """Redact secret-shaped values from ``message``.

    Returns ``(redacted_text, changed)``. ``changed`` is true iff at
    least one rule matched -- computed via each pattern's own match
    count (``subn``), never a second scanning pass.
    """
    text = message
    changed = False
    for pattern, replacement in zip(_REDACTION_RULES, _REPLACEMENTS, strict=True):
        text, count = pattern.subn(replacement, text)
        changed = changed or count > 0
    return text, changed
