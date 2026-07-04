"""Tests for the deep-bio enhancement suite:
  - deterministic employer/school/city extraction (fact_enrich, LLM-down fallback)
  - bio_link_seeds following bio + blog/website links (generalised, not GitHub-only)
  - ingest_external_profiles MERGING a re-scrape into an existing entity (the
    "re-running changed nothing" fix)
  - compute_pivot_suggestions harvesting facts from discovered accounts
"""
import json
import uuid

from backend.auth.auth_service import register_user
from backend.cases.case_service import create_case, get_results
from backend.database import get_db
from backend.ingestion.base_module import make_profile
from backend.ingestion.fact_enrich import deterministic_facts
from backend.pipeline.orchestrator import (
    _merge_metadata, bio_link_seeds, compute_pivot_suggestions,
    ingest_external_profiles, run_investigation_sync,
)


def _new_user():
    return register_user("bio_" + uuid.uuid4().hex[:8], "secret123")


# ---- deterministic fact extraction ----

def test_deterministic_facts_extracts_school_and_city():
    f = deterministic_facts("Student at PES University. Based in Bengaluru.")
    assert "PES University" in f["employers"]
    assert "Bengaluru" in f["locations"]


def test_deterministic_facts_extracts_employer_and_acronym_institute():
    f = deterministic_facts("SDE @ Google | IIT Bombay grad")
    assert "Google" in f["employers"]
    assert "IIT Bombay" in f["employers"]


def test_deterministic_facts_does_not_cross_sentence_boundaries():
    f = deterministic_facts("Student at PES University. Based in Bengaluru. Loves ML.")
    assert "PES University" in f["employers"]
    assert all("Loves" not in e for e in f["employers"])
    assert all("Loves" not in l for l in f["locations"])


def test_deterministic_facts_ignores_bare_generic_words_and_noise():
    assert deterministic_facts("just a guy who codes") == {"employers": [], "locations": []}
    # "from X" is deliberately not a city cue (mis-fires on "photos from Ashwin")
    assert deterministic_facts("Photos from Ashwin at the beach")["locations"] == []


# ---- merge helper ----

def test_merge_metadata_fills_gaps_but_never_overwrites():
    existing = {"name": "Real Name", "bio": "", "employer_candidates": ["Acme"]}
    changed = _merge_metadata(existing, {"name": "Other", "bio": "hi",
                                         "employer_candidates": ["Acme", "Globex"], "city": "Blr"})
    assert changed
    assert existing["name"] == "Real Name"          # not overwritten
    assert existing["bio"] == "hi"                    # gap filled
    assert set(existing["employer_candidates"]) == {"Acme", "Globex"}  # unioned
    assert existing["city"] == "Blr"


def test_merge_metadata_no_change_returns_false():
    existing = {"name": "X", "bio": "y"}
    assert _merge_metadata(existing, {"name": "", "bio": "y"}) is False


# ---- generalised bio-link cascade ----

def test_bio_link_seeds_follows_blog_field():
    p = make_profile("social_account", "vismayhs", "github", "https://github.com/vismayhs",
                     metadata={"bio": "ML enthusiast", "blog": "https://twitter.com/vismay_hs"})
    seeds = bio_link_seeds([p], {"vismayhs"}, cap=5)
    assert any(s.value == "vismay_hs" and s.type == "username" for s in seeds)


def test_bio_link_seeds_skips_already_known_handles():
    p = make_profile("social_account", "a", "github", "u",
                     metadata={"blog": "https://twitter.com/known"})
    assert bio_link_seeds([p], {"a", "known"}, cap=5) == []


def test_bio_link_seeds_normalizes_scheme_less_blog():
    """GitHub often returns blog WITHOUT a scheme ('twitter.com/foo') — it must still
    be followed. A bare personal site ('danabra.mov') yields no social handle, no crash."""
    social = make_profile("social_account", "a", "github", "u",
                          metadata={"blog": "twitter.com/vismay_hs"})
    assert any(s.value == "vismay_hs" for s in bio_link_seeds([social], {"a"}, cap=5))
    personal = make_profile("social_account", "b", "github", "u",
                            metadata={"blog": "danabra.mov"})
    assert bio_link_seeds([personal], {"b"}, cap=5) == []


# ---- merge-on-reingest (the "nothing changed" fix) ----

def test_reingest_merges_enrichment_into_existing_entity():
    uid = _new_user()
    cid = create_case(uid, "Merge", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)

    # find an existing entity and re-ingest the SAME account (same sha256) but carrying a
    # newly-extracted employer the stored copy lacks.
    before = get_results(cid, uid)["entities"]
    target = before[0]
    reenriched = make_profile(
        target["type"], target["value"], target["platform"], target["source_url"] or "x",
        metadata={**target["metadata"], "employer_candidates": ["Newly Found Corp"]})
    # make_profile recomputes sha256 from value+platform+source_url — align source_url so it
    # collides with the stored entity, exercising the merge (not-insert) path.
    reenriched.sha256 = target["sha256"]

    res = ingest_external_profiles(cid, [reenriched])
    assert res["added"] == 0            # not a new account
    assert res["enriched"] >= 1         # merged instead of dropped

    after = {e["entity_id"]: e for e in get_results(cid, uid)["entities"]}
    assert len(after) == len(before)    # no duplicate entity created
    merged = after[target["entity_id"]]
    assert "Newly Found Corp" in (merged["metadata"].get("employer_candidates") or [])


# ---- harvested suggestions ----

def test_suggestions_harvest_bio_link_from_discovered_account():
    uid = _new_user()
    cid = create_case(uid, "Harvest", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)

    # stamp a blog link + distinct real name onto a discovered account, as a live
    # enrichment pass would, then confirm the suggest step surfaces them as new seeds.
    conn = get_db()
    try:
        row = conn.execute("SELECT entity_id, metadata_json FROM entities WHERE case_id=? AND value=?",
                           (cid, "vismayhs")).fetchone()
        md = json.loads(row["metadata_json"] or "{}")
        md["blog"] = "https://twitter.com/vismay_real"
        md["name"] = "Vismay Real Person"
        conn.execute("UPDATE entities SET metadata_json=? WHERE entity_id=?",
                     (json.dumps(md), row["entity_id"]))
        conn.commit()
    finally:
        conn.close()

    sugg = compute_pivot_suggestions([{"type": "username", "value": "vismayhs"}], case_id=cid)
    strategies = {s["strategy"] for s in sugg}
    assert "bio_link" in strategies
    assert any(s["value"] == "vismay_real" for s in sugg)
    assert any(s["strategy"] == "bio_name" and s["value"] == "Vismay Real Person" for s in sugg)


def test_suggestions_without_case_id_are_pure_derivations():
    sugg = compute_pivot_suggestions([{"type": "username", "value": "vismayhs"}])
    assert all("bio_" not in s["strategy"] for s in sugg)


# ---- reiteration count ----

def test_reiteration_count_starts_zero():
    uid = _new_user()
    cid = create_case(uid, "Count", [{"type": "username", "value": "vismayhs"}])
    run_investigation_sync(cid)
    assert get_results(cid, uid)["reiteration_count"] == 0
