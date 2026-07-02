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
from backend.analysis.forensics import stylometry_similarity as _stylometry_similarity

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
    "exact_phone_match": 60,
    "exact_email_match": 60,
    "exact_upi_match": 60,
    "username_exact_match": 45,
    "username_substring_match": 20,
    "username_fuzzy_match": 15,
    "exact_name_match": 35,
    "fuzzy_name_match": 20,
    "location_overlap": 15,
    "profile_photo_phash": 35,
    "posting_hours_overlap": 15,
    "stylometry_cosine": 20,
    "breach_co_occurrence": 18,
    "bio_keyword_overlap": 12,
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

# Mega-breaches (hundreds of millions of unrelated accounts) — a lone shared one
# is not evidence two accounts belong to the same person. Lowercased.
_MEGA_BREACHES = {
    "collection-1", "collection #1", "collection1", "linkedin", "linkedinscrape-2021",
    "adobe", "canva", "dropbox", "myspace", "twitter", "twitter-scraped", "facebook",
    "facebook-marketplace", "yahoo", "tumblr", "myfitnesspal", "chegg", "wattpad",
    "zynga", "naz.api", "exploit.in", "exploitin", "000webhost", "dailymotion",
    "lastfm", "last.fm", "gravatar", "instagram", "deezer", "500px", "imgur",
}


def _norm(s) -> str:
    # str() so a stray list/int from a scraper can't raise AttributeError here.
    return str(s or "").strip().lower()


def _phone(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())[-10:]


def jaro_winkler(s1: str, s2: str) -> float:
    if not s1 or not s2: return 0.0
    if s1 == s2: return 1.0
    
    # Jaro
    match_distance = max(len(s1), len(s2)) // 2 - 1
    matches1 = [False] * len(s1)
    matches2 = [False] * len(s2)
    m = 0
    for i in range(len(s1)):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(s2))
        for j in range(start, end):
            if not matches2[j] and s1[i] == s2[j]:
                matches1[i], matches2[j] = True, True
                m += 1
                break
    if m == 0: return 0.0
    
    t = 0
    k = 0
    for i in range(len(s1)):
        if matches1[i]:
            while not matches2[k]: k += 1
            if s1[i] != s2[k]: t += 1
            k += 1
    t /= 2.0
    
    jaro = (m / len(s1) + m / len(s2) + (m - t) / m) / 3.0
    
    # Winkler
    prefix = 0
    for i in range(min(4, len(s1), len(s2))):
        if s1[i] == s2[i]: prefix += 1
        else: break
    return jaro + (prefix * 0.1 * (1.0 - jaro))


def _username_signal(a: str, b: str) -> tuple[str, int] | None:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return None
    if a == b:
        return "username_exact_match", SIGNAL_WEIGHTS["username_exact_match"]
    if a in b or b in a:
        return "username_substring_match", SIGNAL_WEIGHTS["username_substring_match"]
    
    # Advanced Fuzzy Matching using Jaro-Winkler (better for typological/phonetic errors)
    jw_score = jaro_winkler(a, b) * 100
    ratio = (_fuzz.ratio(a, b) if _HAVE_FUZZ
             else int(difflib.SequenceMatcher(None, a, b).ratio() * 100))
             
    if jw_score >= 85 or ratio >= 80:
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

    # exact identifier matches — use `or ""` to guard against explicit None values
    pa, pb = _phone(ma.get("phone") or ""), _phone(mb.get("phone") or "")
    if pa and pa == pb:
        fired["exact_phone_match"] = SIGNAL_WEIGHTS["exact_phone_match"]
    ea, eb = _norm(ma.get("email") or ""), _norm(mb.get("email") or "")
    if ea and ea == eb:
        fired["exact_email_match"] = SIGNAL_WEIGHTS["exact_email_match"]
    ua, ub = _norm(ma.get("upi") or ""), _norm(mb.get("upi") or "")
    if ua and ua == ub:
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

    # bio keyword overlap — guard against None bios from maigret
    ka, kb = _keywords(str(ma.get("bio") or "")), _keywords(str(mb.get("bio") or ""))
    if ka and kb and len(ka & kb) >= 2:
        fired["bio_keyword_overlap"] = SIGNAL_WEIGHTS["bio_keyword_overlap"]

    # stylometry / authorship — character n-grams + function-word distribution over
    # ALL collected text (bio + sampled posts), capturing writing STYLE not topic.
    ta = " ".join(str(ma.get(k) or "") for k in ("bio", "text_sample"))
    tb = " ".join(str(mb.get(k) or "") for k in ("bio", "text_sample"))
    if _stylometry_similarity(ta, tb) > 0.6:
        fired["stylometry_cosine"] = SIGNAL_WEIGHTS["stylometry_cosine"]

    # breach co-occurrence — but NOT on a single mega-breach. Collection #1,
    # LinkedIn, Adobe, etc. each contain hundreds of millions of unrelated
    # addresses, so a lone shared mega-breach is meaningless. Fire only if a
    # *rare* breach is shared, or two or more breaches are shared.
    bra = {str(x).lower() for x in (ma.get("breaches") or [])}
    brb = {str(x).lower() for x in (mb.get("breaches") or [])}
    shared = bra & brb
    if shared and (len(shared) >= 2 or (shared - _MEGA_BREACHES)):
        fired["breach_co_occurrence"] = SIGNAL_WEIGHTS["breach_co_occurrence"]

    # real name overlap
    na, nb = _norm(ma.get("name") or ""), _norm(mb.get("name") or "")
    if na and nb:
        if na == nb:
            fired["exact_name_match"] = SIGNAL_WEIGHTS["exact_name_match"]
        else:
            ratio = (_fuzz.ratio(na, nb) if _HAVE_FUZZ else int(difflib.SequenceMatcher(None, na, nb).ratio() * 100))
            if ratio >= 80:
                fired["fuzzy_name_match"] = SIGNAL_WEIGHTS["fuzzy_name_match"]

    # location overlap
    la, lb = _norm(ma.get("location") or ""), _norm(mb.get("location") or "")
    if la and lb:
        if la == lb or la in lb or lb in la:
            fired["location_overlap"] = SIGNAL_WEIGHTS["location_overlap"]

    return fired


from backend.llm.llm_client import LLMClient

def correlate(profiles: list[RawProfile]) -> list[CandidatePair]:
    """Compare every profile against every other; return pairs that share >=1 signal."""
    pairs: list[CandidatePair] = []
    llm = LLMClient()
    
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            fired = _pair_signals(profiles[i], profiles[j])
            if fired:
                pairs.append(CandidatePair(i=i, j=j, signals=fired))
            else:
                # If rule-based rules failed to find any exact match, let's try fuzzy holistic correlation
                # Only run this if we have rich metadata for both
                ma, mb = profiles[i].metadata or {}, profiles[j].metadata or {}
                if len(str(ma)) > 50 and len(str(mb)) > 50:
                    llm_score = llm.evaluate_match(ma, mb)
                    if llm_score >= 35:
                        fired["llm_holistic_match"] = llm_score
                        pairs.append(CandidatePair(i=i, j=j, signals=fired))
    return pairs
