"""
backend/pipeline/orchestrator.py — runs one investigation end to end.

run_investigation(case_id) (async) and run_investigation_sync(case_id) (for
FastAPI BackgroundTasks). Flow:

  1. read case seeds
  2. for each seed, fan out the applicable scrapers in parallel (asyncio.gather,
     return_exceptions=True so one failure never kills the batch)
  3. one-level cascade: any derived username/phone seed (e.g. from a UPI) is run
     through its own tools
  4. LLM entity-extraction on free-text blobs (bios/snippets) -> extra seeds folded in
  5. dedup -> persist entities (streaming: written as soon as scraping is done)
  6. correlate -> score -> persist clusters with LLM/template explanations
  7. ledger-log each major step; mark the case complete

DATA_MODE="mock" routes every scraper to its mock branch (dev only).
"""
from __future__ import annotations

import asyncio
import json
import uuid

from backend import config
from backend.cases.case_service import set_status
from backend.correlation.correlation_engine import correlate
from backend.database import get_db
from backend.ingestion.base_module import RawProfile
from backend.ingestion.github_scraper import GitHubScraper
from backend.ingestion.hibp_scraper import HIBPScraper
from backend.ingestion.maigret_scraper import MaigretScraper
from backend.ingestion.mock_scraper import MockScraper
from backend.ingestion.phone_scrapers import IgnorantScraper, PhoneInfogaScraper
from backend.ingestion.serper_scraper import SerperScraper
from backend.ingestion.upi_module import UPIScraper
from backend.ingestion.url_scraper import URLScraper
from backend.ledger.audit_ledger import log_action, save_artifact
from backend.llm.llm_client import LLMClient
from backend.scoring.scoring_engine import score

# Seed type -> scraper instances (Section 11.1). SerperScraper templates vary per seed.
def _seed_tool_map() -> dict:
    live = {
        "email":    [HIBPScraper(), GitHubScraper(), SerperScraper('"{q}"')],
        "phone":    [PhoneInfogaScraper(), IgnorantScraper(), SerperScraper('site:truecaller.com "{q}"')],
        "username": [MaigretScraper(), GitHubScraper(), SerperScraper('"{q}"')],
        "upi":      [UPIScraper(), SerperScraper('"{q}"')],
        "name":     [SerperScraper('site:linkedin.com/in "{q}"'),
                     SerperScraper('site:instagram.com "{q}"'),
                     SerperScraper('site:twitter.com "{q}"')],
        "face":     [],   # handled separately (pHash against collected photos)
        "url":      [URLScraper()],
    }
    if config.DATA_MODE == "mock":
        # development only: every seed type yields the fixed mock dataset so the full
        # pipeline (correlate/score/ledger/PDF) can run offline. UPI still parses for real.
        mock = MockScraper()
        for k in live:
            live[k] = [mock] + ([UPIScraper()] if k == "upi" else []) + ([URLScraper()] if k == "url" else [])
    return live


def _now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def _scrape_seed(seed_type: str, value: str, tool_map: dict) -> list[RawProfile]:
    tools = tool_map.get(seed_type, [SerperScraper('"{q}"')])
    tasks = [t.resolve(value, config.DATA_MODE) for t in tools]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    profiles: list[RawProfile] = []
    for r in results:
        if isinstance(r, list):
            profiles.extend(r)
    return profiles


def _dedup(profiles: list[RawProfile]) -> list[RawProfile]:
    out: list[RawProfile] = []
    seen_social: dict[tuple[str, str], RawProfile] = {}
    seen_other: dict[tuple[str, str, str], RawProfile] = {}

    for p in profiles:
        plat = p.platform.lower()
        val = (p.value or "").lower()

        if p.type == "social_account":
            key = (plat, val)
            if key in seen_social:
                existing = seen_social[key]
                # Merge metadata
                existing.metadata = {**p.metadata, **existing.metadata}
                if not existing.source_url and p.source_url:
                    existing.source_url = p.source_url
            else:
                seen_social[key] = p
                out.append(p)
        else:
            url = (p.source_url or "").lower().rstrip("/")
            key_other = (plat, val, url)
            if key_other in seen_other:
                existing = seen_other[key_other]
                existing.metadata = {**p.metadata, **existing.metadata}
            else:
                seen_other[key_other] = p
                out.append(p)
    return out


