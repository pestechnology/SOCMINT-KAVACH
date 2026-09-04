"""
backend/cases/collections_service.py — named case collections (folders/watchlists).

An investigator files cases into named collections (e.g. "Fraud Ring A", "Priority",
"Cold cases") the way one saves stocks into categories, then filters the case list by
them. Per-user; a case may belong to many collections.

Two tables: `collections` (the user's named folders) and `case_collections` (the
membership map). Every function is user-scoped, and case membership is only ever written
after verifying BOTH that the user owns the case (get_case) AND that the target
collection belongs to the same user — so nothing here can leak a case into another
investigator's collection or vice versa.
"""
from __future__ import annotations

import datetime
import uuid

from backend.cases.case_service import get_case
from backend.database import get_db

MAX_NAME_LEN = 60


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def list_collections(user_id: str) -> list[dict]:
    """This user's collections with a live case-count each, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT c.collection_id, c.name, c.color, c.created_at,
                      COUNT(cc.case_id) AS case_count
               FROM collections c
               LEFT JOIN case_collections cc
                 ON cc.collection_id = c.collection_id AND cc.user_id = c.user_id
               WHERE c.user_id = ?
               GROUP BY c.collection_id
               ORDER BY c.created_at DESC""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def memberships(user_id: str) -> dict[str, list[str]]:
    """{case_id: [collection_id, ...]} for every filed case of this user."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT case_id, collection_id FROM case_collections WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["case_id"], []).append(r["collection_id"])
    return out


def create_collection(user_id: str, name: str, color: str = "") -> dict:
    """Create a collection, or return the existing one if the name is already taken
    (idempotent on name — the UNIQUE(user_id, name) constraint). Raises ValueError on a
    blank/too-long name."""
    name = (name or "").strip()
    if not name:
        raise ValueError("collection name is required")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"name too long (max {MAX_NAME_LEN})")
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT collection_id, name, color, created_at FROM collections "
            "WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if existing:
            return {**dict(existing), "case_count": 0}
        cid = uuid.uuid4().hex
        now = _now()
        conn.execute(
            "INSERT INTO collections (collection_id, user_id, name, color, created_at) "
            "VALUES (?,?,?,?,?)",
            (cid, user_id, name, color or "", now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"collection_id": cid, "name": name, "color": color or "",
            "created_at": now, "case_count": 0}


def delete_collection(user_id: str, collection_id: str) -> bool:
    """Delete a collection and its memberships. True if it existed and was this user's."""
    conn = get_db()
    try:
        owned = conn.execute(
            "SELECT 1 FROM collections WHERE collection_id = ? AND user_id = ?",
            (collection_id, user_id),
        ).fetchone()
        if not owned:
            return False
        conn.execute(
            "DELETE FROM case_collections WHERE collection_id = ? AND user_id = ?",
            (collection_id, user_id),
        )
        conn.execute(
            "DELETE FROM collections WHERE collection_id = ? AND user_id = ?",
            (collection_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def set_case_collections(user_id: str, case_id: str,
                         collection_ids: list[str]) -> list[str] | None:
    """Replace the set of collections a case belongs to. Returns the accepted
    collection_ids, or None if the user doesn't own the case. Any id not owned by the
    user is silently ignored (never an error, never a cross-user write)."""
    if not get_case(case_id, user_id):
        return None
    requested = [str(c) for c in (collection_ids or [])]
    conn = get_db()
    try:
        owned = {
            r["collection_id"]
            for r in conn.execute(
                "SELECT collection_id FROM collections WHERE user_id = ?", (user_id,)
            ).fetchall()
        }
        valid = [c for c in requested if c in owned]
        conn.execute(
            "DELETE FROM case_collections WHERE user_id = ? AND case_id = ?",
            (user_id, case_id),
        )
        now = _now()
        for cid in valid:
            conn.execute(
                "INSERT OR IGNORE INTO case_collections "
                "(user_id, case_id, collection_id, added_at) VALUES (?,?,?,?)",
                (user_id, case_id, cid, now),
            )
        conn.commit()
    finally:
        conn.close()
    return valid
