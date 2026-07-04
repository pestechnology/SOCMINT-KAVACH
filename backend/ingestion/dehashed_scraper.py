"""
backend/ingestion/dehashed_scraper.py — DeHashed breach-database lookup (email/phone).

DeHashed (dehashed.com) is a paid, lawful breach-search API used by security
researchers and OSINT investigators under a commercial subscription — same category
of tool as HIBP/XposedOrNot, just a broader (paid) index. Auth is HTTP Basic
(account email + API key), per DeHashed's documented API.

STUBBED IN THIS ENVIRONMENT: no DEHASHED_EMAIL/DEHASHED_API_KEY is configured here,
so this scraper returns [] every time it runs (see config.DEHASHED_API_KEY check
below) — exactly like every other optional-key scraper in this codebase (HIBP,
NumVerify) when its key is absent. The moment real credentials are added to .env,
this activates with zero other code changes needed.

Results feed the SAME metadata["breaches"] list that hibp_scraper.py /
xposedornot_scraper.py already populate, so correlation_engine.py's
breach_co_occurrence signal (including its _MEGA_BREACHES exclusion) picks up
DeHashed's results automatically — no correlation-engine changes required.

Fail-safe: [] on any error (missing key, non-200, malformed response, network
failure). Never raises.
"""
from __future__ import annotations

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_API = "https://api.dehashed.com/search"


class DehashedScraper(BaseDataSource):
    name = "dehashed"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        if not config.DEHASHED_API_KEY or not config.DEHASHED_EMAIL:
            return []
        field = "email" if "@" in (identifier or "") else "phone"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    _API,
                    params={"query": f"{field}:{identifier}", "size": 20},
                    auth=(config.DEHASHED_EMAIL, config.DEHASHED_API_KEY),
                    headers={"Accept": "application/json"},
                )
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            return []

        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list) or not entries:
            return []

        names = sorted({str(e.get("database_name")) for e in entries
                        if isinstance(e, dict) and e.get("database_name")})
        if not names:
            return []
        return [make_profile(
            "breach", identifier, "dehashed", "https://dehashed.com/",
            metadata={
                "breaches": names,
                "breach_count": len(names),
                "breach_name": ", ".join(names[:5]) + ("…" if len(names) > 5 else ""),
                "source": "dehashed",
            },
        )]
