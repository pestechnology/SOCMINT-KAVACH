"""Search orchestrator — iterative seed expansion with parallel scraping, correlation, and scoring."""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from backend.config import settings
from backend.correlation.engine import CorrelationEngine
from backend.correlation.extractor import extract_identifiers_from_profile
from backend.database.db import get_connection
from backend.datasources.base import BaseDataSource
from backend.datasources.github import GitHubScraper
from backend.datasources.holehe import HoleheScraper
from backend.datasources.ignorant_scraper import IgnorantScraper
from backend.datasources.maigret import MaigretScraper
from backend.datasources.phoneinfoga import PhoneInfogaScraper
from backend.datasources.upi import UPIParser
from backend.ledger.ledger import AuditLedger
from backend.schemas import Identifier, IdentifierType, LinkedIdentity, RawProfile
from backend.scoring.engine import ScoringEngine

logger = logging.getLogger(__name__)

# ── Scraper registry ─────────────────────────────────────────────────
# Maps each identifier type to the scraper CLASSES that can handle it.
# The orchestrator instantiates each class — it never holds long-lived instances.

SEED_TOOL_MAP: dict[IdentifierType, list[type[BaseDataSource]]] = {
    IdentifierType.USERNAME: [MaigretScraper, GitHubScraper],
    IdentifierType.EMAIL: [HoleheScraper],
    IdentifierType.PHONE: [PhoneInfogaScraper, IgnorantScraper],
    IdentifierType.NAME: [],
    IdentifierType.UPI: [UPIParser],
    IdentifierType.FACE: [],
}


_SCRAPER_TIMEOUT: float = 100.0  # seconds per scraper

# ── Expansion limits (non-negotiable) ────────────────────────────────
_MAX_ITERATIONS: int = 3
_MAX_TOTAL_PROFILES: int = 200


async def _safe_resolve(
    scraper: BaseDataSource,
    identifier: Identifier,
) -> list[RawProfile]:
    """Wrap a single scraper resolve() with timeout. Returns empty list on any failure."""
    try:
        logger.debug("[orchestrator] starting %s for %s", scraper.name, identifier.value)
        result = await asyncio.wait_for(
            scraper.resolve(identifier),
            timeout=_SCRAPER_TIMEOUT,
        )
        logger.debug(
            "[orchestrator] %s finished → %d profiles",
            scraper.name,
            len(result),
        )
        return result

    except asyncio.TimeoutError:
        logger.warning(
            "[orchestrator] %s timed out after %.1fs for '%s'",
            scraper.name,
            _SCRAPER_TIMEOUT,
            identifier.value,
        )
        return []

    except Exception as e:
        logger.warning(
            "[orchestrator] %s raised %s: %s",
            scraper.name,
            type(e).__name__,
            e,
        )
        return []


