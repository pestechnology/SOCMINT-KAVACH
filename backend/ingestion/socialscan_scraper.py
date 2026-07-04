"""
backend/ingestion/socialscan_scraper.py — high-confidence username availability check.

socialscan checks ~10 major platforms (Instagram, Twitter, GitHub, GitLab, Tumblr,
Lastfm, Reddit, Snapchat, Yahoo, Pinterest) by mimicking real registration flows.
Where Maigret/Sherlock guess from HTTP status, socialscan is high-confidence for the
platforms it covers, so it corroborates the enumerators.

Uses the socialscan **async Python API** (`execute_queries`) — the 1.4.2 CLI has no
machine-readable output, so the old `--json` subprocess approach always returned [].
A platform is TAKEN (account exists) when available is False AND the check succeeded
(valid + success). Fail-safe: [] if socialscan is missing or anything errors.
"""
from __future__ import annotations

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

# Public profile URL templates for the platforms socialscan covers.
_URL = {
    "instagram": "https://instagram.com/{u}",
    "twitter": "https://twitter.com/{u}",
    "github": "https://github.com/{u}",
    "gitlab": "https://gitlab.com/{u}",
    "tumblr": "https://{u}.tumblr.com",
    "lastfm": "https://last.fm/user/{u}",
    "reddit": "https://reddit.com/user/{u}",
    "pinterest": "https://pinterest.com/{u}",
}


class SocialscanScraper(BaseDataSource):
    name = "socialscan"

    async def _run_live(self, username: str) -> list[RawProfile]:
        if not username:
            return []
        try:
            from socialscan.util import execute_queries
        except Exception:
            return []  # socialscan not installed
        try:
            results = await execute_queries([username])
        except Exception:
            return []

        profiles: list[RawProfile] = []
        for r in results:
            # available is False => the handle is taken (account exists);
            # require a conclusive check (valid + success) to avoid false positives.
            if getattr(r, "available", True) is False and getattr(r, "valid", False) \
                    and getattr(r, "success", False):
                platform = r.platform.name.lower()
                url = _URL.get(platform, "").format(u=username)
                profiles.append(make_profile(
                    "social_account", username, platform, url,
                    metadata={"source": "socialscan", "verified_taken": True,
                              "high_confidence": True},
                ))
        return profiles
