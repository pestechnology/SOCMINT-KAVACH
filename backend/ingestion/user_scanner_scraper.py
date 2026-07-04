"""
backend/ingestion/user_scanner_scraper.py — Email footprinting wrapper.

Uses `user-scanner` (a holehe alternative) to check email registrations.
Fail-safe: returns [] if the binary is missing or fails.
"""
from __future__ import annotations

import asyncio
import json

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class UserScannerScraper(BaseDataSource):
    name = "user_scanner"

    async def _run_live(self, email: str) -> list[RawProfile]:
        try:
            # Assumes user-scanner outputs JSON with --json flag
            proc = await asyncio.create_subprocess_exec(
                "user-scanner", "--email", email, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            
            if proc.returncode != 0 and not out.strip():
                return []
                
            text = out.decode("utf-8", errors="ignore")
            # Parse the JSON output (fallback to plain text parsing if not JSON)
            profiles = []
            
            try:
                # Assuming JSON format is a list of results or a dict with platforms
                data = json.loads(text)
                if isinstance(data, list):
                    for item in data:
                        if item.get("exists") or item.get("registered"):
                            plat = item.get("site") or item.get("platform", "unknown")
                            profiles.append(make_profile(
                                "email_registration", email, plat, "",
                                metadata={"registered": True, "source": "user-scanner"}
                            ))
                elif isinstance(data, dict):
                    # dict of platform -> True/False
                    for plat, exists in data.items():
                        if exists is True:
                            profiles.append(make_profile(
                                "email_registration", email, plat, "",
                                metadata={"registered": True, "source": "user-scanner"}
                            ))
            except json.JSONDecodeError:
                # Fallback to regex parsing if user-scanner doesn't support --json perfectly
                for line in text.splitlines():
                    # Look for [✓], [+], or 'found' style indicators
                    if "[+]" in line or "[✓]" in line or "Found on" in line:
                        plat = line.split("]")[-1].strip().split()[0].lower()
                        if plat:
                            profiles.append(make_profile(
                                "email_registration", email, plat, "",
                                metadata={"registered": True, "source": "user-scanner", "raw_line": line}
                            ))
                            
            return profiles
        except (FileNotFoundError, asyncio.TimeoutError, Exception):
            # Tool not installed, timeout, or other error
            return []
