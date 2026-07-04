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
import math
import re
from dataclasses import dataclass, field

from backend.ingestion.base_module import RawProfile
from backend.analysis.forensics import stylometry_similarity as _stylometry_similarity
from backend.analysis.forensics import BIO_STOPWORDS as _BIO_STOPWORDS
from backend.ingestion.photo_enrich import FACE_COSINE_THRESHOLD as _FACE_COSINE_THRESHOLD
from backend.ingestion.url_scraper import extract_handle as _extract_handle

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
    # ---- Sprint 7: more signal, more data (see scoring_engine.py's
    # HARD_ANCHOR_SIGNALS / _CONTEXT_SIGNALS for each signal's tier) ----
    # Biometric match via SFace embedding (photo_enrich.py) — same PERSON even in a
    # different photo. Independent of profile_photo_phash (same IMAGE FILE reused);
    # both can fire on the same pair from different evidence.
    "face_match": 40,
    # A bio/description that links to another account's OWN discovered profile URL —
    # self-disclosure, one of the strongest signals available (close to an exact
    # identifier match, hence weighted near exact_email_match).
    "bio_url_match": 55,
    # NER-derived employer/school and city mentions extracted from free text (LLM
    # path — see fact_enrich.py). More specific than generic bio_keyword_overlap but
    # LLM-derived, so kept below the deterministic exact/fuzzy name signals.
    "employer_overlap": 16,
    "city_match": 14,
    # Shared GitHub followers — ceiling weight for a 5+-overlap; see
    # _mutual_connections() below for the tiered curve and its reasoning.
    "mutual_connections": 20,
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
# bio_keyword_overlap used to filter against a tiny 19-word stopword list, so two
# TOTAL STRANGERS with generic bios ("photos and videos, follow for more" vs "check
# out my videos and photos, follow me for more") shared >=2 "keywords" (follow,
# videos, photos, more) and fired a correlation signal on pure social-media
# boilerplate. forensics.py already maintains a much larger (~250-word) curated
# list of function words + this exact kind of boilerplate for its keyword-extraction
# UI panel — reuse it here so the two features can't disagree about what counts as
# a "distinctive" shared word.
_STOPWORDS = _BIO_STOPWORDS

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


def _norm_email(s) -> str:
    """Email-specific normalization on top of _norm(): Gmail/Googlemail ignore dots
    in the local part and anything after a "+tag", so "vismay.hs@gmail.com" and
    "vismayhs+work@googlemail.com" are the SAME inbox as "vismayhs@gmail.com" —
    without this, exact_email_match (a 60-pt hard anchor) misses that a derived/
    guessed email is actually the seed's own address under a dotted variant."""
    s = _norm(s)
    if "@" not in s:
        return s
    local, _, domain = s.partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def _phone(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())[-10:]


def jaro_winkler(s1: str, s2: str) -> float:
    if not s1 or not s2: return 0.0
    if s1 == s2: return 1.0
    
    # Jaro
    # Floor at 0: for very short strings (len<=2) the raw formula goes negative, which
    # corrupts the matching window. 0 means "same index only", which is correct there.
    match_distance = max(0, max(len(s1), len(s2)) // 2 - 1)
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
        if min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a) or a.endswith(b) or b.endswith(a)):
            return "username_exact_match", 40
        # A short fragment contained in a longer handle (e.g. "jo" in "john123", "raj" in
        # "brajesh") is not evidence — it collides across countless unrelated handles.
        # Require the shorter string to be >=4 chars; otherwise fall through to fuzzy,
        # which demands high OVERALL similarity, not mere containment.
        if min(len(a), len(b)) >= 4:
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


_PHASH_MAX_HAMMING = 6   # of 64 bits


def _photo_match(ma: dict, mb: dict) -> bool:
    pa, pb = ma.get("photo_phash"), mb.get("photo_phash")
    if pa is not None and pb is not None:
        try:
            # profile_photo_phash is a HARD anchor (one more signal → HIGH), so the
            # threshold must be tight. imagehash's 64-bit pHash changes only ~1-4 bits
            # under re-encoding/resize of the SAME image, but two DIFFERENT photos with a
            # similar palette/composition can sit ~8-12 bits apart. The old <8 cutoff sat
            # inside that ambiguous band and risked anchoring on look-alike-but-different
            # avatars. <6 keeps tolerance for the same image while excluding look-alikes.
            return bin(int(pa, 16) ^ int(pb, 16)).count("1") < _PHASH_MAX_HAMMING
        except Exception:
            pass
    ua, ub = ma.get("photo_url"), mb.get("photo_url")
    return bool(ua and ub and ua == ub)


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _face_match(ma: dict, mb: dict) -> bool:
    """SFace embedding cosine similarity >= FACE_COSINE_THRESHOLD (photo_enrich.py's
    documented, model-calibrated cutoff — see that module's docstring for the source).
    Two profiles with NO embedding (no photo, or no face detected in the photo) are
    'no signal', never a match — see photo_enrich.py's fail-open-to-unset design."""
    ea, eb = ma.get("face_embedding"), mb.get("face_embedding")
    if not isinstance(ea, list) or not isinstance(eb, list):
        return False
    try:
        return _cosine(ea, eb) >= _FACE_COSINE_THRESHOLD
    except Exception:
        return False


