"""
backend/ingestion/holehe_scraper.py — email -> registered services (holehe).

holehe (github.com/megadose/holehe) checks ~120 sites for whether an email is
registered, using each site's password-reset / registration response (it never logs
in and never sees passwords). This replaces the dead Epieos/user-scanner stubs and
answers "which services has this email signed up to?".

Runs the `holehe` CLI with --only-used and parses the `[+] domain` lines. Fail-safe:
returns [] if holehe isn't installed, times out, or errors.
"""
from __future__ import annotations

import asyncio
import re

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool

# `[+] some.domain.tld` — the legend line "[+] Email used, ..." has no domain token,
# so it won't match.
_USED_RE = re.compile(r"\[\+\]\s+([a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})")


class HoleheScraper(BaseDataSource):
    name = "holehe"

    async def _run_live(self, email: str) -> list[RawProfile]:
        if "@" not in (email or ""):
            return []
        exe = resolve_tool("holehe")
        if not exe:
            return []  # holehe not installed
        proc = await asyncio.create_subprocess_exec(
            exe, email, "--only-used", "--no-color",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return []

        text = out.decode(errors="ignore")
        seen: set[str] = set()
        profiles: list[RawProfile] = []
        for domain in _USED_RE.findall(text):
            d = domain.lower()
            if d in seen:
                continue
            seen.add(d)
            profiles.append(make_profile(
                "email_registration", email, d, f"https://{d}",
                metadata={"registered": True, "service": d, "source": "holehe"},
            ))
        return profiles
