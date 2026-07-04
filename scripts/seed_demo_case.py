"""
scripts/seed_demo_case.py — build a complete demo case end-to-end using the mock
data, persisting entities + clusters + ledger + an artifact. Used to test the PDF
generator and the frontend before the live scrapers exist.

Run:  python -m scripts.seed_demo_case
Returns/prints the created case_id.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import uuid

from backend.correlation.correlation_engine import correlate
from backend.database import get_db, init_db
from backend.ingestion.mock_scraper import MockScraper
from backend.ledger.audit_ledger import log_action, save_artifact
from backend.scoring.scoring_engine import score


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def seed_demo_case(seed_value: str = "arjun", title: str = "Demo investigation",
                   minor_involved: bool = False) -> str:
    init_db()
    conn = get_db()
    try:
        # user
        user_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (user_id, f"officer_{user_id[:6]}", "x", "investigator", _now()),
        )
        # case
        case_id = uuid.uuid4().hex
        seeds = [{"type": "username", "value": seed_value}]
        conn.execute(
            """INSERT INTO cases (case_id, user_id, title, seeds_json, minor_involved,
               status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)""",
            (case_id, user_id, title, json.dumps(seeds), int(minor_involved),
             "running", _now(), _now()),
        )
        conn.commit()
    finally:
        conn.close()

    log_action(case_id, "investigation_started", {"seeds": seeds}, None, "system")

    # scrape (mock), correlate, score
    profiles = asyncio.run(MockScraper().resolve(seed_value, "mock"))
    log_action(case_id, "mock_scrape", {"seed": seed_value}, {"profiles": len(profiles)}, "system")

    # persist entities, remember index -> entity_id
    conn = get_db()
    idx_to_eid: dict[int, str] = {}
    try:
        for i, p in enumerate(profiles):
            eid = uuid.uuid4().hex
            idx_to_eid[i] = eid
            conn.execute(
                """INSERT INTO entities (entity_id, case_id, type, value, platform, confidence,
                   metadata_json, source_url, data_mode, sha256, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, case_id, p.type, p.value, p.platform, None,
                 json.dumps(p.metadata), p.source_url, p.data_mode, p.sha256, p.collected_at),
            )
        conn.commit()
    finally:
        conn.close()

    pairs = correlate(profiles)
    clusters = score(profiles, pairs)
    log_action(case_id, "scoring_complete", {"pairs": len(pairs)},
               {"clusters": len(clusters)}, "system")

    # persist clusters
    conn = get_db()
    try:
        for cl in clusters:
            entity_ids = [idx_to_eid[i] for i in cl.member_indices]
            conn.execute(
                """INSERT INTO clusters (cluster_id, case_id, entity_ids_json, confidence_score,
                   tier, explanation, signals_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (cl.cluster_id, case_id, json.dumps(entity_ids), cl.confidence_score,
                 cl.tier, cl.explanation, json.dumps(cl.signals), _now()),
            )
        conn.commit()
    finally:
        conn.close()

    # capture an artifact (the raw scrape dump) + hash it
    dump = json.dumps([p.to_dict() for p in profiles], indent=2)
    save_artifact(case_id, None, "json_dump", dump, suffix=".json")
    log_action(case_id, "artifact_captured", None, {"type": "json_dump"}, "system")

    # mark complete
    conn = get_db()
    try:
        conn.execute("UPDATE cases SET status='complete', updated_at=? WHERE case_id=?",
                     (_now(), case_id))
        conn.commit()
    finally:
        conn.close()
    log_action(case_id, "investigation_complete", None, {"status": "complete"}, "system")

    return case_id


if __name__ == "__main__":
    cid = seed_demo_case()
    print(cid)