_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)


def extract_bio_urls(text: str) -> list[str]:
    """Every http(s) URL embedded in free text (a bio/description field)."""
    return _URL_RE.findall(text or "")


def _bio_links_to(bio_text: str, target: RawProfile) -> bool:
    """True if `bio_text` contains a URL whose (platform, handle) — via the SAME
    parser url_scraper.py uses for its own cascade seeds — matches `target`'s own
    (platform, value). Self-disclosure: someone's GitHub bio linking to the exact
    Twitter account we independently discovered is strong standalone evidence."""
    t_plat, t_val = _norm(target.platform), _norm(target.value)
    if not t_plat or not t_val:
        return False
    for url in extract_bio_urls(bio_text):
        found = _extract_handle(url)
        if found and _norm(found[0]) == t_plat and _norm(found[1]) == t_val:
            return True
    return False


def _employer_overlap(ma: dict, mb: dict) -> bool:
    """metadata['employer_candidates'] is a NER-extracted list (fact_enrich.py), noisy
    by nature — require an exact (normalized) shared entry, not substring/fuzzy."""
    ea = {_norm(x) for x in (ma.get("employer_candidates") or []) if _norm(x)}
    eb = {_norm(x) for x in (mb.get("employer_candidates") or []) if _norm(x)}
    return bool(ea & eb)


def _city_match(ma: dict, mb: dict) -> bool:
    """Same as _employer_overlap but for metadata['location_candidates'] — NER-derived
    city mentions from free text, DISTINCT from the structured `location` field that
    location_overlap already reads (a bio can mention a city with no structured
    location field set at all)."""
    la = {_norm(x) for x in (ma.get("location_candidates") or []) if _norm(x)}
    lb = {_norm(x) for x in (mb.get("location_candidates") or []) if _norm(x)}
    return bool(la & lb)


def _mutual_connections(ma: dict, mb: dict) -> int | None:
    """Shared GitHub followers, weighted by overlap COUNT (not mere presence).

    Reasoning: any two moderately-followed tech accounts are likely to share a couple
    of ubiquitous followers by pure chance (a popular org bot, a well-known figure who
    follows thousands of people) — that is not evidence of a shared identity. But
    GitHub's follower graph has a long tail; two DIFFERENT unrelated people sharing
    5+ specific followers is a low-probability coincidence and starts to look like
    real social-graph evidence (the same person's alt account, or accounts followed
    by the same small real-world circle). Below 2 shared followers we treat it as
    noise (no signal at all); 2-4 is weak corroboration; 5+ is the ceiling weight.
    """
    fa = {_norm(x) for x in (ma.get("followers_sample") or []) if _norm(x)}
    fb = {_norm(x) for x in (mb.get("followers_sample") or []) if _norm(x)}
    overlap = len(fa & fb)
    if overlap < 2:
        return None
    if overlap < 5:
        return 10
    return SIGNAL_WEIGHTS["mutual_connections"]  # 20 — 5+ shared, ceiling weight


