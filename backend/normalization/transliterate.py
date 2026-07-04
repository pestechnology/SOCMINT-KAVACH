"""transliterate.py — Indic script → ISO 15919 Latin via aksharamukha (deterministic).

Diacritic-preserving ISO output here (reversible/inspectable). Diacritic folding happens in
phonetic.py, kept separate on purpose. If aksharamukha is unavailable, the input is returned
unchanged (fail-open) — callers must not treat transliteration as evidence anyway.
"""
from __future__ import annotations

from .script_detect import indic_scripts_present

# our script names → aksharamukha source-script names
_AKSHARA = {"kannada": "Kannada", "tamil": "Tamil", "telugu": "Telugu", "malayalam": "Malayalam"}


def _process(source_name: str, text: str) -> str:
    from aksharamukha import transliterate  # imported lazily; hard dep declared in requirements
    return transliterate.process(source_name, "ISO", text)


def to_latin(text: str, source_script: str) -> str:
    """Transliterate Indic text to ISO 15919. 'latin' returned unchanged."""
    if not text:
        return ""
    if source_script == "latin":
        return text
    if source_script in _AKSHARA:
        try:
            return _process(_AKSHARA[source_script], text)
        except Exception:  # noqa: BLE001
            return text
    if source_script == "mixed":
        # Apply each Indic script present. aksharamukha only rewrites its source script's
        # characters and leaves Latin/other runs in place, so sequential passes preserve
        # the original order and the Latin segments.
        result = text
        for sc in indic_scripts_present(text):
            try:
                result = _process(_AKSHARA[sc], result)
            except Exception:  # noqa: BLE001
                pass
        return result
    return text  # 'unknown' / other — unchanged
