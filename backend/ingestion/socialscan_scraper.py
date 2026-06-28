"""
backend/ingestion/socialscan_scraper.py — high-confidence username availability check.

socialscan checks 11 major platforms (Instagram, Twitter, GitHub, Tumblr, etc.)
with high accuracy by mimicking real registration flows. Unlike maigret which
checks 300+ sites but gets false positives, socialscan's results are highly
reliable for the platforms it covers.

Returns one RawProfile per platform where the username IS TAKEN (exists).
Returns [] if socialscan isn't installed or anything fails.
"""
from __future__ import annotations

import asyncio
import json

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class SocialscanScraper(BaseDataSource):
    name = "socialscan"

    async def _run_live(self, username: str) -> list[RawProfile]:
        proc = await asyncio.create_subprocess_exec(
            "socialscan", username, "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            return []

        text = stdout.decode(errors="ignore").strip()
        profiles: list[RawProfile] = []

        # socialscan JSON output is an array of objects
        try:
            # The output may have non-JSON lines before the actual JSON
            start = text.find("[")
            if start < 0:
                return []
            data = json.loads(text[start:])
        except Exception:
            return []

        for entry in data:
            if not isinstance(entry, dict):
                continue
            # socialscan reports "available" (username free) or "taken" (exists)
            if not entry.get("taken", False):
                continue
            platform = (entry.get("platform") or entry.get("site") or "unknown").lower()
            url = entry.get("url") or ""
            profiles.append(make_profile(
                "social_account", username, platform, url,
                metadata={
                    "source": "socialscan",
                    "verified_taken": True,
                    "high_confidence": True,
                },
            ))

        return profiles
