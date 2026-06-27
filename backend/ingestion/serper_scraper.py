"""
backend/ingestion/serper_scraper.py — Google search backbone via Serper.dev.

One class, reused for every seed type (email, username, name, upi, phone). Each
organic result becomes a RawProfile(type="web_mention"). For a NAME seed, the
orchestrator can run several site-scoped dorks; this class runs one query.

Needs config.SERPER_API_KEY; returns [] without it.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_ENDPOINT = "https://google.serper.dev/search"


def _platform_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        return host.split(".")[0] if host else "web"
    except Exception:
        return "web"


class SerperScraper(BaseDataSource):
    name = "serper"

    def __init__(self, query_template: str = '"{q}"'):
        # e.g. 'site:truecaller.com "{q}"' or 'site:linkedin.com/in "{q}"'
        self.query_template = query_template

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        if not config.SERPER_API_KEY:
            return []
        query = self.query_template.format(q=identifier)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                _ENDPOINT,
                headers={"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": 10},
            )
            if r.status_code != 200:
                return []
            data = r.json()
        out = []
        for item in data.get("organic", [])[:10]:
            url = item.get("link", "")
            out.append(make_profile(
                "web_mention", item.get("title", identifier),
                _platform_from_url(url), url,
                metadata={"snippet": item.get("snippet"), "query": query},
            ))
        return out
