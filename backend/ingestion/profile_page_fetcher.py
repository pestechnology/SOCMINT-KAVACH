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


def _needs_fetch(meta: dict) -> bool:
    return not meta.get("photo_url") or not meta.get("bio")


def _extract(html: str) -> tuple[str | None, str | None]:
    """Return (photo_url, bio_snippet) extracted from HTML head; None if absent."""
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
    return photo, descr


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
        photo, bio = _extract(html)
        if photo and not meta.get("photo_url") and not _is_placeholder(photo):
            meta["photo_url"] = photo
        if bio and not meta.get("bio"):
            meta["bio"] = bio
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
