"""
backend/ingestion/socid_enrich.py — socid_extractor enrichment pass.

profile_page_fetcher.py already recovers name/bio/location from generic Open
Graph tags, but many platforms socid_extractor (github.com/soxoj/socid-extractor)
recognises expose richer, site-specific structured fields (real name, location,
DOB, ...) via per-platform regex/JSON schemes it ships with. This module fetches
the page for profiles socid_extractor can parse and are still missing a name, and
fills metadata["name"] / ["fullname"] / ["location"] / ["dob_candidate"] the same
way profile_page_fetcher does — so exact_name_match / location_overlap can fire on
whatever it recovers, exactly like any other enrichment source.

Fail-safe by design: returns 0 / mutates nothing on any error, including
socid_extractor not being installed (optional dependency).
"""
from __future__ import annotations

import asyncio

import httpx

from backend.analysis.name_intel import is_plausible_name

MAX_FETCH = 15
_TIMEOUT = 5.0
_CONCURRENCY = 6
_UA = "Mozilla/5.0 (compatible; VERTEX-OSINT/1.0)"

_NAME_KEYS = ("fullname", "name", "full_name")
_LOCATION_KEYS = ("location", "city", "address", "current_location")
_DOB_KEYS = ("dob", "birthday", "birth_date", "date_of_birth")


def _needs_name(meta: dict) -> bool:
    return not (meta.get("name") or meta.get("fullname"))


def _map_fields(values: dict, meta: dict) -> bool:
    """Apply socid_extractor's field dict onto metadata in-place. Returns True if
    anything new was written."""
    changed = False
    if _needs_name(meta):
        for key in _NAME_KEYS:
            v = values.get(key)
            if isinstance(v, str) and v.strip() and is_plausible_name(v.strip()):
                meta["name"] = v.strip()
                meta["fullname"] = v.strip()
                changed = True
                break
    if not meta.get("location"):
        for key in _LOCATION_KEYS:
            v = values.get(key)
            if isinstance(v, str) and v.strip():
                meta["location"] = v.strip()[:60]
                changed = True
                break
    if not meta.get("dob_candidate"):
        for key in _DOB_KEYS:
            v = values.get(key)
            if isinstance(v, str) and v.strip():
                meta["dob_candidate"] = v.strip()[:40]
                changed = True
                break
    return changed


async def _enrich_one(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                      extract_fn, meta: dict, url: str) -> bool:
    try:
        async with sem:
            r = await client.get(url, timeout=_TIMEOUT,
                                 headers={"User-Agent": _UA, "Accept": "text/html"},
                                 follow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return False
        values = extract_fn(r.text)
        if not values:
            return False
        return _map_fields(values, meta)
    except Exception:
        return False


async def enrich_via_socid(profiles: list) -> int:
    """Run socid_extractor against profile pages still missing a name.

    Mutates profile.metadata in place. Returns the count of profiles that gained
    at least one new field. Bounded to MAX_FETCH profiles per call. Returns 0
    immediately (no fetches) if socid_extractor isn't installed.
    """
    try:
        from socid_extractor import extract as _extract
    except Exception:
        return 0

    candidates = [
        p for p in profiles
        if isinstance(getattr(p, "metadata", None), dict)
        and isinstance(getattr(p, "source_url", None), str)
        and p.source_url.startswith("http")
        and _needs_name(p.metadata)
    ][:MAX_FETCH]
    if not candidates:
        return 0

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_enrich_one(client, sem, _extract, p.metadata, p.source_url) for p in candidates],
            return_exceptions=True,
        )
    return sum(1 for r in results if r is True)
