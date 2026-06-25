"""Signal computation — pure functions comparing two RawProfile objects.

Each signal function takes (p1, p2) and returns a SignalResult.
No side effects. No DB writes. Deterministic math only.
"""

import re
import logging

import Levenshtein

from backend.schemas import RawProfile, SignalResult

logger = logging.getLogger(__name__)

COMMON_NAMES = {
    # Common Indian names — most likely to collide in our demo
    "rahul kumar", "priya sharma", "amit patel", "anjali singh", "rohit verma",
    "neha gupta", "vikram rao", "sneha reddy", "arjun mehta", "pooja agarwal",
    "rajesh kumar", "deepika nair", "kiran shah", "manoj jha", "sunita devi",
    # Common Western names
    "john smith", "michael chen", "david lee", "sarah johnson", "emily davis",
    "james brown", "jennifer wilson", "robert garcia", "linda martinez",
    "michael smith", "john doe", "jane doe", "test user", "admin user",
    # Common single names (rare but happen)
    "rahul", "priya", "john", "admin", "user", "test"
}

# ── Signal weights (from architecture doc Section 7.1) ───────────────
SIGNAL_WEIGHTS: dict[str, int] = {
    "exact_phone_match": 40,
    "exact_email_match": 35,
    "username_exact_match": 30,
    "fullname_match": 28,
    "fullname_match_common": 14,  # for visibility, even though it's the override
    "username_substring_match": 15,
    "username_fuzzy_match": 10,
    "profile_photo_phash": 25,
    "posting_hours_overlap": 15,
    "stylometry_cosine": 20,
    "bio_keyword_overlap": 8,
}

MAX_POSSIBLE: int = sum(SIGNAL_WEIGHTS.values())  # 198

# ── Plain-English templates (one per signal) ─────────────────────────
SIGNAL_TEMPLATES: dict[str, str] = {
    "exact_phone_match": "Both accounts use the same phone number",
    "exact_email_match": "Both accounts share the same email address",
    "username_exact_match": "Both accounts use the identical username",
    "fullname_match": "Same display name across platforms",
    "username_substring_match": "One username contains the other as a substring",
    "username_fuzzy_match": "The usernames are very similar with minor variations",
    "profile_photo_phash": "Profile photos are visually identical",
    "posting_hours_overlap": "Both accounts are active during the same hours",
    "stylometry_cosine": "Writing style is highly similar",
    "bio_keyword_overlap": "Profile bios share multiple distinctive keywords",
}

# ── Stopwords for bio overlap ────────────────────────────────────────
_STOPWORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "and", "but", "or", "nor",
    "not", "no", "for", "with", "from", "this", "that", "these", "those",
    "it", "its", "i", "me", "my", "we", "our", "you", "your", "he", "she",
    "his", "her", "they", "them", "their", "to", "of", "in", "on", "at",
    "by", "as", "if", "so", "up", "out", "about", "into", "over", "after",
    "just", "also", "like", "love", "more", "some", "than", "very",
}


# ── Helpers to extract data from RawProfile metadata ─────────────────
def _get_phones(p: RawProfile) -> set[str]:
    """Extract and normalize phone numbers — last 10 digits, stripped."""
    phones: set[str] = set()
    raw: list[str] = []
    if p.metadata.get("phone"):
        raw.append(str(p.metadata["phone"]))
    raw.extend(p.metadata.get("phones_found", []))
    for ph in raw:
        digits = re.sub(r"\D", "", str(ph))
        if len(digits) >= 10:
            phones.add(digits[-10:])
    return phones


def _get_emails(p: RawProfile) -> set[str]:
    """Extract and lowercase emails."""
    emails: set[str] = set()
    if p.metadata.get("email"):
        emails.add(str(p.metadata["email"]).lower().strip())
    for em in p.metadata.get("emails_found", []):
        if em:
            emails.add(str(em).lower().strip())
    return emails


def _get_handle(p: RawProfile) -> str:
    """Get normalized handle from profile value."""
    return p.value.lower().strip().lstrip("@")


def _get_phash(p: RawProfile) -> str | None:
    """Get perceptual hash if present."""
    return p.metadata.get("photo_phash", "") or getattr(p, "profile_photo_phash", None) or p.metadata.get("profile_photo_phash", None)


def _get_bio(p: RawProfile) -> str:
    """Get bio text."""
    return str(p.metadata.get("bio", "") or getattr(p, "bio", ""))


def _get_posting_hours(p: RawProfile) -> set[int]:
    """Get set of active hours (0–23)."""
    return set(p.metadata.get("posting_hours", []))


def _hamming_hex(h1: str, h2: str) -> int:
    """Hamming distance between two hex-encoded hashes."""
    max_len = max(len(h1), len(h2))
    h1 = h1.ljust(max_len, "0")
    h2 = h2.ljust(max_len, "0")
    xor_val = int(h1, 16) ^ int(h2, 16)
    return bin(xor_val).count("1")


