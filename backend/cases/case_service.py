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

VALID_SEED_TYPES = {"name", "email", "phone", "username", "upi", "face", "url"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_case(user_id: str, title: str, seeds: list[dict],
                minor_involved: bool = False, country_filter: str = "ALL") -> str:
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
               status, country_filter, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (case_id, user_id, title, json.dumps(seeds), int(minor_involved),
             "pending", country_filter or "ALL", _now(), _now()),
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
        raw_signals = json.loads(c.get("signals_json") or "{}")
        # Keep `signals` as PURE corroborating evidence. Internal ranking metadata is
        # written into signals_json under `_`-prefixed keys (see orchestrator.py) so it
        # rides along to the client, but it is NOT evidence — surfacing it in the
        # Evidence quick-links / "matching evidence" list (as "Relevance Score",
        # "Relevance Rank", …) is misleading. Split it into its own `relevance` field.
        c["signals"] = {k: v for k, v in raw_signals.items() if not k.startswith("_")}
        c["relevance"] = {
            "score": raw_signals.get("_relevance_score"),
            "reason": raw_signals.get("_relevance_reason"),
            "rank": raw_signals.get("_relevance_rank"),
        }
        # AI-adjudicated (LLM-confirmed) link — surfaced distinctly so the UI/report can
        # label it "AI-assessed", not a forensically-anchored hard-evidence match.
        c["ai_confirmed"] = bool(raw_signals.get("_ai_confirmed"))
        c["ai_confidence"] = raw_signals.get("_ai_confidence") or 0
        c["ai_reason"] = raw_signals.get("_ai_reason") or ""
        # User-facing MATCH CONFIDENCE (LOW/MEDIUM/HIGH) — "is this a correct match for the
        # search?", distinct from the forensic `tier` ("same person?"). Exact username/seed
        # matches are HIGH; everything else is graded by algo + LLM (scoring/confidence.py).
        c["match"] = {
            "score": raw_signals.get("_match_score") or 0,
            "tier": raw_signals.get("_match_tier") or "LOW",
            "reason": raw_signals.get("_match_reason") or "",
        }
    # Leak-account pivot: lift the best real name found on ANY member up to label the
    # whole persona cluster. Suspects fake their name on the main account but often leak
    # it on a careless/old account tied in by hard signals; this attributes the cluster.
    try:
        from backend.analysis.name_intel import resolve_cluster_identity
        ent_by_id = {e["entity_id"]: e for e in entities}
        for c in clusters:
            members = [ent_by_id[i] for i in c.get("entity_ids", []) if i in ent_by_id]
            ident = resolve_cluster_identity(members)
            if ident:
                c["identity"] = ident
    except Exception:
        pass
    _TIER_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "REJECT": 0}
    clusters.sort(
        key=lambda c: (
            (c.get("relevance", {}).get("score") or 0) >= 100,
            _TIER_RANK.get(c.get("match", {}).get("tier", "LOW"), 1),
            c.get("match", {}).get("score") or 0,
            len(c.get("entity_ids", [])) > 1,
            c.get("confidence_score", 0),
        ),
        reverse=True,
    )
    # forensic summary (tone/sentiment, keywords, activity, engagement) for the UI
    try:
        from backend.analysis.forensics import summarize as _forensics
        forensics = _forensics(entities)
    except Exception:
        forensics = {}
    # Clean, LLM-classified identity (real names / aliases / locations / employers) for the
    # Names & aliases + Locations panels — replaces the raw metadata dump that leaked junk
    # (ratings as names, handles as names, locations as names). Only worth the LLM call once
    # the investigation is complete; the agent caches per case so polling doesn't re-run it.
    if case.get("status") == "complete":
        try:
            from backend.analysis.identity_agent import classify as _classify_identity
            ident = _classify_identity(entities, case_id=case_id)
            forensics["identity"] = ident
            # The identity agent's `interests` field replaces the old standalone keyword
            # agent: cleaner (topics/skills, not the person's own name echoed back) and one
            # fewer LLM call per run. Only override when it actually produced interests.
            if ident.get("interests"):
                forensics["keywords"] = ident["interests"]
        except Exception:
            pass
    # "What should the officer do next?" — VERTEX's investigative-copilot layer. Ranked,
    # actionable next steps derived from the case state (LLM + deterministic fallback). Only
    # meaningful once the scan is complete; cached per case so polling doesn't re-run the LLM.
    next_actions = []
    chat_suggestions = []
    if case.get("status") == "complete":
        try:
            from backend.analysis.next_actions import recommend as _recommend_actions
            next_actions = _recommend_actions(case, entities, clusters)
        except Exception:
            next_actions = []
        try:
            from backend.analysis.case_chat import suggested_queries as _chat_suggest
            chat_suggestions = _chat_suggest(case, entities, clusters)
        except Exception:
            chat_suggestions = []
    return {"case": case, "entities": entities, "clusters": clusters,
            "forensics": forensics, "next_actions": next_actions,
            "chat_suggestions": chat_suggestions, "status": case.get("status")}