def _pair_signals(a: RawProfile, b: RawProfile) -> dict:
    ma, mb = a.metadata or {}, b.metadata or {}
    fired: dict = {}

    # exact identifier matches — use `or ""` to guard against explicit None values
    pa, pb = _phone(ma.get("phone") or ""), _phone(mb.get("phone") or "")
    if pa and pa == pb:
        fired["exact_phone_match"] = SIGNAL_WEIGHTS["exact_phone_match"]
    ea, eb = _norm_email(ma.get("email") or ""), _norm_email(mb.get("email") or "")
    if ea and ea == eb:
        fired["exact_email_match"] = SIGNAL_WEIGHTS["exact_email_match"]
    ua, ub = _norm(ma.get("upi") or ""), _norm(mb.get("upi") or "")
    if ua and ua == ub:
        fired["exact_upi_match"] = SIGNAL_WEIGHTS["exact_upi_match"]

    # username similarity (best single tier)
    usig = _username_signal(a.value, b.value)
    if usig:
        fired[usig[0]] = usig[1]

    # photo — two independent signals: exact image reuse, and same-person-different-photo.
    if _photo_match(ma, mb):
        fired["profile_photo_phash"] = SIGNAL_WEIGHTS["profile_photo_phash"]
    if _face_match(ma, mb):
        fired["face_match"] = SIGNAL_WEIGHTS["face_match"]

    # bio self-disclosure: A's bio links to B's own account, or vice versa
    bio_a = " ".join(str(ma.get(k) or "") for k in ("bio", "snippet"))
    bio_b = " ".join(str(mb.get(k) or "") for k in ("bio", "snippet"))
    if _bio_links_to(bio_a, b) or _bio_links_to(bio_b, a):
        fired["bio_url_match"] = SIGNAL_WEIGHTS["bio_url_match"]

    # NER-derived employer / city (fact_enrich.py) — distinct from the generic
    # bio_keyword_overlap and the structured-field location_overlap below.
    if _employer_overlap(ma, mb):
        fired["employer_overlap"] = SIGNAL_WEIGHTS["employer_overlap"]
    if _city_match(ma, mb):
        fired["city_match"] = SIGNAL_WEIGHTS["city_match"]

    # shared GitHub followers, weighted by overlap size
    mutual_pts = _mutual_connections(ma, mb)
    if mutual_pts is not None:
        fired["mutual_connections"] = mutual_pts

    # posting hours
    if _hours_jaccard(ma.get("posting_hours"), mb.get("posting_hours")) > 0.6:
        fired["posting_hours_overlap"] = SIGNAL_WEIGHTS["posting_hours_overlap"]

    # bio and snippet keyword overlap
    text_a = " ".join(filter(None, [str(ma.get("bio") or ""), str(ma.get("snippet") or ""), str(ma.get("title") or "")]))
    text_b = " ".join(filter(None, [str(mb.get("bio") or ""), str(mb.get("snippet") or ""), str(mb.get("title") or "")]))
    ka, kb = _keywords(text_a), _keywords(text_b)
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

    # real name overlap across metadata fields
    def _clean_name(meta: dict) -> str:
        n = str(meta.get("name") or meta.get("fullname") or meta.get("title") or "")
        for sep in (" - ", " | ", " (@", " • ", " / "):
            n = n.split(sep)[0]
        return _norm(n)
    na, nb = _clean_name(ma), _clean_name(mb)
    va, vb = _norm(a.value), _norm(b.value)
    if na and nb and len(na) >= 3 and len(nb) >= 3 and na != va and nb != vb:
        # A shared PLACEHOLDER name ("John Doe") or a lone common first name ("Ashwin") is
        # not identifying — demote the weight so two unrelated accounts can't be linked on
        # a common/fake name alone. Distinctive names ("Ashwin Harish") keep full weight.
        try:
            from backend.analysis.name_intel import is_generic_name
            generic = is_generic_name(na) or is_generic_name(nb)
        except Exception:
            generic = False
        exact_w = 8 if generic else SIGNAL_WEIGHTS["exact_name_match"]
        fuzzy_w = 6 if generic else SIGNAL_WEIGHTS["fuzzy_name_match"]
        if na == nb:
            fired["exact_name_match"] = exact_w
        elif (len(na) >= 8 and len(nb) >= 8) and (na in nb or nb in na):
            fired["exact_name_match"] = exact_w
        else:
            ratio = (_fuzz.ratio(na, nb) if _HAVE_FUZZ else int(difflib.SequenceMatcher(None, na, nb).ratio() * 100))
            if ratio >= 80:
                fired["fuzzy_name_match"] = fuzzy_w

    # location overlap — require at least 4-char strings to avoid
    # spurious substring matches like "new" matching "new york" AND "new delhi".
    la, lb = _norm(ma.get("location") or ""), _norm(mb.get("location") or "")
    if la and lb and len(la) >= 4 and len(lb) >= 4:
        if la == lb or la in lb or lb in la:
            fired["location_overlap"] = SIGNAL_WEIGHTS["location_overlap"]

    return fired


def correlate(profiles: list[RawProfile]) -> list[CandidatePair]:
    """Compare every profile against every other; return pairs that share >=1 signal.

    This is purely deterministic (rule-based signals only). LLM-based semantic
    matching is handled downstream by the reranker, which operates on the
    already-clustered output and makes a bounded number of calls.
    """
    pairs: list[CandidatePair] = []
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            fired = _pair_signals(profiles[i], profiles[j])
            if fired:
                pairs.append(CandidatePair(i=i, j=j, signals=fired))
    return pairs
