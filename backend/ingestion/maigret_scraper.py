"""
backend/ingestion/maigret_scraper.py — primary username scraper (Section 5A).

Runs the `maigret` CLI with the two critical flags learned from real output:
  --no-recursion  (don't pull in strangers linked from a bio)
  --timeout 10    (one slow site can't hang the run)

Only "Claimed" accounts are kept.  A username search returns every account sharing
the STRING, not one person — the scoring engine separates same-person from
same-string, so this wrapper returns all claimed accounts honestly.

FALSE-POSITIVE FILTER (control-probe):
  Maigret's per-site detection heuristics have rotted for many sites; running a
  random 20-char nonsense username still returns ~43 "Claimed" hits.  To fix this,
  each run also probes a random control username in parallel.  Any site that claims
  the control string is broken and excluded from the real results.  A 6-hour cache
  (reports/false_positive_sites.json) keeps the extra cost to roughly once per
  demo session.  See fp_filter.py for the full implementation.

PHOTO EXTRACTION NOTE:
  Maigret's --json simple report only populates the per-site `ids` dict where the
  site's definition has explicit field-extraction patterns; most sites in maigret's
  data.json do NOT have bio/avatar extraction configured (confirmed: GitHub and
  Instagram definitions have no such patterns).  Switching to --json ndjson does not
  change this — the populated-fields gap is at the site-definition level, not the
  report format.  Profile photos are therefore obtained via the og:image scraper in
  the orchestrator pipeline rather than from this scraper.

Returns [] if maigret isn't installed or anything fails.
"""
from __future__ import annotations

import asyncio
import json
import os

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool
from backend.ingestion.fp_filter import filter_with_control


class MaigretScraper(BaseDataSource):
    name = "maigret"
    # Set by _run_live after each run; read by orchestrator to log to audit ledger.
    # None means never ran (e.g. mock mode or maigret not installed).
    last_fp_info: dict | None = None

    async def _run_for_username(self, username: str) -> list[RawProfile]:
        """Run maigret for one username and return raw (unfiltered) profiles."""
        exe = resolve_tool("maigret")
        if not exe:
            return []
        outdir = os.path.join(config.REPORT_OUTPUT_DIR, "maigret")
        os.makedirs(outdir, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            exe, username, "--json", "simple", "--no-recursion",
            "--timeout", "10", "--no-progressbar", "--folderoutput", outdir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=200)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        return self._parse(outdir, username)

    async def _run_live(self, username: str) -> list[RawProfile]:
        filtered, fp_info = await filter_with_control(
            "maigret", username, self._run_for_username,
        )
        self.last_fp_info = fp_info
        return filtered

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
                    "name": ids.get("fullname"),
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
