"""Live Holehe CLI data source for email registration checks."""

import asyncio
import hashlib
import logging
import re
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from backend.cache.response_cache import ScraperCache
from backend.config import settings
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class HoleheScraper(BaseDataSource):
    """Concrete scraper running real holehe CLI via async subprocess."""

    source_tool = SourceTool.HOLEHE

    def __init__(self) -> None:
        self.cli_path = shutil.which("holehe")
        if not self.cli_path:
            logger.error("[holehe] CLI tool 'holehe' not found on PATH. Scraper will return empty results.")

    @property
    def name(self) -> str:
        return "holehe"

    def supports(self, identifier_type: IdentifierType) -> bool:
        return identifier_type == IdentifierType.EMAIL

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        email = identifier.value
        cache = ScraperCache(str(settings.DB_PATH), settings.CACHE_TTL_HOURS)

        # 1. Cache check
        if settings.CACHE_ENABLED:
            cached = cache.get("holehe", email)
            if cached is not None:
                logger.info("[%s] returning %d profile(s) from cache for '%s'", self.name, len(cached), email)
                return [RawProfile(**p) for p in cached]

        # 2. Check CLI
        if not self.cli_path:
            logger.error("[%s] holehe CLI not installed.", self.name)
            return []

        # 3. Subprocess
        cmd = [self.cli_path, "--no-color", "--only-used", email]
        logger.debug("[%s] launching subprocess: %s", self.name, " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=90.0
            )

            if proc.returncode != 0:
                logger.warning(
                    "[%s] holehe exited with code %d. Stderr: %s",
                    self.name,
                    proc.returncode,
                    stderr_bytes.decode("utf-8", errors="replace"),
                )
                return []

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            logger.warning("[%s] timed out after 90.0s for '%s'", self.name, email)
            return []
        except Exception as e:
            logger.warning("[%s] subprocess execution failed: %s", self.name, e)
            return []

        # 4. Parse stdout
        matches = re.findall(r"\[\+\]\s+(\S+)", stdout_str)
        now_iso = datetime.now(timezone.utc).isoformat()
        profiles: list[RawProfile] = []

        for domain in sorted(set(matches)):
            clean_domain = domain.strip().lower()
            platform = clean_domain.split(".")[0]  # e.g., instagram.com -> instagram
            source_url = f"https://{clean_domain}"
            sha256_hash = hashlib.sha256(f"{email}{platform}{source_url}".encode("utf-8")).hexdigest()

            metadata: dict[str, Any] = {
                "fullname": "",
                "bio": "",
                "photo_url": "",
                "site_name": clean_domain,
                "source_tool": "holehe",
                "source_query": email,
                "registered": True,
                "emails_found": [email],
            }

            profile = RawProfile(
                type="email_registration",
                value=email,
                platform=platform,
                source_url=source_url,
                data_mode="live",
                metadata=metadata,
                collected_at=now_iso,
                sha256=sha256_hash,
            )
            profiles.append(profile)

        logger.info("[%s] successfully resolved '%s' → %d registered site(s)", self.name, email, len(profiles))

        if settings.CACHE_ENABLED:
            try:
                cache.set("holehe", email, [asdict(p) for p in profiles])
            except Exception as e:
                logger.warning("[%s] failed to store in cache: %s", self.name, e)

        return profiles
