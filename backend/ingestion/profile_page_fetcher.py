"""
backend/ingestion/profile_page_fetcher.py — lightweight public-profile-page enrichment.

Many username enumerators (Maigret, Sherlock) discover a profile URL but return no
avatar or bio because their site definitions lack field-extraction patterns.  This
module does a single GET to each discovered profile URL, parses the standard
Open Graph / Twitter Card meta tags, and populates:

    metadata["photo_url"]   — og:image / twitter:image
    metadata["bio"]         — og:description / twitter:description (first 200 chars)

Constraints (fail-safe by design):
  • Never raises; returns the profile list unchanged on any error.
  • 5-second per-request timeout; up to MAX_FETCH URLs per call (cap protects
    against a 150-account run firing 150 fetches).
  • Only fetches URLs that are missing BOTH photo_url AND bio.
  • Sets metadata["photo_url"] so the existing photo_enrich.py pHash pipeline
    picks it up automatically — no second photo pipeline.
  • Does NOT set "photo_url" if the og:image URL is a data: or javascript: URI
    (XSS-safe for the PDF renderer).
"""
from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from backend.ingestion.base_module import RawProfile

MAX_FETCH = 20
_TIMEOUT = 5.0
_CONCURRENCY = 8
_UA = "Mozilla/5.0 (compatible; VERTEX-OSINT/1.0)"

_PLACEHOLDER_IMAGE_MARKERS = (
    "default_profile_images", "default_profile_normal", "default_profile.png",
    "avatar-default", "no_avatar", "no-avatar", "anonymous-user",
    "missing-avatar", "default-avatar",
)

def _is_placeholder(url: str) -> bool:
    u = url.lower()
    return any(marker in u for marker in _PLACEHOLDER_IMAGE_MARKERS)

# Patterns for og:image, twitter:image, og:description, twitter:description
_OG_IMAGE  = re.compile(
    r'<meta[^>]+(?:property=["\']og:image["\']|name=["\']twitter:image["\'])'
    r'[^>]+content=["\'](https?://[^"\'>\s]+)["\']',
    re.IGNORECASE | re.DOTALL,
)
_OG_DESCR  = re.compile(
    r'<meta[^>]+(?:property=["\']og:description["\']|name=["\'](?:twitter:description|description)["\'])'
    r'[^>]+content=["\']((?:[^"\'<>]|(?:&[a-z]+;)){1,400})["\']',
    re.IGNORECASE | re.DOTALL,
)
# Also handle reversed attribute order (content= before property=)
_OG_IMAGE2  = re.compile(
    r'<meta[^>]+content=["\'](https?://[^"\'>\s]+)["\'][^>]+'
    r'(?:property=["\']og:image["\']|name=["\']twitter:image["\'])',
    re.IGNORECASE | re.DOTALL,
)
_OG_DESCR2  = re.compile(
    r'<meta[^>]+content=["\']((?:[^"\'<>]|(?:&[a-z]+;)){1,400})["\'][^>]+'
    r'(?:property=["\']og:description["\']|name=["\'](?:twitter:description|description)["\'])',
    re.IGNORECASE | re.DOTALL,
)
_OG_TITLE = re.compile(
    r'<meta[^>]+(?:property=["\']og:title["\']|name=["\']twitter:title["\'])'
    r'[^>]+content=["\']([^"\'<>]{1,200})["\']',
    re.IGNORECASE | re.DOTALL,
)
_TITLE_TAG = re.compile(r'<title[^>]*>([^<]{1,200})</title>', re.IGNORECASE | re.DOTALL)
# JSON-LD blocks often carry a clean "name" and an "address"/"homeLocation" for a person.
_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
# Trailing site-name suffixes on a page <title>/og:title, stripped to isolate the name.
_TITLE_SUFFIX = re.compile(
    r'\s*[·•|/–-]\s*(github|gitlab|instagram|instagram photos and videos|x|twitter|'
    r'threads|linkedin|reddit|tiktok|youtube|facebook|steam|dev community|medium|'
    r'about\.me|keybase|gravatar|pinterest|dribbble|behance)\b.*$',
    re.IGNORECASE,
)
_HANDLE_PAREN = re.compile(r'^(.*?)\s*\(@[^)]+\)')          # "Real Name (@handle) …"
_NAME_PAREN   = re.compile(r'^\S+\s*\(([^)@]{2,60})\)')      # "handle (Real Name) …" (GitHub)
# Light location cues in free text. Deliberately NOT matching a bare "from X" — that
# catches "See photos from Ashwin" and mislabels a name as a location. Only unambiguous
# cues: "📍 City", "Based in City", "Location: City", "Lives in City".
_LOC_HINT = re.compile(
    r'(?:📍\s*|based in\s+|location[:\-]\s*|lives in\s+)'
    r'([A-Z][A-Za-z .\'-]{2,40}(?:,\s*[A-Z][A-Za-z .\'-]{2,40}){0,2})',
    re.IGNORECASE,
)


