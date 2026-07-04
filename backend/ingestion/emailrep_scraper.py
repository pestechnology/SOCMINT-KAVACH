"""
backend/ingestion/emailrep_scraper.py — EmailRep.io lookup (email seed).

Verified live on 2026-07-04: the unauthenticated endpoint now returns
HTTP 429 {"status": "fail", "reason": "the unauthenticated API is currently
disabled. please use an API key"} — despite older docs describing this as a
free no-key API, EmailRep now requires a (free-tier) key from emailrep.io for
any lookup. Gated behind config.EMAILREP_API_KEY; returns [] (not an error)
when unset, same as HIBP/NumVerify/DeHashed/LeakCheck.

What it adds once a key is configured:
  - details.profiles — which platforms this email is registered on (mirrors
    holehe_scraper.py's "email_registration" shape, so it participates in the
    same breach/registration corroboration path with zero new signal wiring).
  - details.disposable / details.deliverable — validates the address is real
    BEFORE spending Serper/enumerator budget on derived-email pivots.

Fail-safe: returns [] on any error, non-200, or missing key.
"""
from __future__ import annotations

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_API = "https://emailrep.io"


class EmailRepScraper(BaseDataSource):
    name = "emailrep"

    async def _run_live(self, email: str) -> list[RawProfile]:
        if not config.EMAILREP_API_KEY or "@" not in (email or ""):
            return []
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{_API}/{email}",
                    headers={"Key": config.EMAILREP_API_KEY, "Accept": "application/json"},
                )
            except Exception:
                return []
        if r.status_code != 200:
            return []
        try:
            data = r.json()
        except Exception:
            return []
        if data.get("status") != "success":
            return []

        details = data.get("details") or {}
        profiles: list[RawProfile] = []
        for platform in (details.get("profiles") or []):
            if not isinstance(platform, str) or not platform.strip():
                continue
            profiles.append(make_profile(
                "email_registration", email, platform.strip().lower(),
                f"https://emailrep.io/{email}",
                metadata={
                    "registered": True, "service": platform.strip().lower(),
                    "source": "emailrep", "email": email,
                    "disposable": bool(details.get("disposable")),
                    "deliverable": bool(details.get("deliverable")),
                    "reputation": data.get("reputation"),
                    "suspicious": bool(data.get("suspicious")),
                },
            ))
        return profiles

    async def is_valid_recipient(self, email: str) -> bool | None:
        """True/False when EmailRep confirms deliverability; None when unknown
        (no key configured, or the lookup failed) — callers should treat None as
        "don't know, proceed anyway" rather than as a rejection."""
        if not config.EMAILREP_API_KEY or "@" not in (email or ""):
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{_API}/{email}",
                    headers={"Key": config.EMAILREP_API_KEY, "Accept": "application/json"},
                )
                if r.status_code != 200:
                    return None
                data = r.json()
            except Exception:
                return None
        if data.get("status") != "success":
            return None
        details = data.get("details") or {}
        if details.get("disposable"):
            return False
        return bool(details.get("deliverable"))
