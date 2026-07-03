"""
backend/ingestion/url_scraper.py — extracts platform & handle from a social media URL,
emits a derived username seed so downstream scrapers run on the handle.

extract_handle() is also reused by correlation_engine.py's bio_url_match signal (a bio
that links to "instagram.com/johndoe" needs the SAME platform/handle parsing used here
to compare against a discovered Instagram profile's own value).
"""
from __future__ import annotations

import re

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

# Reserved path segments that are NOT user handles (would create bogus cascade
# seeds and false correlations if treated as usernames).
_RESERVED = {
    "p", "i", "explore", "tv", "reel", "reels", "stories", "watch", "channel",
    "c", "results", "home", "about", "sharer", "share", "login", "signup",
    "help", "search", "hashtag", "intent", "messages", "settings", "feed",
}

# (regex, platform). YouTube only matches real handle/user/c forms — not
# /watch or /channel/<id>, which are not usernames.
_PATTERNS = [
    (r"instagram\.com/([^/?#]+)", "instagram"),
    (r"twitter\.com/([^/?#]+)", "twitter"),
    (r"x\.com/([^/?#]+)", "twitter"),
    (r"github\.com/([^/?#]+)", "github"),
    (r"linkedin\.com/in/([^/?#]+)", "linkedin"),
    (r"facebook\.com/([^/?#]+)", "facebook"),
    (r"reddit\.com/user/([^/?#]+)", "reddit"),
    (r"youtube\.com/(?:@|c/|user/)([^/?#]+)", "youtube"),
]

_KNOWN_HOSTS = ("youtube.com", "facebook.com", "instagram.com", "twitter.com",
               "x.com", "github.com", "linkedin.com", "reddit.com")


def extract_handle(url: str) -> tuple[str, str] | None:
    """Best-effort (platform, handle) from a social-profile URL, or None.

    Module-level so both URLScraper and correlation_engine.py's bio_url_match
    signal use the exact same platform/handle parsing — a bio link and a
    discovered profile must be normalised identically to compare equal.
    """
    url = (url or "").strip()
    for regex, plat in _PATTERNS:
        match = re.search(regex, url, re.I)
        if match:
            cand = match.group(1).split("?")[0].split("#")[0]
            if cand and cand.lower() not in _RESERVED:
                return plat, cand
            return None  # known platform, non-profile path (post/video/etc.)
    return None


def _is_known_host(url: str) -> bool:
    u = url.lower()
    return any(host in u for host in _KNOWN_HOSTS)


class URLScraper(BaseDataSource):
    name = "url_scraper"

    async def _run_live(self, url: str) -> list[RawProfile]:
        return self._build(url)

    def _run_mock(self, url: str) -> list[RawProfile]:
        return self._build(url)

    def _build(self, url: str) -> list[RawProfile]:
        url = (url or "").strip()
        result = extract_handle(url)
        handle = result[1] if result else None
        platform = result[0] if result else "unknown"
        matched_known = result is not None or _is_known_host(url)

        if not handle and not matched_known:
            # Unknown but structured URL: take the last path segment as a best-effort handle.
            parts = [p for p in url.split("/") if p]
            if len(parts) >= 2 and parts[-2].lower() not in ("www.google.com", "google.com", "search"):
                cand = parts[-1].split("?")[0].split("#")[0]
                if cand and cand.lower() not in _RESERVED:
                    handle = cand

        if not handle:
            # Record the URL as a web reference if we know the platform, but emit no
            # (garbage) cascade seed.
            if matched_known:
                return [make_profile("url", url, platform, url,
                                     metadata={"platform": platform, "note": "no extractable handle"})]
            return []

        # Return both the URL profile and the derived username profile (triggers cascade).
        return [
            make_profile(
                "url", url, platform, url,
                metadata={"handle": handle, "platform": platform, "note": f"Extracted handle {handle} from URL"}
            ),
            make_profile(
                "username", handle, "derived", "",
                metadata={"derived_from": url, "cascade": True}
            )
        ]
