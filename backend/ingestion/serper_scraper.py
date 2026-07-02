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
    """Best-effort platform label from a URL host.

    Use the second-level domain (the brand label), not the first sub-label —
    otherwise country subdomains like `in.linkedin.com` / `uk.linkedin.com` get
    mislabelled `in` / `uk` instead of `linkedin`.
    """
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        labels = [p for p in host.split(".") if p]
        if not labels:
            return "web"
        if len(labels) >= 2:
            return labels[-2]   # x.linkedin.com -> linkedin ; instagram.com -> instagram
        return labels[0]
    except Exception:
        return "web"


# Path segments that are NOT profile usernames on their respective platforms.
_NON_USERNAME_SEGMENTS = {
    "p", "reel", "reels", "explore", "stories", "i", "tv", "watch",
    "channel", "user", "c", "hashtag", "trending", "shorts",  # instagram / youtube
    "status", "intent", "search", "home",                      # twitter / x
    "feed", "jobs", "company", "school", "posts", "pulse",     # linkedin
    "wiki", "comments", "r", "search",                         # reddit (r/ caught separately)
}


def _extract_social_username(url: str, platform: str) -> str | None:
    """Extract the profile handle from a known social platform URL, or None.

    Returns None for post/media/collection URLs so they keep the full page
    title rather than a spurious path segment as their value.
    """
    try:
        path = urlparse(url).path.strip("/")
        if not path:
            return None
        parts = [seg for seg in path.split("/") if seg]
        if not parts:
            return None

        if platform == "linkedin":
            # /in/{username}  OR  /in/{username}/... → only exact profile paths
            if len(parts) >= 2 and parts[0] == "in":
                return parts[1]
            return None

        if platform in {"github", "gitlab"}:
            # /{username}  (repos are /{user}/{repo}, orgs are /orgs/*)
            if len(parts) == 1 and parts[0] not in _NON_USERNAME_SEGMENTS:
                return parts[0]
            return None

        if platform in {"instagram", "twitter", "tiktok"}:
            # /{username}/  OR  /{username}
            # Skip known non-profile first segments
            if parts[0] not in _NON_USERNAME_SEGMENTS:
                return parts[0]
            return None

        if platform == "reddit":
            # /u/{username}  OR  /user/{username}
            if len(parts) >= 2 and parts[0] in {"u", "user"}:
                return parts[1]
            return None

    except Exception:
        pass
    return None


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
                json={"q": query, "num": 20},
            )
            if r.status_code != 200:
                return []
            data = r.json()
        out = []
        platform_counts: dict[str, int] = {}
        is_general_query = "site:" not in self.query_template.lower()
        for item in data.get("organic", [])[:20]:
            url      = item.get("link", "")
            platform = _platform_from_url(url)
            if is_general_query:
                count = platform_counts.get(platform, 0)
                if count >= 3:
                    continue
                platform_counts[platform] = count + 1
            username = _extract_social_username(url, platform)
            # Use the extracted handle as the profile value when available so
            # _username_signal in the correlation engine can match it against
            # handles found by Maigret/Sherlock/GitHub (e.g. LinkedIn URL
            # /in/vismayhs → value="vismayhs" → exact_match against GitHub
            # value="VismayHS"). Store the original page title separately.
            value    = username if username else item.get("title", identifier)
            meta     = {"snippet": item.get("snippet"), "query": query}
            if username:
                meta["title"] = item.get("title", "")
            out.append(make_profile("web_mention", value, platform, url, metadata=meta))
        return out