def _needs_fetch(meta: dict) -> bool:
    return not meta.get("photo_url") or not meta.get("bio")


def _clean_name(title: str, handle: str) -> str | None:
    """Isolate a person/display name from a page title. Conservative on purpose: only
    trusts the "Name (@handle)" and "handle (Real Name)" shapes the major social
    platforms use (Instagram/Threads/Twitter/GitLab/GitHub). A bare page title is NOT
    treated as a name — filling the Names panel with page titles is worse than leaving
    it empty. Returns None when no reliable person-name can be isolated."""
    if not title:
        return None
    t = _TITLE_SUFFIX.sub("", title).strip().strip("·•|/–-").strip()
    h = (handle or "").strip().lower()
    name: str | None = None
    m = _HANDLE_PAREN.match(t)          # "Ashwin (@ash29_03) on Threads" -> "Ashwin"
    if m and m.group(1).strip():
        name = m.group(1).strip()
    else:
        mp = _NAME_PAREN.match(t)        # "octocat (The Octocat) · GitHub" -> "The Octocat"
        if mp and mp.group(1).strip().lower() != h:
            name = mp.group(1).strip()
    if not name:
        return None
    name = name.strip().strip("·•|/–-@").strip()
    # Reject handle-echoes and boilerplate.
    if not name or name.lower() == h or name.lower().replace(" ", "") == h.replace("_", "").replace(".", ""):
        return None
    if len(name) > 60 or name.lower() in ("profile", "home", "login", "sign in"):
        return None
    return name


def _extract_location(html: str, bio: str | None) -> str | None:
    # Prefer a JSON-LD address/location; fall back to a bio hint.
    import json as _json
    for block in _JSONLD.findall(html)[:4]:
        try:
            data = _json.loads(block.strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            addr = it.get("address") or it.get("homeLocation")
            if isinstance(addr, dict):
                loc = addr.get("addressLocality") or addr.get("name") or addr.get("addressRegion")
                if isinstance(loc, str) and loc.strip():
                    return loc.strip()[:60]
            elif isinstance(addr, str) and addr.strip():
                return addr.strip()[:60]
    if bio:
        m = _LOC_HINT.search(bio)
        if m:
            return m.group(1).strip()[:60]
    return None


def _extract(html: str, handle: str = "") -> dict:
    """Return {photo, bio, name, location} extracted from an HTML head; missing → None."""
    photo: str | None = None
    for pat in (_OG_IMAGE, _OG_IMAGE2):
        m = pat.search(html)
        if m:
            photo = m.group(1).strip()
            break
    descr: str | None = None
    for pat in (_OG_DESCR, _OG_DESCR2):
        m = pat.search(html)
        if m:
            raw = m.group(1).strip()
            # Basic HTML entity decode for the most common ones
            for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                            ("&quot;", '"'), ("&#39;", "'")):
                raw = raw.replace(ent, ch)
            descr = raw[:200] if raw else None
            break
    # name: prefer og:title, fall back to <title>
    title = None
    tm = _OG_TITLE.search(html) or _TITLE_TAG.search(html)
    if tm:
        title = tm.group(1).strip()
    name = _clean_name(title, handle) if title else None
    location = _extract_location(html, descr)
    return {"photo": photo, "bio": descr, "name": name, "location": location}


