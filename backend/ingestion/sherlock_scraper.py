"""
backend/ingestion/sherlock_scraper.py — username -> accounts (Sherlock).

Sherlock (sherlock-project) is a second, independent username enumerator alongside
Maigret.  Running two enumerators gives corroboration: a site found by BOTH is a
stronger signal than one found by a single tool.  Sherlock only reports accounts it
finds (`--print-found`).

FALSE-POSITIVE FILTER: same control-probe strategy as maigret_scraper.py.
Runs a random control username in parallel; any site that fires for the control
is excluded from the real results.  See fp_filter.py.

Parses `[+] Site: url` lines.  Fail-safe: [] if sherlock isn't installed/errors.
"""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import urlparse

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool
from backend.ingestion.fp_filter import filter_with_control

_FOUND_RE = re.compile(r"^\[\+\]\s+(.+?):\s+(https?://\S+)\s*$", re.MULTILINE)


def _platform_from(site: str, url: str) -> str:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    base = host.split(".")[0] if host else ""
    return base or re.sub(r"[^a-z0-9]+", "", site.lower())


class SherlockScraper(BaseDataSource):
    name = "sherlock"
    # Set by _run_live after each run; read by orchestrator to log to audit ledger.
    last_fp_info: dict | None = None

    async def _run_for_username(self, username: str) -> list[RawProfile]:
        """Run sherlock for one username and return raw (unfiltered) profiles."""
        if not username:
            return []
        exe = resolve_tool("sherlock")
        if not exe:
            return []
        # Sherlock always writes a `<username>.txt` dump to its CWD regardless of
        # --print-found; without an explicit cwd that lands in the repo root (or
        # wherever uvicorn happened to be launched from). Give it its own scratch
        # folder under REPORT_OUTPUT_DIR (same pattern as maigret's --folderoutput).
        outdir = os.path.join(config.REPORT_OUTPUT_DIR, "sherlock")
        os.makedirs(outdir, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            exe, username, "--print-found", "--no-color", "--timeout", "5",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=outdir,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return []

        text = out.decode(errors="ignore")
        seen: set[str] = set()
        profiles: list[RawProfile] = []
        for site, url in _FOUND_RE.findall(text):
            platform = _platform_from(site, url)
            key = (platform, url.lower())
            if key in seen:
                continue
            seen.add(key)
            profiles.append(make_profile(
                "social_account", username, platform, url,
                metadata={"site_name": site.strip(), "source": "sherlock"},
            ))
        return profiles

    async def _run_live(self, username: str) -> list[RawProfile]:
        filtered, fp_info = await filter_with_control(
            "sherlock", username, self._run_for_username,
        )
        self.last_fp_info = fp_info
        return filtered
