"""
backend/agentic_browser/supadata.py — Supadata Web Reader client.

Supadata's /v1/web/scrape fetches ANY url server-side, rendering JS and getting past
anti-bot walls (verified: it returns real content for Cloudflare-protected Inflact where a
local stealth browser is blocked). Returns clean Markdown + page metadata, which our
extractor then turns into structured OSINT entities.

Fail-safe: never raises; returns None (unavailable) or a dict. Public sites only — it runs
unauthenticated from Supadata's servers, so login-gated sites need the authed_browser path.
"""
from __future__ import annotations

import httpx

from backend import config

_BASE = "https://api.supadata.ai/v1/web/scrape"
_TIMEOUT = 60.0


def available() -> bool:
    return bool(config.SUPADATA_API_KEY)


def scrape(url: str, no_links: bool = True) -> dict | None:
    """Fetch `url` via Supadata. Returns:
      {"ok": True, "url", "content" (markdown), "name", "description", "ogUrl", "chars"}
      {"ok": False, "status": int, "error": str}          on API error (e.g. 429, 402)
      None                                                 if no key configured.
    """
    if not config.SUPADATA_API_KEY:
        return None
    params = {"url": url}
    if no_links:
        params["noLinks"] = "true"
    try:
        r = httpx.get(_BASE, headers={"x-api-key": config.SUPADATA_API_KEY},
                      params=params, timeout=_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}"}
    if r.status_code != 200:
        detail = ""
        try:
            detail = (r.json() or {}).get("message") or r.text[:200]
        except Exception:  # noqa: BLE001
            detail = r.text[:200]
        return {"ok": False, "status": r.status_code, "error": detail}
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "status": 200, "error": "non-JSON response"}
    return {
        "ok": True,
        "url": j.get("url") or url,
        "content": j.get("content") or "",
        "name": j.get("name"),
        "description": j.get("description"),
        "ogUrl": j.get("ogUrl"),
        "chars": j.get("countCharacters"),
    }
