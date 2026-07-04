"""
backend/analysis/forensics.py — linguistic & behavioural forensics.

Two public entry points:

    stylometry_similarity(a, b) -> float        # authorship similarity of two texts
    summarize(entities) -> dict                 # case-level forensic summary

Stylometry uses authorship features (character n-grams + function-word frequency
distribution), which capture writing STYLE rather than topic — far more robust than
the previous word-unigram TF-IDF on two short bios. summarize() aggregates everything
the scrapers collected into the investigator-facing forensics block: sentiment / tone
(VADER), top keywords + hashtags, a merged activity-hour profile, and engagement
indicators. All optional deps degrade gracefully.
"""
from __future__ import annotations

import math
import re
from collections import Counter

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _VADER = SentimentIntensityAnalyzer()
except Exception:  # pragma: no cover
    _VADER = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAVE_SK = True
except Exception:  # pragma: no cover
    _HAVE_SK = False

# ~100 common English function words — their relative frequencies are a classic,
# topic-independent authorship fingerprint.
_FUNCTION_WORDS = (
    "the of and a to in is was he for it with as his on be at by i this had not are "
    "but from or have an they which one you were her all she there would their we him "
    "been has when who will more no if out so up said what its about than into them can "
    "only other new some could time these two may then do first any my now such like our "
    "over man me even most made after also did many before must through back years where "
    "much your way well down should because each just those people how too little state "
    "good very make world still see own men work long here get both between life being "
    "under never day same another know while last might us great old year off come since "
).split()
_FUNCTION_SET = set(_FUNCTION_WORDS)

_BOILERPLATE_NOISE = {
    "photos", "videos", "instagram", "profile", "samsung", "galaxy", "follow",
    "flight", "mesa", "tiktok", "number", "twitter", "facebook", "youtube",
    "github", "linkedin", "app", "sign", "up", "subscribers", "posts",
    "account", "user", "channel", "likes", "views", "share", "official",
    "page", "bio", "link", "click", "join", "online", "free", "content",
    "media", "platform", "social", "phone", "site", "source", "view",
    "see", "post", "like", "public", "create", "creating", "login",
    "www", "com", "net", "org", "gmail", "yahoo", "hotmail", "email",
    "dm", "rt", "amp", "http", "https", "that", "this", "with", "your",
    "from", "they", "what", "when", "been", "have", "has", "had", "got",
    "ago", "via", "you", "are", "was", "were", "his", "her", "him", "she",
    "them", "their", "our", "out", "for", "and", "the", "but", "not", "can",
    "all", "any", "get", "got", "picture", "photo", "image", "avatar",
    "check", "welcome", "about", "home", "search", "people", "groups",
    "member", "members", "group", "recent", "default", "contact", "info",
    "information", "status", "user", "users", "name", "full", "first", "last",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "here", "there", "where", "why", "how", "who", "whom", "whose", "which",
    "such", "much", "many", "more", "most", "some", "any", "every", "all",
    "only", "own", "other", "another", "same", "different", "new", "old",
}
_STOP = _FUNCTION_SET | _BOILERPLATE_NOISE
# Public alias — correlation_engine.py's bio_keyword_overlap signal reuses this
# curated ~250-word list (function words + social-media boilerplate) instead of
# maintaining its own much smaller stopword set.
BIO_STOPWORDS = _STOP
_HASHTAG_RE = re.compile(r"#(\w{2,40})")
_WORD_RE = re.compile(r"[A-Za-z']{3,}")


# --------------------------------------------------------------------------- #
#  Stylometry
# --------------------------------------------------------------------------- #
def _func_freq(text: str) -> Counter:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    fw = [w for w in words if w in _FUNCTION_SET]
    return Counter(fw)


def _cosine_counter(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def stylometry_similarity(a: str, b: str) -> float:
    """Authorship similarity in [0,1]. 0 if either text is too short to judge."""
    a, b = (a or "").strip(), (b or "").strip()
    if len(a) < 25 or len(b) < 25:
        return 0.0
    scores: list[float] = []
    # 1) character n-gram cosine (captures spelling/spacing/punctuation habits)
    if _HAVE_SK:
        try:
            v = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=1)
            m = v.fit_transform([a, b])
            scores.append(float(cosine_similarity(m[0], m[1])[0][0]))
        except Exception:
            pass
    # 2) function-word distribution cosine
    scores.append(_cosine_counter(_func_freq(a), _func_freq(b)))
    return round(sum(scores) / len(scores), 4) if scores else 0.0


# --------------------------------------------------------------------------- #
#  Case-level summary
# --------------------------------------------------------------------------- #
def _meta(e: dict) -> dict:
    m = e.get("metadata")
    if isinstance(m, dict):
        return m
    raw = e.get("metadata_json")
    if isinstance(raw, str) and raw:
        import json
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _texts(meta: dict) -> list[str]:
    out = []
    for k in ("bio", "snippet", "text_sample", "title"):
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def sentiment(text: str) -> dict:
    if not _VADER or not text.strip():
        return {"compound": 0.0, "label": "neutral"}
    c = _VADER.polarity_scores(text)["compound"]
    label = "positive" if c >= 0.4 else "negative" if c <= -0.4 else "neutral"
    return {"compound": round(c, 3), "label": label}


