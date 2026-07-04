"""normalize.py — orchestrates detect → transliterate → phonetic. Deterministic.

`normalize_identity()` returns a NormalizedIdentity whose `original` is the verbatim
evidentiary string; `translit`/`phonetic_key` are investigator aids (must be labelled as
such wherever they surface).
"""
from __future__ import annotations

from dataclasses import dataclass

from .script_detect import detect_script
from .transliterate import to_latin
from .phonetic import phonetic_key


@dataclass
class NormalizedIdentity:
    original: str        # verbatim, never altered — the evidentiary field
    script: str          # detect_script result
    translit: str        # ISO 15919 Latin (== original if already latin)
    phonetic_key: str    # reinforcing correlation signal (low-weight, never sufficient alone)


def normalize_identity(text: str) -> NormalizedIdentity:
    original = "" if text is None else str(text)
    script = detect_script(original)
    translit = to_latin(original, script)
    key = phonetic_key(translit)
    return NormalizedIdentity(original=original, script=script, translit=translit, phonetic_key=key)


def annotate_profiles(profiles) -> None:
    """Attach normalization results to each profile's metadata IN PLACE, before correlation.
    Sets metadata['phonetic_key'] (reinforcing signal) and, for non-Latin names, the labelled
    aids metadata['name_translit'] / ['name_script']. Never overwrites the original name.
    Fail-safe: skips any profile it can't process."""
    for p in profiles or []:
        try:
            m = getattr(p, "metadata", None)
            if not isinstance(m, dict):
                continue
            name = m.get("name") or m.get("fullname") or getattr(p, "value", "") or ""
            ni = normalize_identity(str(name))
            if ni.phonetic_key:
                m["phonetic_key"] = ni.phonetic_key
            if ni.script not in ("latin", "unknown") and ni.translit and ni.translit != ni.original:
                m["name_translit"] = ni.translit          # investigator aid — label on display
                m["name_script"] = ni.script
        except Exception:  # noqa: BLE001
            continue
