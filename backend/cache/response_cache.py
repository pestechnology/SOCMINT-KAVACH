"""Persistent SQLite response caching for scrapers."""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)


class ScraperCache:
    """SQLite caching layer for scraper outputs with TTL expiration."""

    def __init__(
        self,
        db_path: str | Path = "vertex.db",
        ttl_hours: int = 24,
    ) -> None:
        self.db_path = str(db_path)
        self.ttl_hours = ttl_hours
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Return a SQLite connection configured with Row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_table(self) -> None:
        """Create scraper_cache table if it does not exist."""
        try:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scraper_cache (
                        cache_key TEXT PRIMARY KEY,
                        scraper_name TEXT,
                        query TEXT,
                        response_json TEXT,
                        cached_at TEXT
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error("Failed to ensure scraper_cache table: %s", e)

    @staticmethod
    def _make_key(scraper_name: str, query: str) -> str:
        """Compute SHA-256 cache key from scraper_name:query."""
        raw = f"{scraper_name}:{query}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, scraper_name: str, query: str) -> list[dict[str, Any]] | None:
        """Retrieve unexpired cached profiles for a query.

        Returns None if cache miss, expired, or CACHE_ENABLED is False.
        """
        if not getattr(settings, "CACHE_ENABLED", True):
            logger.debug("[cache] skipping read (CACHE_ENABLED=False)")
            return None

        cache_key = self._make_key(scraper_name, query)
        try:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT response_json, cached_at FROM scraper_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
            finally:
                conn.close()

            if not row:
                return None

            cached_at_str = row["cached_at"].replace("Z", "+00:00")
            cached_dt = datetime.fromisoformat(cached_at_str)
            now = datetime.now(timezone.utc)
            elapsed_seconds = (now - cached_dt).total_seconds()

            if elapsed_seconds <= self.ttl_hours * 3600:
                logger.info("[cache] HIT for %s:'%s'", scraper_name, query)
                result: list[dict[str, Any]] = json.loads(row["response_json"])
                return result

            logger.info("[cache] EXPIRED for %s:'%s'", scraper_name, query)
            return None

        except Exception as e:
            logger.warning("[cache] get error for %s:'%s': %s", scraper_name, query, e)
            return None

    def set(
        self,
        scraper_name: str,
        query: str,
        profiles_as_dicts: list[dict[str, Any]],
    ) -> None:
        """Store profiles as JSON in SQLite cache under SHA-256 key."""
        cache_key = self._make_key(scraper_name, query)
        now_str = datetime.now(timezone.utc).isoformat()
        response_json = json.dumps(profiles_as_dicts, ensure_ascii=False)

        try:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scraper_cache
                    (cache_key, scraper_name, query, response_json, cached_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cache_key, scraper_name, query, response_json, now_str),
                )
                conn.commit()
                logger.info("[cache] stored %d profile(s) for %s:'%s'", len(profiles_as_dicts), scraper_name, query)
            finally:
                conn.close()
        except Exception as e:
            logger.error("[cache] set error for %s:'%s': %s", scraper_name, query, e)