def summarize(entities: list[dict]) -> dict:
    """Aggregate the case's collected public text + metadata into a forensic profile."""
    texts: list[str] = []
    hours: Counter = Counter()
    posts_analyzed = 0
    followers_total = 0
    top_accounts: list[dict] = []
    platforms = set()
    n_breaches = 0
    n_services = 0

    for e in entities:
        m = _meta(e)
        texts.extend(_texts(m))
        if e.get("type") == "social_account":
            platforms.add((e.get("platform") or "").lower())
        if e.get("type") == "breach":
            n_breaches += int(m.get("breach_count") or len(m.get("breaches") or []))
        if e.get("type") == "email_registration":
            n_services += 1
        ph = m.get("posting_hours")
        if isinstance(ph, list):
            for h in ph:
                try:
                    hours[int(h)] += 1
                except Exception:
                    pass
        if m.get("posts_analyzed"):
            try:
                posts_analyzed += int(m["posts_analyzed"])
            except Exception:
                pass
        fc = m.get("follower_count")
        try:
            fc = int(fc)
        except Exception:
            fc = 0
        if fc:
            followers_total += fc
            top_accounts.append({"platform": e.get("platform"), "value": e.get("value"),
                                 "followers": fc})

    blob = "  ".join(texts)[:20000]

    # --- sentiment / tone ---
    sent = sentiment(blob)
    neg_texts = sum(1 for t in texts if sentiment(t)["label"] == "negative")
    tone = {
        **sent,
        "samples_analyzed": len(texts),
        "negative_samples": neg_texts,
        # heuristic flag for investigator attention (abusive/threatening tone)
        "flag_negative": bool(texts) and (sent["label"] == "negative" or neg_texts >= max(2, len(texts) // 3)),
    }

    # --- keywords + hashtags ---
    words = [w.lower() for w in _WORD_RE.findall(blob)]
    
    # 1. Gather explicit identifying names / tokens from entities so they get priority
    explicit_tokens: Counter = Counter()
    for e in entities:
        m = _meta(e)
        for k in ("name", "fullname", "username", "first_name", "last_name", "title", "query"):
            val = str(m.get(k) or e.get(k) or "").strip()
            if val and val.lower() != "null":
                val = val.split(" • ")[0].split(" | ")[0].replace("(@", " ").replace(")", " ")
                for tok in _WORD_RE.findall(val):
                    t_lower = tok.lower()
                    if t_lower not in _STOP and len(t_lower) >= 3 and not t_lower.isdigit():
                        explicit_tokens[t_lower] += 50  # Huge boost for actual person names / handles!

    # 2. Deterministic keyword baseline (frequency + boosted explicit name/handle tokens).
    # This runs on every poll incl. while the case is still RUNNING. The high-quality,
    # LLM-classified version comes from identity_agent.interests, which case_service swaps
    # into `keywords` once the case is COMPLETE — so we no longer make a second standalone
    # LLM keyword call here (that was redundant with the identity agent and cost an extra
    # call against Groq's per-minute limit on every results fetch).
    freq = Counter(w for w in words if w not in _STOP)
    combined = explicit_tokens + freq
    keywords = [w for w, _ in combined.most_common(15)]
    if explicit_tokens:
        # Guarantee top explicit names appear at the front of the final keyword list
        top_names = [w for w, _ in explicit_tokens.most_common(6) if w not in keywords]
        keywords = (top_names + keywords)[:15]

    hashtags = [h for h, _ in Counter(m.lower() for m in _HASHTAG_RE.findall(blob)).most_common(10)]

    # --- activity profile ---
    peak = sorted(hours.items(), key=lambda kv: kv[1], reverse=True)[:3]
    activity = {
        "posts_analyzed": posts_analyzed,
        "active_hours_utc": [h for h, _ in sorted(peak)],
        "histogram": {str(h): hours[h] for h in sorted(hours)},
        "available": bool(hours),
    }

    # --- engagement ---
    top_accounts.sort(key=lambda a: a["followers"], reverse=True)
    engagement = {
        "followers_total": followers_total,
        "top_accounts": top_accounts[:5],
        "available": bool(top_accounts),
    }

    return {
        "tone": tone,
        "keywords": keywords,
        "hashtags": hashtags,
        "activity": activity,
        "engagement": engagement,
        "footprint": {
            "platforms": sorted(p for p in platforms if p),
            "platform_count": len([p for p in platforms if p]),
            "breach_exposures": n_breaches,
            "registered_services": n_services,
            "text_samples": len(texts),
        },
    }
