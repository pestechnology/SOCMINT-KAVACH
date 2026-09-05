"""
backend/cases/annotations_service.py — per-user bookmarks + severity flags on accounts.

Two investigator annotations, stored together per (user, case, account):
  - bookmarked: a saved account/result the investigator wants to return to.
  - flag: a red/orange/yellow SEVERITY marker.
        red    = high concern / confirmed threat
        orange = medium / suspicious
        yellow = low / watch
        ''     = no flag
  - note: optional free text.

STABLE KEY (why not entity_id): entity_id is a random uuid the orchestrator regenerates
on every re-scrape/pivot (it DELETEs + re-INSERTs a case's entities), so an annotation
keyed on entity_id would vanish on the next pivot. Annotations are therefore keyed on a
content signature — target_key = "type:platform:value" (normalized) — which is stable
because the same account re-discovered produces the same triple. The API still speaks
entity_id to the frontend; we resolve entity_id -> target_key here, and on read map the
stored annotations back onto whatever entity_ids currently exist.

Access control: every function takes user_id and verifies case ownership via get_case,
so one investigator can never read or write another's annotations, and annotations are
private per user even on the same case.
"""
from __future__ import annotations

import datetime
import json
import uuid

from backend.cases.case_service import get_case
from backend.database import get_db

VALID_FLAGS = {"", "red", "orange", "yellow"}


def target_key_for(entity_type: str, platform: str, value: str) -> str:
    """Stable content signature for an account, normalized so the same account always
    maps to the same key regardless of casing/whitespace or a re-run's fresh uuid."""
    parts = [str(x or "").strip().lower() for x in (entity_type, platform, value)]
    return ":".join(parts)


def _key_from_entity_row(row) -> str:
    return target_key_for(row["type"], row["platform"], row["value"])


def _resolve_entity(conn, case_id: str, entity_id: str):
    """Return the entity row for (case_id, entity_id), or None."""
    return conn.execute(
        "SELECT entity_id, type, platform, value FROM entities "
        "WHERE case_id = ? AND entity_id = ?",
        (case_id, entity_id),
    ).fetchone()