def _bio_keywords(bio: str) -> set[str]:
    """Extract meaningful keywords from bio (>= 4 chars, no stopwords)."""
    words = re.findall(r"[a-z]+", bio.lower())
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


# ── Signal functions ─────────────────────────────────────────────────

def exact_phone_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if any phone in p1 matches any in p2 (last 10 digits)."""
    name = "exact_phone_match"
    phones1 = _get_phones(p1)
    phones2 = _get_phones(p2)
    matched = bool(phones1 and phones2 and phones1 & phones2)
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def exact_email_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if any email in p1 matches any in p2 (lowercase)."""
    name = "exact_email_match"
    emails1 = _get_emails(p1)
    emails2 = _get_emails(p2)
    matched = bool(emails1 and emails2 and emails1 & emails2)
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def username_exact_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if normalized handles are identical."""
    name = "username_exact_match"
    h1, h2 = _get_handle(p1), _get_handle(p2)
    matched = bool(h1 and h2 and h1 == h2)
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def fullname_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """Fires when BOTH fullnames are non-empty, >= 5 chars, and match case-insensitively."""
    name = "fullname_match"
    fn1 = str(p1.metadata.get("fullname", "") or getattr(p1, "fullname", "")).strip()
    fn2 = str(p2.metadata.get("fullname", "") or getattr(p2, "fullname", "")).strip()
    matched = False
    weight = SIGNAL_WEIGHTS[name]
    detail = ""
    if fn1 and fn2 and len(fn1) >= 5 and len(fn2) >= 5:
        if fn1.lower() == fn2.lower():
            matched = True
            if fn1.lower() in COMMON_NAMES:
                weight = 14
                detail = f"Both accounts show the same display name '{fn1}' (common name, weaker signal)"
            else:
                detail = f"Same display name '{fn1}' across platforms"
    return SignalResult(
        signal_name=name,
        weight=weight,
        matched=matched,
        detail=detail,
    )


def username_substring_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if one handle is a substring of the other (min length 4, not exact)."""
    name = "username_substring_match"
    h1, h2 = _get_handle(p1), _get_handle(p2)
    matched = False
    if h1 and h2 and h1 != h2 and len(h1) >= 4 and len(h2) >= 4:
        matched = h1 in h2 or h2 in h1
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def username_fuzzy_match(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if Levenshtein distance < 3 AND not exact match."""
    name = "username_fuzzy_match"
    h1, h2 = _get_handle(p1), _get_handle(p2)
    matched = False
    if h1 and h2 and h1 != h2:
        dist = Levenshtein.distance(h1, h2)
        matched = dist < 3
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def profile_photo_phash(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if both pHashes non-empty AND Hamming distance < 8."""
    name = "profile_photo_phash"
    ph1, ph2 = _get_phash(p1), _get_phash(p2)
    matched = False
    if ph1 and ph2:
        try:
            matched = _hamming_hex(ph1, ph2) < 8
        except ValueError:
            matched = False
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def posting_hours_overlap(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if Jaccard of active hours-of-day > 0.6."""
    name = "posting_hours_overlap"
    h1, h2 = _get_posting_hours(p1), _get_posting_hours(p2)
    matched = False
    if h1 and h2:
        intersection = len(h1 & h2)
        union = len(h1 | h2)
        if union > 0:
            matched = (intersection / union) > 0.6
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


def stylometry_cosine(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """STUB — always returns matched=False. Will be filled in a later session."""
    name = "stylometry_cosine"
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=False,
        detail="",
    )


def bio_keyword_overlap(p1: RawProfile, p2: RawProfile) -> SignalResult:
    """True if >= 3 words (>=4 chars) common between bios after stopword removal."""
    name = "bio_keyword_overlap"
    bio1 = _get_bio(p1)
    bio2 = _get_bio(p2)
    matched = False
    if bio1 and bio2:
        kw1 = _bio_keywords(bio1)
        kw2 = _bio_keywords(bio2)
        matched = len(kw1 & kw2) >= 3
    return SignalResult(
        signal_name=name,
        weight=SIGNAL_WEIGHTS[name],
        matched=matched,
        detail=SIGNAL_TEMPLATES[name] if matched else "",
    )


# ── Registry ─────────────────────────────────────────────────────────
ALL_SIGNAL_FUNCTIONS = [
    exact_phone_match,
    exact_email_match,
    username_exact_match,
    fullname_match,
    username_substring_match,
    username_fuzzy_match,
    profile_photo_phash,
    posting_hours_overlap,
    stylometry_cosine,
    bio_keyword_overlap,
]


def compute_all_signals(p1: RawProfile, p2: RawProfile) -> list[SignalResult]:
    """Run every signal function on a pair of profiles."""
    return [fn(p1, p2) for fn in ALL_SIGNAL_FUNCTIONS]


def fired_signals(results: list[SignalResult]) -> list[SignalResult]:
    """Filter to only matched signals."""
    return [r for r in results if r.matched]
