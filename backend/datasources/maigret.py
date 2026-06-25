"""Live Maigret OSINT scraper — searches 500+ sites for usernames."""

import asyncio
import hashlib
import io
import json
import logging
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import imagehash
from PIL import Image

from backend.cache.response_cache import ScraperCache
from backend.config import settings
from backend.datasources._helpers import fetch_and_phash_photos
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class MaigretScraper(BaseDataSource):
    """Concrete scraper running real Maigret CLI via async subprocess."""

    source_tool = SourceTool.MAIGRET

    def __init__(self) -> None:
        self.cli_path = shutil.which("maigret")
        if not self.cli_path:
            logger.error("[maigret] CLI tool 'maigret' not found on PATH. Scraper will return empty results.")

    @property
    def name(self) -> str:
        return "maigret"

    def supports(self, identifier_type: IdentifierType) -> bool:
        """True only for username identifiers."""
        return identifier_type == IdentifierType.USERNAME

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        """Scrape live OSINT sources for username using Maigret CLI."""
        if identifier.type != IdentifierType.USERNAME:
            return []

        username = identifier.value.strip()
        if not username:
            return []

        # ── a. Check cache first ─────────────────────────────────────
        cache = ScraperCache(
            db_path=getattr(settings, "DB_PATH", Path("vertex.db")),
            ttl_hours=getattr(settings, "CACHE_TTL_HOURS", 24),
        )
        cached_dicts = cache.get(self.name, username)
        if cached_dicts is not None:
            logger.info("[%s] returning %d profile(s) from cache for '%s'", self.name, len(cached_dicts), username)
            try:
                profiles = []
                for d in cached_dicts:
                    d["data_mode"] = "live"
                    profiles.append(RawProfile(**d))
                return profiles
            except Exception as e:
                logger.warning("[%s] failed to deserialize cached profiles: %s", self.name, e)

        if not self.cli_path:
            logger.warning("[%s] cannot resolve '%s': maigret CLI not installed", self.name, username)
            return []

        # ── b & c. Run async subprocess ──────────────────────────────
        output_dir = Path("/tmp/vertex_maigret")
        output_dir.mkdir(parents=True, exist_ok=True)

        args = [
            self.cli_path,
            username,
            "--json",
            "simple",
            "--no-progressbar",
            "--timeout",
            "20",
            "--top-sites",
            "100",
            "--no-recursion",
            "--folderoutput",
            str(output_dir),
        ]

        logger.info("[%s] launching subprocess for '%s'", self.name, username)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # ── d. Hard timeout 120s ─────────────────────────────────
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace") if stderr else ""
                logger.warning("[%s] subprocess exited with code %d: %s", self.name, proc.returncode, err_text)
                # Maigret sometimes returns non-zero even if it wrote reports on partial errors,
                # so we don't return immediately; we check if the file exists.
        except asyncio.TimeoutError:
            logger.warning("[%s] subprocess timed out (>120s) for '%s'", self.name, username)
            try:
                proc.kill()
            except Exception:
                pass
            return []
        except Exception as e:
            logger.warning("[%s] subprocess execution failed for '%s': %s", self.name, username, e)
            return []

        # ── e. Locate report file ────────────────────────────────────
        report_file1 = output_dir / f"report_{username}_simple.json"
        report_file2 = output_dir / f"{username}_simple.json"

        report_file = None
        if report_file1.exists():
            report_file = report_file1
        elif report_file2.exists():
            report_file = report_file2
        else:
            matches = list(output_dir.glob(f"*{username}*_simple.json"))
            if matches:
                report_file = matches[0]

        if not report_file:
            logger.warning("[%s] no report JSON file found in %s for '%s'", self.name, output_dir, username)
            return []

        # ── f. Parse JSON output ─────────────────────────────────────
        try:
            raw_content = report_file.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw_content)
        except Exception as e:
            logger.warning("[%s] failed to read/parse report JSON %s: %s", self.name, report_file, e)
            return []

        now_iso = datetime.now(timezone.utc).isoformat()
        profiles: list[RawProfile] = []

        for site_name, site_data in data.items():
            if not isinstance(site_data, dict):
                continue

            status_obj = site_data.get("status", {})
            if isinstance(status_obj, dict):
                status_val = status_obj.get("status")
                ids = status_obj.get("ids") or {}
            elif isinstance(status_obj, str):
                status_val = status_obj
                ids = site_data.get("ids") or {}
            else:
                continue

            if status_val != "Claimed":
                continue

            profile_url = str(site_data.get("url_user") or (status_obj.get("url_user") if isinstance(status_obj, dict) else "") or "")
            if not profile_url:
                continue

            display_name = str(ids.get("fullname") or ids.get("name") or "")
            bio = str(ids.get("bio") or ids.get("description") or "")
            photo_url = str(ids.get("image") or ids.get("avatar") or "")

            raw_followers = ids.get("followers") if "followers" in ids else ids.get("subscribers")
            follower_count: int | None = None
            if raw_followers is not None:
                try:
                    if isinstance(raw_followers, int):
                        follower_count = raw_followers
                    elif isinstance(raw_followers, float):
                        follower_count = int(raw_followers)
                    elif isinstance(raw_followers, str):
                        s = raw_followers.strip().upper()
                        if s.endswith("M"):
                            follower_count = int(float(s[:-1]) * 1_000_000)
                        elif s.endswith("K"):
                            follower_count = int(float(s[:-1]) * 1_000)
                        else:
                            follower_count = int(float(s))
                except Exception:
                    follower_count = None

            platform = str(site_name).lower().strip()
            handle = username
            sha256_hash = hashlib.sha256(f"{handle}{platform}{profile_url}".encode("utf-8")).hexdigest()

            profile = RawProfile(
                type="social_account",
                value=handle,
                platform=platform,
                source_url=profile_url,
                data_mode="live",
                metadata={
                    "fullname": display_name,
                    "bio": bio,
                    "photo_url": photo_url,
                    "follower_count": follower_count,
                    "site_name": site_name,
                    "source_tool": self.source_tool.value,
                    "source_query": handle,
                },
                collected_at=now_iso,
                sha256=sha256_hash,
            )
            profiles.append(profile)

        logger.info("[%s] successfully resolved '%s' → %d live profile(s)", self.name, username, len(profiles))

        # ── Fetch and compute photo pHash in parallel ────────────────
        await fetch_and_phash_photos(profiles, logger)

        # ── g. Store results in cache ────────────────────────────────
        try:
            cache.set(self.name, username, [asdict(p) for p in profiles])
        except Exception as e:
            logger.warning("[%s] failed to store results in cache: %s", self.name, e)

        return profiles