def get_annotations(case_id: str, user_id: str) -> dict | None:
    """All of this user's annotations for this case, mapped onto CURRENT entity_ids.

    Returns None if the case doesn't exist or isn't owned by user_id. Otherwise:
        {"by_entity": { entity_id: {bookmarked, flag, note} },
         "by_key":    { target_key: {bookmarked, flag, note} }}
    by_entity is what the UI consumes; by_key is included so annotations on accounts not
    currently present (e.g. dropped by a re-run) are not silently hidden.
    """
    if not get_case(case_id, user_id):
        return None
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT target_key, bookmarked, flag, note FROM annotations "
            "WHERE user_id = ? AND case_id = ?",
            (user_id, case_id),
        ).fetchall()
        by_key = {
            r["target_key"]: {
                "bookmarked": bool(r["bookmarked"]),
                "flag": r["flag"] or "",
                "note": r["note"] or "",
            }
            for r in rows
        }
        entities = conn.execute(
            "SELECT entity_id, type, platform, value FROM entities WHERE case_id = ?",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()

    by_entity = {}
    for e in entities:
        ann = by_key.get(_key_from_entity_row(e))
        if ann:
            by_entity[e["entity_id"]] = ann
    return {"by_entity": by_entity, "by_key": by_key}


def set_annotation(case_id: str, user_id: str, entity_id: str,
                   bookmarked: bool | None = None, flag: str | None = None,
                   note: str | None = None) -> dict | None:
    """Upsert one account's annotation. Only the provided fields change (a None field is
    left as-is on an existing row, or defaulted on a new one).

    Returns the resulting {bookmarked, flag, note}, or None if the case/entity is not
    found or not owned by user_id. Raises ValueError on an invalid flag.
    """
    if flag is not None and flag not in VALID_FLAGS:
        raise ValueError(f"invalid flag {flag!r}; allowed: {sorted(VALID_FLAGS)}")
    if not get_case(case_id, user_id):
        return None

    conn = get_db()
    try:
        ent = _resolve_entity(conn, case_id, entity_id)
        if not ent:
            return None
        key = _key_from_entity_row(ent)
        existing = conn.execute(
            "SELECT bookmarked, flag, note FROM annotations "
            "WHERE user_id = ? AND case_id = ? AND target_key = ?",
            (user_id, case_id, key),
        ).fetchone()

        cur_bm = bool(existing["bookmarked"]) if existing else False
        cur_flag = (existing["flag"] if existing else "") or ""
        cur_note = (existing["note"] if existing else "") or ""

        new_bm = cur_bm if bookmarked is None else bool(bookmarked)
        new_flag = cur_flag if flag is None else flag
        new_note = cur_note if note is None else str(note)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # If everything is cleared, delete the row rather than keep an empty annotation.
        if not new_bm and not new_flag and not new_note:
            if existing:
                conn.execute(
                    "DELETE FROM annotations WHERE user_id = ? AND case_id = ? AND target_key = ?",
                    (user_id, case_id, key),
                )
                conn.commit()
            return {"bookmarked": False, "flag": "", "note": ""}

        if existing:
            conn.execute(
                "UPDATE annotations SET bookmarked = ?, flag = ?, note = ?, updated_at = ? "
                "WHERE user_id = ? AND case_id = ? AND target_key = ?",
                (int(new_bm), new_flag, new_note, now, user_id, case_id, key),
            )
        else:
            conn.execute(
                "INSERT INTO annotations (annotation_id, user_id, case_id, target_key, "
                "bookmarked, flag, note, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, user_id, case_id, key, int(new_bm), new_flag, new_note, now),
            )
        conn.commit()
    finally:
        conn.close()
    return {"bookmarked": new_bm, "flag": new_flag, "note": new_note}


def list_flagged(user_id: str) -> dict:
    """Every red/orange/yellow-flagged ACCOUNT across ALL of this user's cases, grouped
    by colour — powers the cross-case "Flagged" dashboard (three columns, one per
    severity, click an item to jump to its case).

    Single query for the annotation rows, then one batched lookup of the owning cases'
    titles and their current entities (rather than N+1 per-case round trips). An
    annotation is only included once it resolves to a CURRENTLY EXISTING entity_id —
    same rule get_annotations() uses — so a flagged account dropped by a later re-scrape
    doesn't show up as a dead link with no photo/name to render.

    Returns {"red": [...], "orange": [...], "yellow": [...]}, each entry newest-first:
        {case_id, case_title, entity_id, type, platform, value, name, photo_url, bio,
         source_url, note, bookmarked, updated_at}
    """
    out = {k: [] for k in VALID_FLAGS if k}  # {"red": [], "orange": [], "yellow": []}
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT case_id, target_key, flag, bookmarked, note, updated_at FROM annotations "
            "WHERE user_id = ? AND flag != '' ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        if not rows:
            return out
        case_ids = sorted({r["case_id"] for r in rows})
        placeholders = ",".join("?" * len(case_ids))
        cases = {
            r["case_id"]: r["title"]
            for r in conn.execute(
                f"SELECT case_id, title FROM cases WHERE user_id = ? AND case_id IN ({placeholders})",
                (user_id, *case_ids),
            ).fetchall()
        }
        entities = conn.execute(
            f"SELECT case_id, entity_id, type, value, platform, metadata_json, source_url "
            f"FROM entities WHERE case_id IN ({placeholders})",
            case_ids,
        ).fetchall()
    finally:
        conn.close()

    # (case_id, target_key) -> live entity row, so each annotation resolves to whatever
    # account currently carries that content signature (see module docstring).
    by_case_key = {(e["case_id"], _key_from_entity_row(e)): e for e in entities}

    for r in rows:
        case_title = cases.get(r["case_id"])
        ent = by_case_key.get((r["case_id"], r["target_key"]))
        if case_title is None or ent is None:
            continue  # case not owned by this user, or account dropped by a re-run
        meta = json.loads(ent["metadata_json"] or "{}")
        out.setdefault(r["flag"], []).append({
            "case_id": r["case_id"],
            "case_title": case_title,
            "entity_id": ent["entity_id"],
            "type": ent["type"],
            "platform": ent["platform"],
            "value": ent["value"],
            "name": meta.get("fullname") or meta.get("name") or "",
            "photo_url": meta.get("photo_url") or "",
            "bio": meta.get("bio") or meta.get("title") or "",
            "source_url": ent["source_url"] or "",
            "note": r["note"] or "",
            "bookmarked": bool(r["bookmarked"]),
            "updated_at": r["updated_at"],
        })
    return out
