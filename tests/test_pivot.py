"""Integration tests — re-iteration / identifier cross-pivoting end to end
(backend/ingestion/derive.py + backend/pipeline/orchestrator.py's run_pivot_seeds).

Mirrors test_report_and_pipeline.py's style: call the orchestrator functions
directly (not through the HTTP layer) for a fast, deterministic pipeline test.

The interaction model is multi-select: the investigator checks one or more
already-discovered accounts (and/or suggestions, and/or manually-typed values)
and runs ONE combined pivot on all of them at once — repeatable, since after it
completes they can select a new batch from the larger result set.
"""
import json
import uuid

from backend.auth.auth_service import register_user
from backend.cases.case_service import create_case, get_results
from backend.database import get_db
from backend.pipeline.orchestrator import (
    compute_pivot_suggestions, run_investigation_sync, run_pivot_seeds_sync,
)


def _new_user():
    return register_user("pivot_" + uuid.uuid4().hex[:8], "secret123")


# ---- compute_pivot_suggestions (pure, no scraping) ----

def test_suggestions_merge_across_multiple_inputs_and_dedupe():
    suggestions = compute_pivot_suggestions([
        {"type": "username", "value": "vismayhs"},
        {"type": "email", "value": "vismayhs@gmail.com"},
    ])
    # both inputs derive the SAME "vismayhs" username-local-part / handle-variant
    # candidates — must appear once each, not duplicated per input.
    values_seen = [ (s["type"], s["value"].lower()) for s in suggestions ]
    assert len(values_seen) == len(set(values_seen))
    assert any(s["type"] == "email" and "vismayhs@" in s["value"] for s in suggestions)


def test_suggestions_never_reintroduce_an_input_value():
    suggestions = compute_pivot_suggestions([{"type": "username", "value": "vismayhs"}])
    assert not any(s["value"].strip().lower() == "vismayhs" for s in suggestions)


def test_suggestions_tag_provenance_from_value():
    suggestions = compute_pivot_suggestions([{"type": "username", "value": "vismayhs"}])
    assert all(s["from_value"] == "vismayhs" for s in suggestions)


def test_suggestions_empty_for_empty_input():
    assert compute_pivot_suggestions([]) == []


# ---- run_pivot_seeds / run_pivot_seeds_sync (integration) ----

def test_pivot_seeds_adds_profiles_and_recorrelates():
    uid = _new_user()
    cid = create_case(uid, "Pivot E2E", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    n_before = len(get_results(cid, uid)["entities"])

    suggestions = compute_pivot_suggestions([{"type": "username", "value": "vismayhs"}])
    res = run_pivot_seeds_sync(cid, suggestions)
    assert res["status"] == "complete"
    assert res["seeds"] == len(suggestions) > 0

    after = get_results(cid, uid)
    assert len(after["entities"]) > n_before
    assert any(e["metadata"].get("derived_via") for e in after["entities"])


def test_pivot_seeds_combines_multiple_selected_identifiers_in_one_run():
    """The core multi-select behavior: checking several things at once (an existing
    account re-selected AS a seed, plus a manually-typed identifier) runs as ONE
    combined pivot, not one at a time."""
    uid = _new_user()
    cid = create_case(uid, "Pivot Multi", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)

    combined_seeds = [
        {"type": "username", "value": "vismayhs", "strategy": "existing_account"},
        {"type": "name", "value": "Manually Typed Name", "strategy": "manual"},
    ]
    res = run_pivot_seeds_sync(cid, combined_seeds)
    assert res["status"] == "complete"
    assert res["seeds"] == 2

    after = get_results(cid, uid)
    manual_entities = [e for e in after["entities"]
                      if e["metadata"].get("derived_via", {}).get("from_value") == "Manually Typed Name"]
    assert manual_entities
    assert manual_entities[0]["metadata"]["derived_via"]["strategy"] == "manual"


def test_pivot_is_repeatable():
    """After a pivot completes, running ANOTHER pivot on a new selection must also
    succeed and keep growing/re-correlating the same case — this is what re-iteration
    means: select, run, select again from the bigger set, run again."""
    uid = _new_user()
    cid = create_case(uid, "Pivot Repeat", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)

    res1 = run_pivot_seeds_sync(cid, [{"type": "username", "value": "vismayhs"}])
    assert res1["status"] == "complete"
    n_after_first = len(get_results(cid, uid)["entities"])

    res2 = run_pivot_seeds_sync(cid, [{"type": "name", "value": "Second Round Name"}])
    assert res2["status"] == "complete"
    n_after_second = len(get_results(cid, uid)["entities"])
    assert n_after_second >= n_after_first


def test_pivot_seeds_appends_to_case_seeds_json():
    uid = _new_user()
    cid = create_case(uid, "Pivot Seeds JSON", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    run_pivot_seeds_sync(cid, [{"type": "email", "value": "vismayhs@gmail.com"}])

    conn = get_db()
    try:
        row = conn.execute("SELECT seeds_json FROM cases WHERE case_id=?", (cid,)).fetchone()
    finally:
        conn.close()
    seeds = json.loads(row["seeds_json"])
    assert len(seeds) > 1


def test_pivot_seeds_empty_list_is_a_safe_noop():
    uid = _new_user()
    cid = create_case(uid, "Pivot Empty", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    n_before = len(get_results(cid, uid)["entities"])

    res = run_pivot_seeds_sync(cid, [])
    assert res["status"] == "complete"
    assert res["seeds"] == 0
    assert len(get_results(cid, uid)["entities"]) == n_before


def test_pivot_seeds_ignores_malformed_entries():
    uid = _new_user()
    cid = create_case(uid, "Pivot Malformed", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    res = run_pivot_seeds_sync(cid, [{"type": "username"}, {"value": "no-type"}, {}])
    assert res["status"] == "complete"
    assert res["seeds"] == 0


def test_pivot_on_unknown_case_id_does_not_raise():
    res = run_pivot_seeds_sync("nonexistent-case-id", [{"type": "username", "value": "vismayhs"}])
    assert res["status"] in ("complete", "error")


# ---- "face" seeds (profile pictures dragged in from the Summary tab) ----

def test_pivot_face_seed_is_a_noop_in_mock_mode():
    """build_face_seed_profile() has no mock-mode branch of its own (it always does a
    real HTTP fetch) — _scrape_pivot_seed must gate it behind DATA_MODE=="live" itself,
    or a mock-mode pivot (e.g. this very test) would fire a real network request."""
    uid = _new_user()
    cid = create_case(uid, "Pivot Face", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    res = run_pivot_seeds_sync(cid, [{"type": "face", "value": "https://example.com/photo.jpg"}])
    assert res["status"] == "complete"
    assert res["seeds"] == 1
    assert res["added"] == 0   # no network call made; nothing to add
