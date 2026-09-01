"""
backend/ingestion/brave_scraper.py — Google-alternative search dorking via the Brave
Search API (api.search.brave.com), independent index (not a Google/Bing reseller).

Mirrors serper_scraper.py's shape and contract exactly, so it slots into
_seed_tool_map() as a THIRD parallel search source alongside SerperScraper, not a
replacement — every organic result becomes a RawProfile(type="web_mention") using the
same URL -> platform / username extraction helpers Serper already uses.

Needs config.BRAVE_API_KEY; returns [] without it (same fail-safe contract as every
other optional-key scraper in this codebase).

CAVEAT (from Brave's own docs, verified 2026-09-01): the site:/filetype: operators
this project's dork templates use are labelled "experimental" by Brave and MAY BE
SILENTLY DROPPED when too few results match a site:-scoped query — unlike Serper,
which just returns zero results in that case. There is no reliable way to detect
this from the response alone (no error, no flag). To keep every hit here trustworthy
for a "defensibility over volume" pipeline, `_run_live` defensively re-checks each
returned URL's host against the site: domain in the query template and drops any
result that doesn't actually match — so a silently-broadened Brave query can never
leak an off-target hit into the case as if it were platform-scoped evidence.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile
from backend.ingestion.serper_scraper import _platform_from_url, _extract_social_username

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# Pulls the domain out of a 'site:example.com "{q}"'-style template, e.g. "pastebin.com".
_SITE_OP_RE = re.compile(r"site:([a-z0-9.-]+)", re.I)


def _site_domain(query_template: str) -> str | None:
    m = _SITE_OP_RE.search(query_template)
    return m.group(1).lower() if m else None


def _host_matches_site(url: str, site_domain: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return False
    return host == site_domain or host.endswith("." + site_domain)


class BraveScraper(BaseDataSource):
    name = "brave"

    def __init__(self, query_template: str = '"{q}"', sensitive: bool = False):
        # Same template convention as SerperScraper, e.g. 'site:t.me "{q}"'.
        self.query_template = query_template
        self.sensitive = sensitive

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        if not config.BRAVE_API_KEY:
            return []
        query = self.query_template.format(q=identifier)
        site_domain = _site_domain(self.query_template)
        headers = {
            "X-Subscription-Token": config.BRAVE_API_KEY,
            "Accept": "application/json",
        }
        params = {"q": query, "count": 20, "safesearch": "off"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(_ENDPOINT, headers=headers, params=params)
            # The Search plan is rate-limited at the API-key level (50 qps); a burst of
            # parallel calls in one seed's fan-out can still trip it. One short retry,
            # same conservative policy serper_scraper.py and llm_client.py already use.
            if r.status_code == 429:
                await asyncio.sleep(1.5)
                r = await client.get(_ENDPOINT, headers=headers, params=params)
            if r.status_code != 200:
                return []
            try:
                data = r.json()
            except Exception:
                return []

        results = ((data.get("web") or {}).get("results")) or []
        out: list[RawProfile] = []
        platform_counts: dict[str, int] = {}
        is_general_query = site_domain is None
        for item in results[:20]:
            url = item.get("url", "")
            if not url:
                continue
            # See module docstring: Brave's site: operator is "experimental" and can be
            # silently dropped, so a scoped query must be defensively re-verified against
            # the actual returned host before it's trusted as platform-specific evidence.
            if site_domain and not _host_matches_site(url, site_domain):
                continue
            platform = _platform_from_url(url)
            if is_general_query:
                count = platform_counts.get(platform, 0)
                if count >= 3:
                    continue
                platform_counts[platform] = count + 1
            username = _extract_social_username(url, platform)
            value = username if username else item.get("title", identifier)
            meta = {"snippet": item.get("description"), "query": query}
            if username:
                meta["title"] = item.get("title", "")
            if self.sensitive:
                meta["sensitive_source"] = True
            out.append(make_profile("web_mention", value, platform, url, metadata=meta))
        return out
