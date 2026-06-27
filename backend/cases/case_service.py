"""
backend/cases/case_service.py — case CRUD with owner access control.

    create_case(user_id, title, seeds, minor_involved=False) -> case_id
    get_case(case_id, user_id) -> dict | None     # None if not owned by user_id
    list_cases(user_id) -> list[dict]
    set_status(case_id, status) -> None
    get_results(case_id, user_id) -> dict | None   # entities + clusters for the UI

Seeds are stored as a JSON string in cases.seeds_json.
Valid seed types: name, email, phone, username, upi, face.
"""
from __future__ import annotations

import datetime
import json
import uuid

from backend.database import get_db

VALID_SEED_TYPES = {"name", "email", "phone", "username", "upi", "face"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_case(user_id: str, title: str, seeds: list[dict],
                minor_involved: bool = False) -> str:
    for s in seeds:
        if s.get("type") not in VALID_SEED_TYPES:
            raise ValueError(f"invalid seed type: {s.get('type')!r}")
        if not s.get("value"):
            raise ValueError("seed value required")
    case_id = uuid.uuid4().hex
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO cases (case_id, user_id, title, seeds_json, minor_involved,
               status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)""",
            (case_id, user_id, title, json.dumps(seeds), int(minor_involved),
             "pending", _now(), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return case_id


def get_case(case_id: str, user_id: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    finally:
        conn.close()
    if not row or row["user_id"] != user_id:
        return None
    d = dict(row)
    d["seeds"] = json.loads(d.get("seeds_json") or "[]")
    return d


def list_cases(user_id: str) -> list[dict]:
    # Single query with a LEFT JOIN aggregate — avoids the previous N+1
    # (one extra connection + COUNT per case).
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT c.*, COUNT(e.entity_id) AS account_count
               FROM cases c
               LEFT JOIN entities e ON e.case_id = c.case_id
               WHERE c.user_id = ?
               GROUP BY c.case_id
               ORDER BY c.created_at DESC""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["seeds"] = json.loads(d.get("seeds_json") or "[]")
        out.append(d)
    return out


def set_status(case_id: str, status: str) -> None:
    conn = get_db()
    try:
        conn.execute("UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
                     (status, _now(), case_id))
        conn.commit()
    finally:
        conn.close()


def get_results(case_id: str, user_id: str) -> dict | None:
    """Entities + clusters for the results dashboard (access-controlled)."""
    case = get_case(case_id, user_id)
    if not case:
        return None
    conn = get_db()
    try:
        entities = [dict(e) for e in conn.execute(
            "SELECT * FROM entities WHERE case_id = ? ORDER BY rowid", (case_id,)).fetchall()]
        clusters = [dict(c) for c in conn.execute(
            "SELECT * FROM clusters WHERE case_id = ? ORDER BY confidence_score DESC",
            (case_id,)).fetchall()]
    finally:
        conn.close()
    for e in entities:
        e["metadata"] = json.loads(e.get("metadata_json") or "{}")
    for c in clusters:
        c["entity_ids"] = json.loads(c.get("entity_ids_json") or "[]")
        c["signals"] = json.loads(c.get("signals_json") or "{}")
    return {"case": case, "entities": entities, "clusters": clusters,
            "status": case.get("status")}
