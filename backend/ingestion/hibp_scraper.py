"""
backend/ingestion/hibp_scraper.py — Have I Been Pwned breach lookup (email seed).

CRITICAL: HIBP requires BOTH an 'hibp-api-key' header AND a 'user-agent' header.
Missing user-agent returns HTTP 403 — the #1 integration mistake. Returns [] on
any failure (including no key, 404 = no breaches).
"""
from __future__ import annotations

from urllib.parse import quote

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_API = "https://haveibeenpwned.com/api/v3/breachedaccount"


class HIBPScraper(BaseDataSource):
    name = "hibp"

    async def _run_live(self, email: str) -> list[RawProfile]:
        if not config.HIBP_API_KEY:
            return []
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_API}/{quote(email)}",
                headers={"hibp-api-key": config.HIBP_API_KEY, "user-agent": "VERTEX-OSINT"},
                params={"truncateResponse": "true"},
            )
        if r.status_code != 200:   # 404 = no breaches, anything else = problem
            return []
        out = []
        for breach in r.json():
            name = breach.get("Name", "unknown") if isinstance(breach, dict) else str(breach)
            out.append(make_profile(
                "breach", email, "hibp",
                f"https://haveibeenpwned.com/PwnedWebsites#{name}",
                metadata={"breach_name": name, "breaches": [name]},
            ))
        return out
