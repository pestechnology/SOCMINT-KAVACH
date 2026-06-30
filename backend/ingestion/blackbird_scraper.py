"""
backend/ingestion/blackbird_scraper.py — Blackbird username + email enumeration.

Runs the `blackbird` CLI in two modes:
  - username mode: blackbird --username {u} --json
  - email mode:    blackbird --email {e} --json

Only "FOUND" accounts are kept. Returns [] if blackbird isn't installed.
Fail-safe: never raises.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool


class BlackbirdUsernameScraper(BaseDataSource):
    name = "blackbird"

    async def _run_live(self, username: str) -> list[RawProfile]:
        return await _run_blackbird("--username", username)


class BlackbirdEmailScraper(BaseDataSource):
    name = "blackbird_email"

    async def _run_live(self, email: str) -> list[RawProfile]:
        return await _run_blackbird("--email", email)


async def _run_blackbird(flag: str, value: str) -> list[RawProfile]:
    """Run blackbird CLI and parse JSON results."""
    exe = resolve_tool("blackbird")
    if not exe:
        return []  # blackbird not installed
    outdir = os.path.join(config.REPORT_OUTPUT_DIR, "blackbird")
    os.makedirs(outdir, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        exe, flag, value, "--json",
        "--no-nsfw",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=outdir,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return []

    # blackbird outputs JSON to stdout
    text = stdout.decode(errors="ignore").strip()
    profiles: list[RawProfile] = []

    # Try to parse the JSON output
    try:
        # blackbird may output a JSON array of results
        data = json.loads(text) if text.startswith("[") else []
    except Exception:
        # fallback: look for JSON files in the output directory
        data = []
        for f in os.listdir(outdir):
            if f.endswith(".json") and value.lower() in f.lower():
                try:
                    with open(os.path.join(outdir, f)) as fh:
                        data = json.load(fh)
                    break
                except Exception:
                    pass

    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            status = (entry.get("status") or "").lower()
            if status not in ("found", "claimed"):
                continue
            site = entry.get("site") or entry.get("app") or "unknown"
            url = entry.get("url") or ""
            profiles.append(make_profile(
                "social_account", value, site.lower(), url,
                metadata={
                    "source": "blackbird",
                    "status": status,
                    "response_time": entry.get("response_time"),
                },
            ))

    return profiles
