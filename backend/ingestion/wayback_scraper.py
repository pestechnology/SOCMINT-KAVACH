"""
backend/ingestion/wayback_scraper.py — Wayback Machine CDX API wrapper.

Queries the Wayback Machine CDX API to see if a URL has been archived.
If so, returns a RawProfile with the archive URL and timestamp.
Fail-safe: returns [] on any error or timeout.
"""
from __future__ import annotations

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class WaybackScraper(BaseDataSource):
    name = "wayback"

    async def _run_live(self, url: str) -> list[RawProfile]:
        # CDX API endpoint: http://web.archive.org/cdx/search/cdx
        # Params: url={url}, output=json, limit=1, fastLatest=true
        api_url = "http://web.archive.org/cdx/search/cdx"
        params = {
            "url": url,
            "output": "json",
            "limit": 1,
            "fastLatest": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(api_url, params=params)
                if r.status_code != 200:
                    return []
                data = r.json()
                if not data or len(data) < 2:
                    return []
                # data[0] is headers, data[1] is the latest capture
                # format: [urlkey, timestamp, original, mimetype, statuscode, digest, length]
                timestamp = data[1][1]
                archive_url = f"https://web.archive.org/web/{timestamp}/{url}"
                return [make_profile(
                    "web_mention", url, "wayback", archive_url,
                    metadata={"archived_at": timestamp, "source": "wayback"}
                )]
        except Exception:
            return []
