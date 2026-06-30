"""
backend/ingestion/variants.py — username-variant generation.

The same person rarely uses an identical handle everywhere: "j.shankar" on one site
is "jshankar" / "j_shankar" / "shankarj" on others. Generating these variants and
re-running the username enumerators dramatically improves cross-platform recall — the
"build accuracy by finding the same person under different handles" idea.

Conservative on purpose: only well-formed variants derived from tokenisation, so we
don't flood the pipeline with garbage handles (which would create false leads).
"""
from __future__ import annotations

import re

_SEP_RE = re.compile(r"[._\-\s]+")


def _tokens(value: str) -> list[str]:
    return [t for t in _SEP_RE.split(value.strip().lower()) if t]


def username_variants(value: str, max_n: int = 5) -> list[str]:
    """Return up to max_n plausible alternate handles for a username/name seed.

    Excludes the original. Returns [] when nothing sensible can be derived
    (e.g. a single opaque token like 'ghostrider99' -> only the de-numbered form).
    """
    if not value:
        return []
    original = value.strip().lower()
    toks = _tokens(original)
    out: list[str] = []

    def add(candidate: str) -> None:
        c = candidate.strip("._-")
        if c and c != original and c not in out and 3 <= len(c) <= 40:
            out.append(c)

    if len(toks) >= 2:
        add("".join(toks))                  # j.shankar -> jshankar
        add(".".join(toks))                 #           -> j.shankar (== orig, skipped)
        add("_".join(toks))                 #           -> j_shankar
        rev = list(reversed(toks))
        add("".join(rev))                   #           -> shankarj
        add(".".join(rev))                  #           -> shankar.j
        add(toks[0][0] + toks[-1])          # arjun mehta -> amehta
    else:
        de_num = re.sub(r"\d+$", "", original)   # ghostrider99 -> ghostrider
        add(de_num)

    return out[:max_n]