async def run_investigation(
    identifier: Identifier | str,
    id_type: IdentifierType | None = None,
) -> tuple[list[RawProfile], list[LinkedIdentity]]:
    """Run iterative SOCMINT expansion starting from a single seed identifier.

    Loop:
      1. Scrape current frontier of identifiers (in parallel)
      2. Collect all RawProfiles
      3. Extract new identifiers from those profiles
      4. Filter out identifiers we've already searched
      5. Add new identifiers to next frontier
      6. Stop when frontier is empty OR max iterations reached
    """
    if isinstance(identifier, str):
        if id_type is None:
            raise ValueError("id_type required when identifier is str")
        identifier = Identifier(type=id_type, value=identifier)

    # ── Ensure case context & initialize audit ledger ─────────────────
    case_id = f"case_{identifier.type.value}_{identifier.value}"
    conn = get_connection(settings.DB_PATH)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, password_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("USR-KUMAR", "Inspector Kumar", "mockhash", "investigator", now),
        )
        seeds_json = json.dumps([{"type": identifier.type.value, "value": identifier.value}])
        conn.execute(
            "INSERT OR IGNORE INTO cases (case_id, user_id, title, seeds_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (case_id, "USR-KUMAR", f"Investigation: {identifier.value}", seeds_json, "pending", now, now),
        )
        conn.commit()
    finally:
        conn.close()

    ledger = AuditLedger()
    search_id = str(uuid.uuid4())

    input_init = {
        "identifier": {
            "type": identifier.type.value,
            "value": identifier.value,
        },
        "search_id": search_id,
    }
    ledger.record(case_id, "search_initiated", input_init, {})

    t0 = time.perf_counter()

    # ── Iterative seed expansion ─────────────────────────────────────
    seen_identifiers: set[tuple[str, str]] = set()  # (value.lower(), type.value)
    all_profiles: list[RawProfile] = []
    frontier: list[Identifier] = [identifier]
    iteration = 0

    while (
        frontier
        and iteration < _MAX_ITERATIONS
        and len(all_profiles) < _MAX_TOTAL_PROFILES
    ):
        iteration += 1
        logger.info(
            "[orchestrator] Iteration %d: scraping %d identifiers — %s",
            iteration,
            len(frontier),
            [(i.type.value, i.value) for i in frontier],
        )

        # Mark this frontier as seen
        for ident in frontier:
            seen_identifiers.add((ident.value.lower(), ident.type.value))

        # Build scrape tasks for ALL frontier identifiers in parallel
        scrape_tasks: list[asyncio.Task[list[RawProfile]]] = []
        for ident in frontier:
            scraper_classes = SEED_TOOL_MAP.get(ident.type, [])
            for scraper_cls in scraper_classes:
                scraper = scraper_cls()
                scrape_tasks.append(_safe_resolve(scraper, ident))

        if not scrape_tasks:
            logger.info(
                "[orchestrator] Iteration %d: no scrapers for frontier types, stopping",
                iteration,
            )
            break

        results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        # Flatten profiles from this iteration
        new_profiles: list[RawProfile] = []
        for r in results:
            if isinstance(r, list):
                new_profiles.extend(r)

        all_profiles.extend(new_profiles)

        # ── Audit ledger: log this iteration ─────────────────────────
        iteration_input = {
            "search_id": search_id,
            "iteration": iteration,
            "frontier": [
                {"type": i.type.value, "value": i.value} for i in frontier
            ],
        }
        iteration_output = {
            "new_profile_count": len(new_profiles),
            "total_profile_count": len(all_profiles),
        }
        ledger.record(case_id, "iterative_expansion", iteration_input, iteration_output)

        # ── Extract new identifiers from newly found profiles ────────
        next_frontier: list[Identifier] = []
        for profile in new_profiles:
            new_idents = extract_identifiers_from_profile(profile, identifier.value)
            for new_ident in new_idents:
                key = (new_ident.value.lower(), new_ident.type.value)
                if key not in seen_identifiers:
                    seen_identifiers.add(key)
                    next_frontier.append(new_ident)

            if profile.type == "upi_id":
                prefix = str(profile.metadata.get("username_prefix", "")).strip()
                if prefix:
                    if re.fullmatch(r"\d{10}", prefix):
                        next_seed = Identifier(type=IdentifierType.PHONE, value=prefix)
                    else:
                        next_seed = Identifier(type=IdentifierType.USERNAME, value=prefix)
                    key = (next_seed.value.lower(), next_seed.type.value)
                    if key not in seen_identifiers:
                        seen_identifiers.add(key)
                        next_frontier.append(next_seed)


        logger.info(
            "[orchestrator] Iteration %d complete: +%d profiles, +%d new seeds",
            iteration,
            len(new_profiles),
            len(next_frontier),
        )
        frontier = next_frontier

    scrape_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "[orchestrator] expansion done — %d total profiles across %d iteration(s) in %.1fms",
        len(all_profiles),
        iteration,
        scrape_ms,
    )

    # ── Correlate & score ────────────────────────────────────────────
    if all_profiles:
        clusters = CorrelationEngine().correlate(all_profiles)
        engine = ScoringEngine()
        for cluster in clusters:
            engine.score(cluster)
        engine.detect_red_herrings(clusters)
    else:
        clusters: list[LinkedIdentity] = []

    # ── Final audit ledger entry ─────────────────────────────────────
    cluster_summaries = [
        {
            "tier": c.tier,
            "confidence": c.confidence_score,
        }
        for c in clusters
    ]
    input_comp = {
        "search_id": search_id,
    }
    output_comp = {
        "profile_count": len(all_profiles),
        "cluster_count": len(clusters),
        "cluster_summaries": cluster_summaries,
        "iterations_used": iteration,
    }
    ledger.record(case_id, "search_completed", input_comp, output_comp)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "[orchestrator] done — %d profiles, %d clusters in %.1fms (%d iterations)",
        len(all_profiles),
        len(clusters),
        elapsed_ms,
        iteration,
    )

    return all_profiles, clusters