async def run_investigation(case_id: str) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"status": "error", "reason": "case not found"}

    seeds = json.loads(row["seeds_json"] or "[]")
    set_status(case_id, "running")

    # idempotent re-runs: clear prior findings (ledger stays append-only by design)
    conn = get_db()
    try:
        conn.execute("DELETE FROM entities WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM clusters WHERE case_id = ?", (case_id,))
        conn.commit()
    finally:
        conn.close()

    log_action(case_id, "investigation_started", {"seeds": seeds}, None, "system")

    tool_map = _seed_tool_map()
    all_profiles: list[RawProfile] = []

    # 1+2: primary fan-out per seed
    for seed in seeds:
        ps = await _scrape_seed(seed.get("type"), seed.get("value"), tool_map)
        log_action(case_id, f"scrape:{seed.get('type')}",
                   {"value": seed.get("value")}, {"found": len(ps)}, "system")
        all_profiles.extend(ps)

    # 3: one-level cascade for derived seeds (e.g. UPI -> username/phone)
    derived = [p for p in all_profiles if p.platform == "derived"
               and p.metadata.get("cascade")]
    for d in derived:
        ps = await _scrape_seed(d.type, d.value, tool_map)
        log_action(case_id, f"cascade:{d.type}", {"value": d.value}, {"found": len(ps)}, "system")
        all_profiles.extend(ps)

    # 4: LLM entity-extraction over free-text blobs -> extra username/email seeds
    llm = LLMClient()
    blobs = []
    for p in all_profiles:
        for k in ("bio", "snippet"):
            v = p.metadata.get(k)
            if v and isinstance(v, str) and len(v) > 10:
                blobs.append(v)
    extracted_seeds = []
    for blob in blobs[:10]:           # cap to keep it fast
        for ent in llm.extract_entities(blob):
            if ent.get("type") in ("username", "email") and ent.get("value"):
                extracted_seeds.append(ent)
    if extracted_seeds:
        log_action(case_id, "llm_entity_extraction", {"blobs": len(blobs)},
                   {"new_seeds": len(extracted_seeds)}, "system")

    # bio-link expansion: run scrapers on NEW identifiers self-disclosed in bios,
    # skipping ones we've already searched. Bounded to avoid runaway expansion.
    seen_seeds = {(s.get("type"), str(s.get("value")).lower()) for s in seeds}
    seen_seeds |= {(d.type, (d.value or "").lower()) for d in derived}
    expansions = 0
    for ent in extracted_seeds:
        key = (ent["type"], str(ent["value"]).lower())
        if key in seen_seeds:
            continue
        seen_seeds.add(key)
        expansions += 1
        if expansions > 5:            # hard cap (Section: max iterations)
            break
        ps = await _scrape_seed(ent["type"], ent["value"], tool_map)
        log_action(case_id, f"expand:{ent['type']}", {"value": ent["value"]},
                   {"found": len(ps)}, "system")
        all_profiles.extend(ps)

    # 5: dedup + persist entities (streaming write)
    profiles = _dedup(all_profiles)
    idx_to_eid: dict[int, str] = {}
    conn = get_db()
    try:
        for i, p in enumerate(profiles):
            eid = uuid.uuid4().hex
            idx_to_eid[i] = eid
            conn.execute(
                """INSERT INTO entities (entity_id, case_id, type, value, platform, confidence,
                   metadata_json, source_url, data_mode, sha256, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, case_id, p.type, p.value, p.platform, None,
                 json.dumps(p.metadata, default=str), p.source_url, p.data_mode,
                 p.sha256, p.collected_at),
            )
        conn.commit()
    finally:
        conn.close()

    # raw scrape dump as a hashed artifact
    save_artifact(case_id, None, "json_dump",
                  json.dumps([p.to_dict() for p in profiles], indent=2, default=str),
                  suffix=".json")

    # 6: correlate -> score -> persist clusters with explanations
    pairs = correlate(profiles)
    clusters = score(profiles, pairs)
    log_action(case_id, "scoring_complete", {"pairs": len(pairs)},
               {"clusters": len(clusters)}, "system")

    conn = get_db()
    try:
        for cl in clusters:
            entity_ids = [idx_to_eid[i] for i in cl.member_indices]
            # LLM explanation for multi-member clusters; template fallback inside the client
            explanation = cl.explanation
            if len(cl.member_indices) > 1 and cl.signals:
                explanation = llm.explain_match(list(cl.signals.keys()), cl.tier)
            conn.execute(
                """INSERT INTO clusters (cluster_id, case_id, entity_ids_json, confidence_score,
                   tier, explanation, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (cl.cluster_id, case_id, json.dumps(entity_ids), cl.confidence_score,
                 cl.tier, explanation, json.dumps(cl.signals), _now()),
            )
            # write each member's confidence onto its entity row
            for eid in entity_ids:
                conn.execute("UPDATE entities SET confidence=? WHERE entity_id=?",
                             (cl.confidence_score, eid))
        conn.commit()
    finally:
        conn.close()

    set_status(case_id, "complete")
    log_action(case_id, "investigation_complete", None,
               {"accounts": len(profiles), "clusters": len(clusters)}, "system")
    return {"status": "complete", "accounts": len(profiles), "clusters": len(clusters)}


def run_investigation_sync(case_id: str) -> dict:
    """Blocking wrapper for FastAPI BackgroundTasks."""
    try:
        return asyncio.run(run_investigation(case_id))
    except Exception as e:  # noqa: BLE001
        set_status(case_id, "error")
        log_action(case_id, "investigation_error", None, {"error": str(e)}, "system")
        return {"status": "error", "reason": str(e)}
