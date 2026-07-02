"""
backend/ingestion/xposedornot_scraper.py — free breach lookup (no API key).

HIBP v3 requires a paid key (the project's .env ships a dummy one), so the breach
signal was dead. XposedOrNot exposes a free, key-less public API for the same kind of
data: which known breaches an email appears in. This populates metadata["breaches"]
so (a) the report shows real breach exposure and (b) the correlation engine's
breach_co_occurrence signal can fire when two emails share a breach.

Public, lawful breach-presence lookup (the same category as HIBP) — it returns the
NAMES of breaches an address is in, never passwords. Fail-safe: [] on any error.
"""
from __future__ import annotations

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class XposedOrNotScraper(BaseDataSource):
    name = "xposedornot"

    async def _run_live(self, email: str) -> list[RawProfile]:
        if "@" not in (email or ""):
            return []
        url = f"https://api.xposedornot.com/v1/check-email/{email}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, headers={"User-Agent": "VERTEX-OSINT"})
                if r.status_code != 200:  # 404 == not found in any breach
                    return []
                data = r.json()
        except Exception:
            return []

        # API returns {"breaches": [["Name1","Name2", ...]]} (nested) in practice;
        # handle nested-list, flat-list and dict shapes defensively.
        raw = data.get("breaches") if isinstance(data, dict) else None
        names: list[str] = []
        if isinstance(raw, list):
            for b in raw:
                if isinstance(b, list):
                    names.extend(str(x) for x in b if x)
                elif isinstance(b, dict):
                    n = b.get("breach") or b.get("name")
                    if n:
                        names.append(str(n))
                elif b:
                    names.append(str(b))
        names = sorted({n for n in names if n})
        if not names:
            return []

        return [make_profile(
            "breach", email, "xposedornot", "https://xposedornot.com/",
            metadata={
                "breaches": names,
                "breach_count": len(names),
                "breach_name": ", ".join(names[:5]) + ("…" if len(names) > 5 else ""),
                "source": "xposedornot",
            },
        )]
