"""Agentic browser: schema conversion, NO fabrication, auth, and pipeline integration.

Critical properties under test:
  * extracted data converts cleanly into VERTEX's RawProfile;
  * when the live browser is unavailable, the engine RAISES - it never fabricates;
  * ingested profiles flow THROUGH correlation (they link to related accounts), and are
    NOT inserted as standalone islands; exact duplicates are skipped;
  * endpoints require auth and enforce case ownership.

Uses the conftest `client` / `auth_headers` fixtures for API tests (real auth) - no global
dependency override, so app-level auth is never polluted for the rest of the suite.
"""
import asyncio
import json
import uuid

import pytest

from backend.agentic_browser.schemas import (
    ExtractedWebProfile, ExtractedProfilesResult, AgenticLookupRequest,
)
from backend.agentic_browser.agent import AgenticBrowserEngine, get_curated_tools
from backend.agentic_browser import service
from backend.pipeline.orchestrator import ingest_external_profiles
from backend.cases.case_service import create_case, get_results
from backend.auth.auth_service import register_user
from backend.database import get_db


# ---------- schema / conversion ----------
def test_extracted_profile_converts_to_raw_profile():
    ep = ExtractedWebProfile(platform="Instagram", username="ash29_03", value="ash29_03",
                             fullname="Ashwin Harish", bio="hi", followers=100,
                             profile_photo="http://x/p.jpg")
    rp = ep.to_raw_profile()
    assert rp.type == "social_account"
    assert rp.platform == "instagram"
    assert rp.value == "ash29_03"
    assert rp.data_mode == "agentic_web"
    assert rp.metadata["name"] == "Ashwin Harish"
    assert rp.metadata["username"] == "ash29_03"
    assert rp.metadata["photo_url"] == "http://x/p.jpg"
    assert rp.metadata["agentic_source"] is True


def test_result_wrapper_defaults_to_empty_not_fabricated():
    r = ExtractedProfilesResult()
    assert r.profiles == [] and r.blocked is False


def test_curated_tools_dropped_whatsmyname():
    ids = {t.id for t in get_curated_tools()}
    assert "socialsearcher" in ids and "custom" in ids
    assert "whatsmyname_web" not in ids


# ---------- NO fabrication when the live browser is unavailable ----------
def test_engine_unavailable_without_key_raises(monkeypatch):
    import backend.agentic_browser.agent as agent_mod
    monkeypatch.setattr(agent_mod, "GEMINI_API_KEY", "")
    eng = AgenticBrowserEngine(mode="auto")
    ok, reason = eng.live_available()
    assert ok is False and "GEMINI" in reason
    with pytest.raises(RuntimeError):
        asyncio.run(eng.run_task("socialsearcher", "ash29_03"))


# ---------- pipeline integration (the make-or-break) ----------
def _case_with_seed_and_entity(email: str):
    uid = register_user("u_" + uuid.uuid4().hex[:8], "secret123")
    cid = create_case(uid, "t", [{"type": "username", "value": "ash29_03"}])
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO entities (entity_id, case_id, type, value, platform, confidence,
               metadata_json, source_url, data_mode, sha256, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (uuid.uuid4().hex, cid, "social_account", "existing_acct", "twitter", None,
             json.dumps({"email": email, "phone": "+15551234567"}), "https://twitter.com/existing_acct", "live",
             "hash_existing", "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    return uid, cid


def test_ingest_links_agentic_profile_not_island():
    uid, cid = _case_with_seed_and_entity("shared@x.com")
    ep = ExtractedWebProfile(platform="instagram", username="ash29_03", value="ash29_03",
                             additional_metadata={"email": "shared@x.com", "phone": "+15551234567"})
    stats = ingest_external_profiles(cid, [ep.to_raw_profile()])
    assert stats["added"] == 1

    res = get_results(cid, uid)
    agentic = [e for e in res["entities"] if e["data_mode"] == "agentic_web"]
    assert len(agentic) == 1
    assert agentic[0]["metadata"].get("exact_seed_match") is True
    linked = [c for c in res["clusters"] if len(c["entity_ids"]) >= 2]
    if not linked:
        assert False, f"clusters={res['clusters']} entities={res['entities']}"


def test_ingest_skips_exact_duplicate():
    uid, cid = _case_with_seed_and_entity("a@b.com")
    ep = ExtractedWebProfile(platform="instagram", username="dup", value="dup")
    ingest_external_profiles(cid, [ep.to_raw_profile()])
    n1 = len(get_results(cid, uid)["entities"])
    ingest_external_profiles(cid, [ep.to_raw_profile()])
    n2 = len(get_results(cid, uid)["entities"])
    assert n2 == n1, "re-ingesting the same account must not duplicate it"


# ---------- service task lifecycle (mocked engine + mocked ingest) ----------
def test_service_lifecycle_reaches_complete(monkeypatch):
    async def fake_run_task(self, tool_id, query, custom_url=None, custom_instruction=None, log_callback=None):
        return ExtractedProfilesResult(
            profiles=[ExtractedWebProfile(platform="instagram", username=query, value=query)])
    monkeypatch.setattr(AgenticBrowserEngine, "run_task", fake_run_task)
    monkeypatch.setattr(AgenticBrowserEngine, "live_available", lambda self: (True, "ok"))
    monkeypatch.setattr("backend.pipeline.orchestrator.ingest_external_profiles",
                        lambda cid, raws: {"added": len(raws), "clusters": 1})

    req = AgenticLookupRequest(case_id="c1", tool_id="socialsearcher", query="ash29_03")
    task = service.create_task(req)
    asyncio.run(service.run_agentic_task_background(task.task_id, req, False))
    t = service.get_task(task.task_id)
    assert t.status == "complete"
    assert t.entities_added == 1


def test_service_unavailable_sets_error_never_fabricates(monkeypatch):
    monkeypatch.setattr(AgenticBrowserEngine, "live_available",
                        lambda self: (False, "GEMINI_API_KEY not set"))
    req = AgenticLookupRequest(case_id="c2", tool_id="socialsearcher", query="x")
    task = service.create_task(req)
    asyncio.run(service.run_agentic_task_background(task.task_id, req, False))
    t = service.get_task(task.task_id)
    assert t.status == "error"
    assert t.extracted_profiles == []


def test_service_blocked_is_honest_not_error(monkeypatch):
    async def fake_run_task(self, *a, **k):
        return ExtractedProfilesResult(profiles=[], blocked=True, notes="Turnstile")
    monkeypatch.setattr(AgenticBrowserEngine, "run_task", fake_run_task)
    monkeypatch.setattr(AgenticBrowserEngine, "live_available", lambda self: (True, "ok"))
    req = AgenticLookupRequest(case_id="c3", tool_id="inflact", query="x")
    task = service.create_task(req)
    asyncio.run(service.run_agentic_task_background(task.task_id, req, False))
    t = service.get_task(task.task_id)
    assert t.status == "blocked"
    assert t.extracted_profiles == []


# ---------- API auth + ownership (real auth via fixtures) ----------
def test_tools_endpoint_requires_auth(client):
    assert client.get("/api/agentic-browser/tools").status_code in (401, 403)


def test_tools_endpoint_with_auth(client, auth_headers):
    headers, _ = auth_headers
    r = client.get("/api/agentic-browser/tools", headers=headers)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert "socialsearcher" in ids


def test_run_rejects_unowned_case(client, auth_headers):
    headers, _ = auth_headers
    r = client.post("/api/agentic-browser/run", headers=headers,
                    json={"case_id": "nonexistent-case", "tool_id": "socialsearcher", "query": "x"})
    assert r.status_code == 404
