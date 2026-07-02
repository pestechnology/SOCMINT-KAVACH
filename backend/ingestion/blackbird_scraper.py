"""
backend/ingestion/blackbird_scraper.py — Blackbird username + email enumeration.

Blackbird (github.com/p1ngul1n0/blackbird) is a WhatsMyName-based OSINT tool.
It is NOT pip-installable — it must be cloned and its path configured via
BLACKBIRD_PATH in .env.  A thin wrapper (venv/Scripts/blackbird.bat) makes
resolve_tool("blackbird") find it.

Invocation:
  username:  blackbird -u {username} --json --no-nsfw --no-update --timeout 15
  email:     blackbird -e {email}    --json --no-nsfw --no-update --timeout 15

The `--json` flag writes a file to {BLACKBIRD_PATH}/results/{id}_{date}_blackbird/
{id}_{date}_blackbird.json — NOT to stdout (verified from source:
src/modules/export/json.py + src/modules/export/file_operations.py).

Output JSON shape (verified from src/modules/core/username.py::checkSite):
  [{"name": "SiteName", "url": "https://...", "category": "social",
    "status": "FOUND", "metadata": [...] | null}, ...]
Note: the status field is "FOUND" (not "Claimed" or "Found") — this differs from
the old incorrect assumption that used "site"/"app" keys.

FALSE-POSITIVE FILTER: same control-probe strategy as maigret/sherlock.
Runs a random control username in parallel; any site that fires for the control
is excluded from the real results.  See fp_filter.py.

Windows notes:
  • Blackbird prints a rich ASCII-art banner on startup that contains box-drawing
    characters outside cp1252.  Setting PYTHONIOENCODING=utf-8 in the subprocess
    environment prevents the UnicodeEncodeError crash.
  • resolve_tool() returns a .bat path on Windows; asyncio.create_subprocess_exec
    cannot run .bat files directly (CreateProcess needs a real exe).  We detect
    this and route through cmd.exe /c.

Returns [] if BLACKBIRD_PATH is not set or blackbird isn't found.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
from datetime import datetime

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile, resolve_tool
from backend.ingestion.fp_filter import filter_with_control


def _blackbird_repo() -> str | None:
    """Return the Blackbird repo root from BLACKBIRD_PATH env var, or None."""
    return os.environ.get("BLACKBIRD_PATH") or getattr(config, "BLACKBIRD_PATH", None)


def _build_cmd(exe: str, *args: str) -> list[str]:
    """Wrap .bat/.cmd executables with cmd /c on Windows so CreateProcess works."""
    if os.name == "nt" and exe.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]


class BlackbirdUsernameScraper(BaseDataSource):
    name = "blackbird"
    last_fp_info: dict | None = None

    async def _run_for_username(self, username: str) -> list[RawProfile]:
        return await _run_blackbird("-u", username)

    async def _run_live(self, username: str) -> list[RawProfile]:
        filtered, fp_info = await filter_with_control(
            "blackbird", username, self._run_for_username,
        )
        self.last_fp_info = fp_info
        return filtered


class BlackbirdEmailScraper(BaseDataSource):
    name = "blackbird_email"

    async def _run_live(self, email: str) -> list[RawProfile]:
        # Email mode: no FP filter (no meaningful "control email" pattern exists)
        return await _run_blackbird("-e", email)


async def _run_blackbird(flag: str, value: str) -> list[RawProfile]:
    """Run blackbird CLI and parse the JSON file it writes."""
    exe = resolve_tool("blackbird")
    if not exe:
        return []
    repo = _blackbird_repo()
    if not repo:
        return []

    # PYTHONIOENCODING=utf-8 prevents the rich/cp1252 UnicodeEncodeError on Windows
    # when blackbird prints its ASCII-art banner to a redirected stdout.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    cmd = _build_cmd(
        exe, flag, value,
        "--json", "--no-nsfw", "--no-update", "--timeout", "15",
    )
    # Run with cwd=repo so blackbird creates its logs/ dir there (not in VERTEX root)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo,
        env=env,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return []

    # Blackbird writes: {repo}/results/{value}_{date}_blackbird/{value}_{date}_blackbird.json
    date_str = datetime.now().strftime("%m_%d_%Y")
    safe_value = value.replace("@", "_").replace(".", "_")  # email safe name
    # Try today's date first; fall back to any matching JSON in results/
    json_path = os.path.join(
        repo, "results",
        f"{safe_value}_{date_str}_blackbird",
        f"{safe_value}_{date_str}_blackbird.json",
    )
    if not os.path.exists(json_path):
        # Glob fallback (handles edge cases like midnight date roll-over)
        pattern = os.path.join(repo, "results", f"{safe_value}_*_blackbird", "*.json")
        matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if not matches:
            return []
        json_path = matches[0]

    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []

    profiles: list[RawProfile] = []
    if not isinstance(data, list):
        return profiles

    for entry in data:
        if not isinstance(entry, dict):
            continue
        # Blackbird status values: "FOUND", "NOT-FOUND", "ERROR", "NONE"
        if entry.get("status") != "FOUND":
            continue
        # Field is "name" (site name), not "site" or "app"
        site = entry.get("name") or "unknown"
        url = entry.get("url") or ""
        metadata_raw = entry.get("metadata") or []
        # Flatten blackbird metadata list [{name, value}] into a simple dict
        meta_flat = {m["name"]: m["value"] for m in metadata_raw
                     if isinstance(m, dict) and "name" in m and "value" in m}
        profiles.append(make_profile(
            "social_account", value, site.lower(), url,
            metadata={
                "source": "blackbird",
                "category": entry.get("category"),
                **meta_flat,
            },
        ))

    return profiles
