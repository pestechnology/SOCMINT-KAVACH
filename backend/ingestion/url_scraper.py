"""
backend/ingestion/url_scraper.py — extracts platform & handle from a social media URL,
emits a derived username seed so downstream scrapers run on the handle.
"""
from __future__ import annotations

import re

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class URLScraper(BaseDataSource):
    name = "url_scraper"

    async def _run_live(self, url: str) -> list[RawProfile]:
        return self._build(url)

    def _run_mock(self, url: str) -> list[RawProfile]:
        return self._build(url)

    # Reserved path segments that are NOT user handles (would create bogus cascade
    # seeds and false correlations if treated as usernames).
    _RESERVED = {
        "p", "i", "explore", "tv", "reel", "reels", "stories", "watch", "channel",
        "c", "results", "home", "about", "sharer", "share", "login", "signup",
        "help", "search", "hashtag", "intent", "messages", "settings", "feed",
    }

    def _build(self, url: str) -> list[RawProfile]:
        url = (url or "").strip()
        # (regex, platform). YouTube only matches real handle/user/c forms — not
        # /watch or /channel/<id>, which are not usernames.
        patterns = [
            (r"instagram\.com/([^/?#]+)", "instagram"),
            (r"twitter\.com/([^/?#]+)", "twitter"),
            (r"x\.com/([^/?#]+)", "twitter"),
            (r"github\.com/([^/?#]+)", "github"),
            (r"linkedin\.com/in/([^/?#]+)", "linkedin"),
            (r"facebook\.com/([^/?#]+)", "facebook"),
            (r"reddit\.com/user/([^/?#]+)", "reddit"),
            (r"youtube\.com/(?:@|c/|user/)([^/?#]+)", "youtube"),
        ]
        handle = None
        platform = "unknown"
        matched_known = False  # URL host is a recognised social platform
        for regex, plat in patterns:
            match = re.search(regex, url, re.I)
            if match:
                matched_known = True
                platform = plat
                cand = match.group(1).split("?")[0].split("#")[0]
                if cand and cand.lower() not in self._RESERVED:
                    handle = cand
                break  # this platform's host matched; don't try the others

        # A known platform host but a non-profile path (e.g. instagram.com/p/<id>,
        # youtube.com/watch?v=...). Detect it so the fallback below doesn't grab the
        # post/video id as a bogus handle.
        if not matched_known:
            for host in ("youtube.com", "facebook.com", "instagram.com", "twitter.com",
                         "x.com", "github.com", "linkedin.com", "reddit.com"):
                if host in url.lower():
                    matched_known = True
                    break

        if not handle and not matched_known:
            # Unknown but structured URL: take the last path segment as a best-effort handle.
            parts = [p for p in url.split("/") if p]
            if len(parts) >= 2 and parts[-2].lower() not in ("www.google.com", "google.com", "search"):
                cand = parts[-1].split("?")[0].split("#")[0]
                if cand and cand.lower() not in self._RESERVED:
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
