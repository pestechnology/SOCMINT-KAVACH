"""
backend/ingestion/gravatar_scraper.py — Gravatar lookup (email seed).

Two tiers, verified live against api.gravatar.com/gravatar.com on 2026-07-04:

  1. Avatar existence check — GET /avatar/{sha256}?d=404. Genuinely free, no key:
     200 means this email has a Gravatar-linked avatar (a real, if weak, signal
     that the address is a real person's identity, not throwaway); 404 means none.
     The photo URL feeds the existing pHash / face-embedding pipeline exactly like
     any other discovered photo_url.
  2. Full profile (display name, verified linked accounts) via api.gravatar.com/v3 —
     despite older docs calling this "free, no key", Automattic now requires an
     API key (Bearer token, gravatar.com/developers) even for public profiles;
     confirmed by a live 404 "Profile not found" against a known public account
     with no key attached. Gated behind config.GRAVATAR_API_KEY; skipped (not an
     error) when unset.

Fail-safe: returns [] on any error, missing avatar, or missing/invalid key.
"""
from __future__ import annotations

import hashlib

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_AVATAR_URL = "https://www.gravatar.com/avatar/{h}"
_PROFILE_URL = "https://api.gravatar.com/v3/profiles/{h}"


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class GravatarScraper(BaseDataSource):
    name = "gravatar"

    async def _run_live(self, email: str) -> list[RawProfile]:
        if "@" not in (email or ""):
            return []
        h = _hash_email(email)
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                avatar_r = await client.get(_AVATAR_URL.format(h=h), params={"d": "404"})
            except Exception:
                return []
            has_avatar = avatar_r.status_code == 200

            profile: dict | None = None
            if config.GRAVATAR_API_KEY:
                try:
                    prof_r = await client.get(
                        _PROFILE_URL.format(h=h),
                        headers={"Authorization": f"Bearer {config.GRAVATAR_API_KEY}"},
                    )
                    if prof_r.status_code == 200:
                        profile = prof_r.json()
                except Exception:
                    profile = None

        if not has_avatar and not profile:
            return []

        metadata: dict = {"email": email}
        if has_avatar:
            metadata["photo_url"] = _AVATAR_URL.format(h=h)
        display_name = None
        linked_accounts: list[str] = []
        if isinstance(profile, dict):
            display_name = profile.get("display_name") or profile.get("name")
            for acct in (profile.get("verified_accounts") or []):
                url = acct.get("url") or acct.get("service_url")
                if url:
                    linked_accounts.append(url)
            loc = profile.get("location")
            if isinstance(loc, str) and loc.strip():
                metadata["location"] = loc.strip()[:60]
        if display_name:
            metadata["name"] = display_name
            metadata["fullname"] = display_name
        if linked_accounts:
            # Self-disclosed cross-platform links from a VERIFIED Gravatar profile —
            # near bio_url_match strength; correlation_engine's bio_url_match check
            # already scans the "bio"/"snippet" text for another account's URL, so
            # folding these into "bio" lets that existing signal fire with zero new code.
            metadata["bio"] = " ".join(linked_accounts)[:400]
            metadata["gravatar_verified_accounts"] = linked_accounts

        return [make_profile(
            "social_account", email, "gravatar",
            f"https://gravatar.com/{h}",
            metadata=metadata,
        )]
