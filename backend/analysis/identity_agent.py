"""
backend/analysis/identity_agent.py — LLM identity-resolution agent.

The Names/Locations panels used to be built by dumping every entity's raw name field
straight to the UI, which produced junk: a chess rating ("1796") shown as a name, the
handle ("@vismay_hs") shown as an alias, a location ("Vancouver, BC") shown as a name.

This agent consolidates the noisy per-account fragments (names, handles, bios, snippets,
titles, extracted locations/employers) into ONE clean, correctly-classified identity:

    classify(entities, case_id=None) -> {
        "real_names": [...],   # actual human names, Title Case, no handles/numbers
        "aliases":    [...],   # distinct usernames/handles (@ stripped)
        "locations":  [...],   # cities / regions / countries
        "employers":  [...],   # companies / schools / universities
    }

It is LLM-backed (the classification requires world knowledge — "is 'Kozhikode' a place
or a name?") with a deterministic fallback so it never blocks results, and it is cached
per case so it runs ~once (get_results is polled repeatedly). All text is HTML-unescaped
first (scraped fields arrive with entities like `&#064;` for `@`).
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter

try:
    from backend.analysis.forensics import _STOP as _FORENSIC_STOP
except Exception:  # pragma: no cover
    _FORENSIC_STOP = set()

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'+#-]{2,}")
# Generic bio filler that isn't a real interest/topic (the LLM path avoids these; this is
# only for the deterministic fallback when the LLM is unavailable).
_INTEREST_NOISE = {
    "loves", "love", "student", "player", "play", "based", "currently", "working",
    "work", "years", "year", "world", "life", "like", "using", "make", "building",
    "build", "things", "stuff", "here", "welcome", "everything", "anything", "just",
    "always", "learning", "learn", "passionate", "enthusiast", "lover", "fan",
}

# case_id -> (entity_count, result). get_results polls repeatedly; only recompute when the
# set of entities actually changes (i.e. once, when the investigation reaches its final count).
_CACHE: dict[str, tuple[int, dict]] = {}

_EMPTY = {"real_names": [], "aliases": [], "locations": [], "employers": [], "interests": []}

# Names that are platform/UI boilerplate, not people. Lowercased.
_NAME_DENY = {
    "closed user", "deleted user", "private account", "unknown", "unknown account",
    "user", "profile", "account", "instagram", "github", "twitter", "facebook",
    "youtube", "linkedin", "reddit", "telegram", "steam", "home", "login", "sign in",
    "not found", "page not found", "anonymous", "guest", "member", "official",
}
_UI_NOISE_RE = re.compile(
    r"\b(followers?|following|posts?|subscribers?|likes?|views?|see\s+(instagram|photos)|"
    r"photos?\s+and\s+videos|discover|profile|rating|played|games?)\b", re.I)
_HANDLE_RE = re.compile(r"^[@]?[a-z0-9._-]{2,30}$", re.I)   # single-token handle shape


def _clean(s) -> str:
    return html.unescape(str(s or "")).strip()


def _looks_like_real_name(s: str, known_handles: set[str]) -> bool:
    """Deterministic 'is this a human name' heuristic for the fallback path."""
    s = s.strip()
    if not s or len(s) > 60:
        return False
    low = s.lower()
    if low in _NAME_DENY or _UI_NOISE_RE.search(s):
        return False
    if any(ch.isdigit() for ch in s):          # "1796", "ash29_03"
        return False
    if s.startswith("@"):
        return False
    if low in known_handles:                    # equals a username we already have
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    tokens = s.split()
    # Real names are usually 2+ tokens (First Last). A lone token that matches a handle
    # shape (all one word, lowercase) is almost certainly a username, not a name.
    if len(tokens) == 1 and _HANDLE_RE.match(s) and s == low:
        return False
    return True


def _gather(entities: list[dict]) -> dict:
    """Pull the raw candidate fragments out of the entity metadata (HTML-unescaped)."""
    name_cands: list[str] = []
    handles: list[str] = []
    loc_cands: list[str] = []
    emp_cands: list[str] = []
    texts: list[str] = []
    for e in entities:
        m = e.get("metadata") or {}
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except Exception:
                m = {}
        for k in ("fullname", "name"):
            v = _clean(m.get(k))
            if v:
                name_cands.append(v)
        v = _clean(e.get("value"))
        if v:
            handles.append(v)
        for k in ("location",):
            v = _clean(m.get(k))
            if v:
                loc_cands.append(v)
        for k in ("location_candidates", "city_candidates"):
            for x in (m.get(k) or []):
                v = _clean(x)
                if v:
                    loc_cands.append(v)
        for x in (m.get("employer_candidates") or []):
            v = _clean(x)
            if v:
                emp_cands.append(v)
        for k in ("bio", "snippet", "title"):
            v = _clean(m.get(k))
            if v:
                texts.append(v)
    return {"name_cands": name_cands, "handles": handles,
            "loc_cands": loc_cands, "emp_cands": emp_cands, "texts": texts}


def _dedupe_ci(items: list[str], limit: int = 12) -> list[str]:
    out, seen = [], set()
    for it in items:
        k = it.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(it.strip())
        if len(out) >= limit:
            break
    return out


def _interests_from_texts(texts: list[str], exclude: set[str]) -> list[str]:
    """Deterministic interest/topic guess: most frequent content words in the bios that
    aren't stopwords, UI-noise, the person's own name tokens, or their handles."""
    freq: Counter = Counter()
    for t in texts:
        for w in _WORD_RE.findall(t.lower()):
            w = w.strip(".-'")
            if (len(w) >= 3 and w not in _FORENSIC_STOP and w not in exclude
                    and w not in _INTEREST_NOISE and not _UI_NOISE_RE.search(w)
                    and not any(c.isdigit() for c in w)):
                freq[w] += 1
    return [w for w, _ in freq.most_common(15)]


def _fallback(g: dict) -> dict:
    known_handles = {h.lower().lstrip("@") for h in g["handles"]}
    names = [n for n in g["name_cands"] if _looks_like_real_name(n, known_handles)]
    aliases = [h.lstrip("@") for h in g["handles"]]
    # exclude the person's own name/handle tokens from interests so it stops echoing them
    exclude = set(known_handles)
    for n in names:
        for tok in n.lower().split():
            exclude.add(tok)
    return {
        "real_names": _dedupe_ci(names, 10),
        "aliases": _dedupe_ci(aliases, 15),
        "locations": _dedupe_ci(g["loc_cands"], 10),
        "employers": _dedupe_ci(g["emp_cands"], 8),
        "interests": _interests_from_texts(g["texts"], exclude)[:12],
    }


_SYSTEM = (
    "You are an OSINT identity-resolution analyst. You receive fragments of text and "
    "metadata collected from many online accounts believed to belong to ONE person. "
    "Consolidate them into a single clean identity and classify every piece of "
    "information into exactly one field. Output ONLY strict JSON with keys "
    '"real_names", "aliases", "locations", "employers", "interests" (each an array of strings).\n'
    "Rules:\n"
    "- real_names: genuine human names (e.g. 'Vismay H S'). NEVER usernames, NEVER "
    "numbers (e.g. '1796' is a rating, not a name), NEVER platform names, NEVER UI text "
    "like 'Followers'/'See photos', NEVER locations.\n"
    "- aliases: the distinct usernames/handles the person uses; strip any leading '@'.\n"
    "- locations: cities, regions, or countries where the person lives or is from.\n"
    "- employers: companies, schools, or universities.\n"
    "- interests: the person's topics, skills, hobbies, or profession (e.g. 'chess', "
    "'league of legends', 'machine learning', 'photography'). These describe what the "
    "person is ABOUT. NEVER put their name, handle, location, or a platform name here. "
    "This field must NOT repeat anything already in real_names or aliases.\n"
    "- Deduplicate. Fix capitalization on names. If unsure whether a token is a real "
    "name, EXCLUDE it. Empty arrays are fine. No prose outside the JSON."
)


def classify(entities: list[dict], case_id: str | None = None) -> dict:
    """Return a clean, classified identity. LLM-backed with deterministic fallback.

    Cached per case_id keyed by entity count so repeated get_results polls don't re-run
    the LLM. Never raises.
    """
    if not entities:
        return dict(_EMPTY)
    if case_id and case_id in _CACHE and _CACHE[case_id][0] == len(entities):
        return _CACHE[case_id][1]

    g = _gather(entities)
    result = _fallback(g)   # always have a deterministic answer ready

    # Try to upgrade with the LLM agent (better classification of ambiguous tokens).
    try:
        from backend.llm.llm_client import LLMClient
        from backend import config
        payload = {
            "candidate_names": _dedupe_ci(g["name_cands"], 30),
            "handles": _dedupe_ci(g["handles"], 30),
            "location_hints": _dedupe_ci(g["loc_cands"], 20),
            "employer_hints": _dedupe_ci(g["emp_cands"], 20),
            "bio_text": "  ".join(g["texts"])[:2500],
        }
        llm = LLMClient()
        content = llm._chat_with_failover(
            config.LLM_EXTRACT_MODEL,
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": json.dumps(payload)[:3500]}],
            temperature=0.0, max_tokens=500,
        )
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content[4:] if content.startswith("json") else content
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(content[start:end + 1])
            if isinstance(data, dict):
                known_handles = {h.lower().lstrip("@") for h in g["handles"]}
                names = [_clean(x) for x in (data.get("real_names") or [])
                         if _looks_like_real_name(_clean(x), known_handles)]
                aliases = [_clean(x).lstrip("@") for x in (data.get("aliases") or []) if _clean(x)]
                locs = [_clean(x) for x in (data.get("locations") or []) if _clean(x)]
                emps = [_clean(x) for x in (data.get("employers") or []) if _clean(x)]
                # interests must not echo the person's name tokens or handles
                name_toks = {t for n in names for t in n.lower().split()} | known_handles
                interests = [_clean(x) for x in (data.get("interests") or [])
                             if _clean(x) and _clean(x).lower() not in name_toks]
                # Only accept the LLM result if it actually produced something usable;
                # otherwise keep the deterministic fallback.
                if names or locs or emps or aliases or interests:
                    result = {
                        "real_names": _dedupe_ci(names, 10),
                        "aliases": _dedupe_ci(aliases or g["handles"], 15),
                        "locations": _dedupe_ci(locs, 10),
                        "employers": _dedupe_ci(emps, 8),
                        "interests": _dedupe_ci(interests or result["interests"], 12),
                    }
    except Exception:  # noqa: BLE001 — any failure keeps the deterministic fallback
        pass

    if case_id:
        _CACHE[case_id] = (len(entities), result)
    return result
