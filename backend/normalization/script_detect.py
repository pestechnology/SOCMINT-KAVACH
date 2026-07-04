"""script_detect.py — Unicode-block script detection (pure, no model)."""
from __future__ import annotations

# Unicode block → script name
_BLOCKS = [
    (0x0C80, 0x0CFF, "kannada"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0D00, 0x0D7F, "malayalam"),
]
_INDIC = {b[2] for b in _BLOCKS}


def char_script(ch: str) -> str | None:
    """Script class of a single alphabetic char, else None (digits/punct/space are neutral)."""
    if not ch.isalpha():
        return None
    cp = ord(ch)
    for lo, hi, name in _BLOCKS:
        if lo <= cp <= hi:
            return name
    if cp <= 0x024F:            # Basic Latin + Latin-1 + Latin Extended-A/B
        return "latin"
    return None                 # other scripts — ignored by this layer


def indic_scripts_present(text: str) -> list[str]:
    """Indic scripts present in `text`, in a stable order."""
    seen = []
    for ch in text or "":
        s = char_script(ch)
        if s in _INDIC and s not in seen:
            seen.append(s)
    return seen


def detect_script(text: str) -> str:
    """Return one of: 'kannada','tamil','telugu','malayalam','latin','mixed','unknown'.

    - Multiple Indic blocks, or an Indic block plus Latin → 'mixed'.
    - No classifiable letters → 'unknown'.
    """
    if not text or not text.strip():
        return "unknown"
    indic = set()
    latin = False
    for ch in text:
        s = char_script(ch)
        if s in _INDIC:
            indic.add(s)
        elif s == "latin":
            latin = True
    if not indic and not latin:
        return "unknown"
    if len(indic) > 1 or (indic and latin):
        return "mixed"
    if indic:
        return next(iter(indic))
    return "latin"