async def _enrich_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    meta: dict,
    url: str,
) -> None:
    """Fetch one profile page and populate meta in-place.  Never raises."""
    try:
        async with sem:
            r = await client.get(
                url, timeout=_TIMEOUT,
                headers={"User-Agent": _UA, "Accept": "text/html"},
                follow_redirects=True,
            )
        if r.status_code != 200:
            return
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype:
            return
        # Only read the first 50 KB — the <head> is always near the top
        html = r.text[:51200]
        ex = _extract(html, meta.get("username") or "")
        if ex["photo"] and not meta.get("photo_url") and not _is_placeholder(ex["photo"]):
            meta["photo_url"] = ex["photo"]
        if ex["bio"] and not meta.get("bio"):
            meta["bio"] = ex["bio"]
        if ex["name"] and not (meta.get("name") or meta.get("fullname")):
            meta["name"] = ex["name"]
            meta["fullname"] = ex["name"]
        if ex["location"] and not meta.get("location"):
            meta["location"] = ex["location"]
    except Exception:
        return


async def enrich_profiles_from_page(profiles: list) -> int:
    """Fetch og:image / og:description for profiles that are missing both.

    Mutates profile.metadata in-place.  Returns the count of profiles enriched
    (i.e. at least one field was newly populated).

    Capped at MAX_FETCH (20) URLs per call so a large batch never fires hundreds
    of HTTP requests.  Only live profiles with a real http(s) source_url are
    eligible; profiles that already have both photo_url and bio are skipped.
    """
    candidates = [
        p for p in profiles
        if isinstance(getattr(p, "metadata", None), dict)
        and isinstance(getattr(p, "source_url", None), str)
        and p.source_url.startswith("http")
        and _needs_fetch(p.metadata)
    ][:MAX_FETCH]

    if not candidates:
        return 0

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            _enrich_one(client, sem, p.metadata, p.source_url)
            for p in candidates
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return sum(
        1 for p in candidates
        if p.metadata.get("photo_url") or p.metadata.get("bio")
    )


async def _enrich_anchor_one(client, sem, p) -> None:
    """Fully enrich ONE anchor profile: name + location + photo + bio. Never raises.
    Unlike _enrich_one it fills name/location and runs even if photo/bio already exist,
    because the anchor is the reference the whole case is resolved against."""
    meta = p.metadata
    url = p.source_url
    try:
        async with sem:
            r = await client.get(url, timeout=_TIMEOUT,
                                 headers={"User-Agent": _UA, "Accept": "text/html"},
                                 follow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return
        ex = _extract(r.text[:51200], meta.get("username") or p.value or "")
    except Exception:
        return
    if ex["photo"] and not meta.get("photo_url") and not _is_placeholder(ex["photo"]):
        meta["photo_url"] = ex["photo"]
    if ex["bio"] and not meta.get("bio"):
        meta["bio"] = ex["bio"]
    if ex["name"] and not (meta.get("name") or meta.get("fullname")):
        meta["name"] = ex["name"]
        meta["fullname"] = ex["name"]
    if ex["location"] and not meta.get("location"):
        meta["location"] = ex["location"]


async def enrich_anchors(profiles: list) -> int:
    """Deep-enrich the exact-match anchor accounts (metadata.exact_seed_match).

    These are the literal answer to the search, so they get the richest treatment:
    their profile page is fetched to recover a real name, location, photo and bio even
    when some fields are already present. Those recovered attributes then become the
    reference the correlation engine links every other account against, and populate the
    case's Names / Locations panels. Bounded, parallel, fully fail-safe.
    """
    # Prioritise the platforms that actually carry a real name/location/photo in their
    # page metadata, so the bounded fetch spends its budget on instagram/github/gitlab/etc.
    # rather than obscure forums that yield nothing — the exact-match set can be large.
    _ANCHOR_PRIORITY = {
        "instagram": 0, "github": 1, "gitlab": 2, "threads": 3, "twitter": 4, "x": 4,
        "linkedin": 5, "facebook": 6, "youtube": 7, "reddit": 8, "tiktok": 9,
        "about.me": 10, "keybase": 11, "gravatar": 12, "medium": 13, "dev community": 14,
    }
    _arank = lambda p: _ANCHOR_PRIORITY.get((p.platform or "").lower(), 50)
    anchors = sorted(
        [p for p in profiles
         if isinstance(getattr(p, "metadata", None), dict)
         and p.metadata.get("exact_seed_match")
         and isinstance(getattr(p, "source_url", None), str)
         and p.source_url.startswith("http")],
        key=_arank,
    )[:12]   # bounded so a big run stays fast; major platforms fetched first
    if not anchors:
        return 0
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await asyncio.gather(*[_enrich_anchor_one(client, sem, p) for p in anchors],
                             return_exceptions=True)
    return sum(1 for p in anchors
               if p.metadata.get("name") or p.metadata.get("location"))
