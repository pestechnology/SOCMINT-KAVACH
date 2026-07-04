"""
backend/analysis/anchor_keywords.py — rarity-weighted anchor-keyword candidate booster.

Idea (user's): take the distinctive keywords from the EXACT-MATCH anchor account(s) — the
real name, the concatenated handle, the employer, the city — and check which other
discovered accounts mention them. Accounts that match the anchor's DISTINCTIVE keywords are
surfaced to the LLM adjudicator for a same-person verdict.

CRITICAL SAFETY DESIGN — this must not reduce the current version's accuracy:
  * It NEVER writes a score/tier/signal onto any cluster. It only produces a per-candidate
    relevance number used to ROUTE more candidates to the adjudicator (which still gates
    every link). Deterministic correlation/scoring is completely untouched.
  * Rarity weighting defeats the common-name trap that a naive keyword count would create:
      - weight = IDF over THIS case's own accounts (a term appearing in many discovered
        accounts is generic here -> low weight) ...
      - ... times a specificity factor that near-zeros common first names ("ashwin") and
        generic interests ("gaming", "music"), and boosts concatenated handles / rare
        multi-part tokens ("ashwinharish", "greywiz").
    So a candidate matching ONLY a common first name scores ~0 and never surfaces; one
    matching the rare full-handle or employer scores high.
  * Fail-safe and inert on tiny/empty cases (IDF is small) so it can't regress tests.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'#+._-]{2,}")

# Globally-common given names get near-zero weight even if they are locally rare in the
# case (IDF alone can't catch that). Focused on the tool's likely target population.
_COMMON_FIRST_NAMES = {
    "aarav", "aditya", "akash", "amit", "ananya", "anil", "anita", "anjali", "ankit",
    "arjun", "arun", "ashwin", "deepak", "divya", "gaurav", "harish", "karan", "kavya",
    "kiran", "krishna", "manish", "meera", "mohan", "neha", "nikhil", "pooja", "prakash",
    "pranav", "priya", "rahul", "raj", "rajesh", "ram", "ravi", "rohit", "sagar", "sanjay",
    "shreya", "shyam", "sneha", "sourav", "sri", "sunil", "suresh", "swati", "varun",
    "vijay", "vikas", "vikram", "vishal", "vivek", "yash",
    "aaron", "adam", "alex", "alice", "amy", "andrew", "anna", "ben", "bob", "brian",
    "carol", "chris", "dan", "dave", "david", "emily", "emma", "eric", "james", "jane",
    "jason", "jeff", "jenny", "john", "jose", "josh", "julia", "kevin", "laura", "lee",
    "linda", "lisa", "mark", "mary", "matt", "max", "mike", "nick", "paul", "peter",
    "rachel", "rob", "ryan", "sam", "sara", "sarah", "sean", "steve", "tom", "will",
}
_GENERIC = {
    "gaming", "gamer", "music", "photo", "photos", "video", "videos", "official", "real",
    "life", "world", "love", "fan", "art", "artist", "dev", "developer", "student",
    "engineer", "coder", "player", "content", "creator", "digital", "online", "team",
    "pro", "the", "and", "for", "you", "your", "new", "best", "free", "live", "follow",
}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) >= 3}


def _profile_text(p) -> str:
    m = getattr(p, "metadata", None) or {}
    parts = [str(p.value or "")]
    for k in ("name", "fullname", "bio", "snippet", "title"):
        parts.append(str(m.get(k) or ""))
    return " ".join(parts)


def _specificity(kw: str, is_concat: bool) -> float:
    """Globally-informed weight multiplier independent of this case's frequencies."""
    if kw in _COMMON_FIRST_NAMES or kw in _GENERIC:
        return 0.12
    if len(kw) < 4:
        return 0.0
    if is_concat or any(c.isdigit() for c in kw) or len(kw) >= 9:
        return 1.5     # concatenated handle / rare multi-part / long distinctive token
    return 1.0


def build_anchor_keywords(profiles) -> list[tuple[str, float]]:
    """Return [(keyword, weight)] built from the exact-match anchor accounts, weighted by
    rarity (IDF over the case) x specificity. Empty list if there is no anchor."""
    anchors = [p for p in profiles if (getattr(p, "metadata", None) or {}).get("exact_seed_match")]
    if not anchors or len(profiles) < 4:
        return []

    # Document frequency of every token across ALL discovered accounts (for IDF).
    N = len(profiles)
    df: Counter = Counter()
    for p in profiles:
        for t in _tokens(_profile_text(p)):
            df[t] += 1

    # Candidate keywords = distinctive tokens from the anchors: their handles, name tokens,
    # and — importantly — the CONCATENATION of the anchor's name tokens (e.g. "ashwinharish").
    concat: set[str] = set()
    raw: set[str] = set()
    for p in anchors:
        m = getattr(p, "metadata", None) or {}
        raw |= _tokens(str(p.value or ""))
        for k in ("name", "fullname"):
            name = str(m.get(k) or "")
            name_toks = [t for t in _WORD_RE.findall(name.lower()) if len(t) >= 2]
            raw |= set(name_toks)
            if len(name_toks) >= 2:
                concat.add("".join(name_toks))            # ashwin harish -> ashwinharish
        # employer/location candidates are distinctive by nature
        for k in ("location", "employer"):
            raw |= _tokens(str(m.get(k) or ""))
        for k in ("employer_candidates", "location_candidates", "city_candidates"):
            for x in (m.get(k) or []):
                raw |= _tokens(str(x))
        # Bio/snippet/title tokens too — the distinctive terms (employer, city, niche) often
        # live only in free text. Generic ones are removed by the specificity/IDF weighting
        # below; the surface threshold stops a lone generic-ish token from qualifying.
        for k in ("bio", "snippet", "title"):
            raw |= _tokens(str(m.get(k) or ""))

    out: dict[str, float] = {}
    for kw in raw | concat:
        is_concat = kw in concat
        spec = _specificity(kw, is_concat)
        if spec <= 0:
            continue
        # IDF: rare-in-this-case terms weigh more. Concatenations may not appear as their own
        # token in df (they're synthetic) -> treat df as 1 (maximally rare).
        d = df.get(kw, 1) if not is_concat else 1
        idf = math.log((N + 1) / (d + 1))
        w = round(idf * spec, 3)
        if w >= 0.5:                     # drop near-zero contributors
            out[kw] = max(out.get(kw, 0.0), w)
    # Cap to the top-20 most distinctive so the profile stays tight.
    return sorted(out.items(), key=lambda kv: kv[1], reverse=True)[:20]


def score_candidate(text: str, anchor_keywords: list[tuple[str, float]]) -> tuple[float, list[str]]:
    """Sum the weights of anchor keywords that appear in the candidate text.
    Returns (score, matched_keywords). Higher = more distinctive-keyword overlap."""
    if not anchor_keywords or not text:
        return 0.0, []
    low = text.lower()
    toks = _tokens(low)
    score = 0.0
    matched: list[str] = []
    for kw, w in anchor_keywords:
        # word-token match for normal keywords; substring for concatenated handles (they
        # may be embedded in a URL/handle e.g. "/ashwinharish").
        hit = kw in toks or (len(kw) >= 8 and kw in low)
        if hit:
            score += w
            matched.append(kw)
    return round(score, 3), matched
