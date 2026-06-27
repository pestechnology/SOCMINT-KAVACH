"""
backend/correlation/correlation_engine.py

correlate(profiles) -> list of pairwise CandidatePair objects, each recording
which signals fired between two profiles and the points each signal is worth.

Heavy libraries (thefuzz, scikit-learn, imagehash) are OPTIONAL — the engine
degrades to stdlib (difflib) so it runs before `pip install`. The scoring
engine consumes the fired-signal dict; it does not re-derive anything here.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from backend.ingestion.base_module import RawProfile

# Optional accelerators ------------------------------------------------------
try:
    from thefuzz import fuzz as _fuzz  # type: ignore
    _HAVE_FUZZ = True
except Exception:
    _HAVE_FUZZ = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
    _HAVE_SKLEARN = True
except Exception:
    _HAVE_SKLEARN = False


# Signal weights (Section 7.1) ----------------------------------------------
SIGNAL_WEIGHTS = {
    "exact_phone_match": 40,
    "exact_email_match": 35,
    "exact_upi_match": 40,
    "username_exact_match": 30,
    "username_substring_match": 15,
    "username_fuzzy_match": 10,
    "profile_photo_phash": 25,
    "posting_hours_overlap": 15,
    "stylometry_cosine": 20,
    "breach_co_occurrence": 18,
    "bio_keyword_overlap": 8,
    "reciprocal_mention": 15,
}


@dataclass
class CandidatePair:
    i: int                       # index of profile A in the input list
    j: int                       # index of profile B
    signals: dict = field(default_factory=dict)   # signal_name -> points

    @property
    def num_signals(self) -> int:
        return len(self.signals)

    @property
    def raw_points(self) -> int:
        return sum(self.signals.values())


# --- helpers ---------------------------------------------------------------
_STOPWORDS = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "at",
             "dm", "me", "my", "now", "i", "is", "are", "with"}


def _norm(s) -> str:
    return (s or "").strip().lower()


def _phone(s) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())[-10:]


def _username_signal(a: str, b: str) -> tuple[str, int] | None:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return None
    if a == b:
        return "username_exact_match", SIGNAL_WEIGHTS["username_exact_match"]
    if a in b or b in a:
        return "username_substring_match", SIGNAL_WEIGHTS["username_substring_match"]
    ratio = (_fuzz.ratio(a, b) if _HAVE_FUZZ
             else int(difflib.SequenceMatcher(None, a, b).ratio() * 100))
    if ratio >= 80:
        return "username_fuzzy_match", SIGNAL_WEIGHTS["username_fuzzy_match"]
    return None


def _keywords(text: str) -> set:
    return {w for w in _norm(text).replace("|", " ").replace(",", " ").split()
            if len(w) > 2 and w not in _STOPWORDS}


def _hours_jaccard(a, b) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _photo_match(ma: dict, mb: dict) -> bool:
    pa, pb = ma.get("photo_phash"), mb.get("photo_phash")
    if pa is not None and pb is not None:
        try:  # hamming distance < 8
            return bin(int(pa, 16) ^ int(pb, 16)).count("1") < 8
        except Exception:
            pass
    ua, ub = ma.get("photo_url"), mb.get("photo_url")
    return bool(ua and ub and ua == ub)


def _pair_signals(a: RawProfile, b: RawProfile) -> dict:
    ma, mb = a.metadata or {}, b.metadata or {}
    fired: dict = {}

    # exact identifier matches
    if _phone(ma.get("phone")) and _phone(ma.get("phone")) == _phone(mb.get("phone")):
        fired["exact_phone_match"] = SIGNAL_WEIGHTS["exact_phone_match"]
    if _norm(ma.get("email")) and _norm(ma.get("email")) == _norm(mb.get("email")):
        fired["exact_email_match"] = SIGNAL_WEIGHTS["exact_email_match"]
    if _norm(ma.get("upi")) and _norm(ma.get("upi")) == _norm(mb.get("upi")):
        fired["exact_upi_match"] = SIGNAL_WEIGHTS["exact_upi_match"]

    # username similarity (best single tier)
    usig = _username_signal(a.value, b.value)
    if usig:
        fired[usig[0]] = usig[1]

    # photo
    if _photo_match(ma, mb):
        fired["profile_photo_phash"] = SIGNAL_WEIGHTS["profile_photo_phash"]

    # posting hours
    if _hours_jaccard(ma.get("posting_hours"), mb.get("posting_hours")) > 0.6:
        fired["posting_hours_overlap"] = SIGNAL_WEIGHTS["posting_hours_overlap"]

    # bio keyword overlap
    ka, kb = _keywords(ma.get("bio", "")), _keywords(mb.get("bio", ""))
    if ka and kb and len(ka & kb) >= 2:
        fired["bio_keyword_overlap"] = SIGNAL_WEIGHTS["bio_keyword_overlap"]

    # stylometry (optional, needs sklearn + enough text)
    if _HAVE_SKLEARN:
        ta, tb = ma.get("bio", ""), mb.get("bio", "")
        if len(ta) > 15 and len(tb) > 15:
            try:
                m = TfidfVectorizer().fit_transform([ta, tb])
                if cosine_similarity(m[0], m[1])[0][0] > 0.75:
                    fired["stylometry_cosine"] = SIGNAL_WEIGHTS["stylometry_cosine"]
            except Exception:
                pass

    # breach co-occurrence
    bra, brb = set(ma.get("breaches", []) or []), set(mb.get("breaches", []) or [])
    if bra and brb and bra & brb:
        fired["breach_co_occurrence"] = SIGNAL_WEIGHTS["breach_co_occurrence"]

    return fired


def correlate(profiles: list[RawProfile]) -> list[CandidatePair]:
    """Compare every profile against every other; return pairs that share >=1 signal."""
    pairs: list[CandidatePair] = []
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            fired = _pair_signals(profiles[i], profiles[j])
            if fired:
                pairs.append(CandidatePair(i=i, j=j, signals=fired))
    return pairs
