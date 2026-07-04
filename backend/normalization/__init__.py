"""
backend/normalization/ — deterministic multilingual identity normalization.

Stops the correlation engine from splitting one real person into several profiles just
because their name/handle appears in different scripts or romanizations (Kannada / Tamil /
Telugu / Malayalam / Latin). NOT a translation feature: the original-script string is the
evidence; transliteration and phonetic keys are investigator aids and are labelled as such.

Pure/deterministic — no LLM calls anywhere in this package.
"""
from .normalize import NormalizedIdentity, normalize_identity, annotate_profiles

__all__ = ["NormalizedIdentity", "normalize_identity", "annotate_profiles"]
