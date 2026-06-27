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

    def _build(self, url: str) -> list[RawProfile]:
        url = (url or "").strip()
        # Patterns to match handle (group 1) and platform
        patterns = [
            (r"instagram\.com/([^/?#]+)", "instagram"),
            (r"twitter\.com/([^/?#]+)", "twitter"),
            (r"x\.com/([^/?#]+)", "twitter"),
            (r"github\.com/([^/?#]+)", "github"),
            (r"linkedin\.com/in/([^/?#]+)", "linkedin"),
            (r"facebook\.com/([^/?#]+)", "facebook"),
            (r"reddit\.com/user/([^/?#]+)", "reddit"),
            (r"youtube\.com/@?([^/?#]+)", "youtube"),
        ]
        handle = None
        platform = "unknown"
        for regex, plat in patterns:
            match = re.search(regex, url, re.I)
            if match:
                handle = match.group(1)
                platform = plat
                break

        if not handle:
            # Fallback: take last non-empty path segment if URL looks structured
            parts = [p for p in url.split("/") if p]
            if len(parts) >= 2 and parts[-2].lower() not in ("www.google.com", "google.com", "search"):
                handle = parts[-1]

        if not handle:
            return []

        # Return both the URL profile itself and the derived username profile to trigger cascade.
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
