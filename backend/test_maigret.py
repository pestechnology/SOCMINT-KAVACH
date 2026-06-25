"""Standalone test for MaigretScraper and response caching."""

import asyncio
import logging
import time
from pathlib import Path

from backend.config import settings
from backend.database.db import init_db
from backend.datasources.maigret import MaigretScraper
from backend.schemas import Identifier, IdentifierType, RawProfile

logging.basicConfig(level="INFO", format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run verification suite for MaigretScraper caching and resolution."""
    # Ensure database tables exist
    init_db(settings.DB_PATH)

    scraper = MaigretScraper()
    id_octocat = Identifier(type=IdentifierType.USERNAME, value="octocat")

    # ── First Call: octocat (Cache Miss) ─────────────────────────────
    logger.info("=== Call 1: resolve('octocat') [expected cache miss] ===")
    t0 = time.perf_counter()
    profiles_1 = await scraper.resolve(id_octocat)
    elapsed_1 = time.perf_counter() - t0

    logger.info("Call 1 took %.2f seconds → %d profile(s)", elapsed_1, len(profiles_1))
    assert len(profiles_1) >= 3, f"Expected at least 3 profiles for octocat, got {len(profiles_1)}"
    for p in profiles_1:
        assert isinstance(p, RawProfile), f"Expected RawProfile, got {type(p)}"
        print(f"  - Platform: {p.platform.ljust(15)} | Handle: {p.value}")

    # ── Second Call: octocat (Cache Hit) ─────────────────────────────
    logger.info("\n=== Call 2: resolve('octocat') [expected cache hit] ===")
    t0 = time.perf_counter()
    profiles_2 = await scraper.resolve(id_octocat)
    elapsed_2 = time.perf_counter() - t0

    logger.info("Call 2 took %.4f seconds → %d profile(s)", elapsed_2, len(profiles_2))
    assert elapsed_2 < 1.0, f"Cache hit took {elapsed_2:.4f}s, expected < 1.0s"
    assert len(profiles_2) == len(profiles_1), f"Expected {len(profiles_1)} profiles, got {len(profiles_2)}"

    # ── Third Call: torvalds (Cache Miss) ────────────────────────────
    id_torvalds = Identifier(type=IdentifierType.USERNAME, value="torvalds")
    logger.info("\n=== Call 3: resolve('torvalds') [expected cache miss] ===")
    t0 = time.perf_counter()
    profiles_3 = await scraper.resolve(id_torvalds)
    elapsed_3 = time.perf_counter() - t0

    logger.info("Call 3 took %.2f seconds → %d profile(s)", elapsed_3, len(profiles_3))
    assert len(profiles_3) >= 3, f"Expected at least 3 profiles for torvalds, got {len(profiles_3)}"

    platforms_1 = {p.platform for p in profiles_1}
    platforms_3 = {p.platform for p in profiles_3}
    logger.info("Octocat platforms : %d unique", len(platforms_1))
    logger.info("Torvalds platforms: %d unique", len(platforms_3))

    logger.info("\n=== ALL GATE TESTS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(main())
