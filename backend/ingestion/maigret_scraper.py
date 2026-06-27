"""
backend/ingestion/maigret_scraper.py — primary username scraper (Section 5A).

Runs the `maigret` CLI with the two critical flags learned from real output:
  --no-recursion  (don't pull in strangers linked from a bio)
  --timeout 10    (one slow site can't hang the run)

Only "Claimed" accounts are kept. A username search returns every account sharing
the STRING, not one person — the scoring engine separates same-person from
same-string, so this wrapper returns all claimed accounts honestly.

Returns [] if maigret isn't installed or anything fails.
"""
from __future__ import annotations

import asyncio
import json
import os

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class MaigretScraper(BaseDataSource):
    name = "maigret"

    async def _run_live(self, username: str) -> list[RawProfile]:
        outdir = os.path.join(config.REPORT_OUTPUT_DIR, "maigret")
        os.makedirs(outdir, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "maigret", username, "--json", "simple", "--no-recursion",
            "--timeout", "10", "--no-progressbar", "--folderoutput", outdir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=200)
        except asyncio.TimeoutError:
            proc.kill()
            return self._parse(outdir, username)  # parse whatever was written
        return self._parse(outdir, username)

    def _parse(self, outdir: str, username: str) -> list[RawProfile]:
        path = os.path.join(outdir, f"report_{username}_simple.json")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        profiles: list[RawProfile] = []
        for platform_name, entry in data.items():
            status = entry.get("status", {})
            if status.get("status") != "Claimed":
                continue
            ids = status.get("ids", {}) or {}
            profiles.append(make_profile(
                "social_account", ids.get("username", username),
                platform_name.lower(), status.get("url", ""),
                metadata={
                    "fullname": ids.get("fullname"),
                    "bio": ids.get("bio"),
                    "photo_url": ids.get("image"),
                    "follower_count": ids.get("follower_count"),
                    "created_at": ids.get("created_at"),
                    "location": ids.get("location"),
                    "tags": status.get("tags", []),
                    "all_ids": ids,
                },
            ))
        return profiles
