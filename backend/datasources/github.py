"""Live GitHub API data source."""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.cache.response_cache import ScraperCache
from backend.config import settings
from backend.datasources._helpers import fetch_and_phash_photos
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class GitHubScraper(BaseDataSource):
    """Scraper querying GitHub REST API v3 for username profiles."""

    source_tool = SourceTool.GITHUB

    @property
    def name(self) -> str:
        return "github"

    def supports(self, identifier_type: IdentifierType) -> bool:
        return identifier_type == IdentifierType.USERNAME

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        username = identifier.value
        cache = ScraperCache(str(settings.DB_PATH), settings.CACHE_TTL_HOURS)

        # 1. Check cache
        if settings.CACHE_ENABLED:
            cached = cache.get("github", username)
            if cached is not None:
                logger.info("[%s] returning %d profile(s) from cache for '%s'", self.name, len(cached), username)
                return [RawProfile(**p) for p in cached]

        # 2. Read GITHUB_TOKEN
        token = settings.GITHUB_TOKEN.strip() or os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            logger.warning("[%s] GITHUB_TOKEN missing or empty in environment. Returning empty list.", self.name)
            return []

        url = f"https://api.github.com/users/{username}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15.0)

            if resp.status_code == 404:
                logger.info("[%s] user '%s' not found (404).", self.name, username)
                return []
            elif resp.status_code == 401:
                logger.warning("[%s] GitHub token invalid (401).", self.name)
                return []
            elif resp.status_code == 403:
                reset_time = resp.headers.get("x-ratelimit-reset", "unknown")
                logger.warning("[%s] GitHub API rate limited (403). Reset at: %s", self.name, reset_time)
                return []

            resp.raise_for_status()
            data = resp.json()

        except Exception as e:
            logger.warning("[%s] HTTP request failed for '%s': %s", self.name, username, e)
            return []

        now_iso = datetime.now(timezone.utc).isoformat()
        sha256_hash = hashlib.sha256(f"{data['login']}github{data['html_url']}".encode("utf-8")).hexdigest()

        metadata: dict[str, Any] = {
            "fullname": data.get("name") or "",
            "bio": data.get("bio") or "",
            "photo_url": data.get("avatar_url") or "",
            "location": data.get("location") or "",
            "company": data.get("company") or "",
            "blog": data.get("blog") or "",
            "twitter_username": data.get("twitter_username") or "",
            "public_repos": data.get("public_repos") or 0,
            "followers": data.get("followers") or 0,
            "following": data.get("following") or 0,
            "created_at": data.get("created_at") or "",
            "site_name": "GitHub",
            "source_tool": "github",
            "source_query": username,
        }

        # Extract email if present
        email = data.get("email")
        if email and isinstance(email, str) and email.strip():
            metadata["emails_found"] = [email.strip()]

        profile = RawProfile(
            type="social_account",
            value=data["login"],
            platform="github",
            source_url=data["html_url"],
            data_mode="live",
            metadata=metadata,
            collected_at=now_iso,
            sha256=sha256_hash,
        )

        profiles = [profile]
        await fetch_and_phash_photos(profiles, logger)

        if settings.CACHE_ENABLED:
            try:
                cache.set("github", username, [asdict(p) for p in profiles])
            except Exception as e:
                logger.warning("[%s] failed to cache result: %s", self.name, e)

        return profiles
