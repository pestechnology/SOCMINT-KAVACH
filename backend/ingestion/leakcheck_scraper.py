"""
backend/ingestion/leakcheck_scraper.py — LeakCheck breach-database lookup (email/phone).

LeakCheck (leakcheck.io) is a paid, lawful breach-search API, same category as HIBP/
XposedOrNot/DeHashed. Auth is a single API key sent as the X-API-Key header, per
LeakCheck's documented v2 API.

STUBBED IN THIS ENVIRONMENT: no LEAKCHECK_API_KEY is configured here, so this
scraper returns [] every time it runs (see config.LEAKCHECK_API_KEY check below) —
exactly like every other optional-key scraper in this codebase when its key is
absent. The moment a real key is added to .env, this activates with zero other code
changes needed.

Results feed the SAME metadata["breaches"] list that hibp_scraper.py /
xposedornot_scraper.py / dehashed_scraper.py already populate, so
correlation_engine.py's breach_co_occurrence signal picks up LeakCheck's results
automatically — no correlation-engine changes required.

Fail-safe: [] on any error (missing key, non-200, malformed response, network
failure). Never raises.
"""
from __future__ import annotations

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_API = "https://leakcheck.io/api/v2/query"


class LeakcheckScraper(BaseDataSource):
    name = "leakcheck"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        if not config.LEAKCHECK_API_KEY:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{_API}/{identifier}",
                    headers={"X-API-Key": config.LEAKCHECK_API_KEY, "Accept": "application/json"},
                )
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            return []

        results = data.get("result") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return []

        names = sorted({
            str((r.get("source") or {}).get("name"))
            for r in results
            if isinstance(r, dict) and isinstance(r.get("source"), dict) and r["source"].get("name")
        })
        if not names:
            return []
        return [make_profile(
            "breach", identifier, "leakcheck", "https://leakcheck.io/",
            metadata={
                "breaches": names,
                "breach_count": len(names),
                "breach_name": ", ".join(names[:5]) + ("…" if len(names) > 5 else ""),
                "source": "leakcheck",
            },
        )]
