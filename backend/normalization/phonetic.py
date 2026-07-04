"""phonetic.py — Indic-aware phonetic key from ISO-15919 Latin (deterministic).

WARNING: phonetic collision is real — many distinct names collapse to the same key. This is
exactly why the correlation signal built on it is LOW-WEIGHT and can never form a cluster on
its own (LINK_MIN_SIGNALS >= 2 still holds). It reinforces, it does not decide.
"""
from __future__ import annotations

import re
import unicodedata

# Handle honorifics / suffixes stripped as whole tokens AND as trailing suffixes.
# Analyst-reviewable — keep as an explicit constant.
_HONORIFICS = ("official", "real", "anna", "sri", "the", "mr")

_LONG_VOWELS = [("aa", "a"), ("ii", "i"), ("uu", "u"), ("ee", "e"), ("oo", "o")]
_CONSONANT = "bcdfghjklmnpqrstvwxyz"


def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def phonetic_key(latin_text: str) -> str:
    """Fold-and-collapse phonetic key. `Rajesh`, `raajesh_official`, `rajeshanna`, and the
    ISO transliteration of `ರಾಜೇಶ್` all produce the same key."""
    if not latin_text:
        return ""
    s = _strip_diacritics(latin_text.lower())
    # tokenize on non-alphanumerics; drop honorific tokens; rejoin
    tokens = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _HONORIFICS]
    s = "".join(tokens)
    if not s:
        return ""
    # strip a trailing honorific/handle suffix (e.g. "rajeshanna" -> "rajesh"), keeping >=3 chars
    for suf in sorted(_HONORIFICS, key=len, reverse=True):
        if s.endswith(suf) and len(s) - len(suf) >= 3:
            s = s[: -len(suf)]
            break
    # collapse long-vowel doubling
    for a, b in _LONG_VOWELS:
        s = s.replace(a, b)
    # cautious consonant folding: v/w -> v, sh -> s (NOT ph->f — keep aspiration minimal)
    s = s.replace("w", "v").replace("sh", "s")
    # drop repeated consonants (nn->n, ll->l, …)
    s = re.sub(rf"([{_CONSONANT}])\1+", r"\1", s)
    # final: alphanumerics only
    return re.sub(r"[^a-z0-9]", "", s)
