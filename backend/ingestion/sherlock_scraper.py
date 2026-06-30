"""
backend/ingestion/sherlock_scraper.py — username -> accounts (Sherlock).

Sherlock (sherlock-project) is a second, independent username enumerator alongside
Maigret. Running two enumerators gives corroboration: a site found by BOTH is a
stronger signal than one found by a single tool. Sherlock only reports accounts it
finds (`--print-found`).

Parses `[+] Site: url` lines. Fail-safe: [] if sherlock isn't installed/errors/times out.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool

_FOUND_RE = re.compile(r"^\[\+\]\s+(.+?):\s+(https?://\S+)\s*$", re.MULTILINE)


def _platform_from(site: str, url: str) -> str:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    base = host.split(".")[0] if host else ""
    return base or re.sub(r"[^a-z0-9]+", "", site.lower())


class SherlockScraper(BaseDataSource):
    name = "sherlock"

    async def _run_live(self, username: str) -> list[RawProfile]:
        if not username:
            return []
        exe = resolve_tool("sherlock")
        if not exe:
            return []  # sherlock not installed
        proc = await asyncio.create_subprocess_exec(
            exe, username, "--print-found", "--no-color", "--timeout", "5",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
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
