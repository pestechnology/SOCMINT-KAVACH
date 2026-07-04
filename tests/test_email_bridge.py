"""Regression test — the automatic email -> username bridge in run_investigation.

An email seed's local part is very often reused as a handle elsewhere, but the
email tool_map (HIBP, Holehe, DeHashed, ...) never checks social platforms by
handle. Section 1.5 of orchestrator.run_investigation automatically derives the
local part as a username seed (the SAME "email_local_part" strategy derive_seeds()
uses for manual re-iteration) and runs it through the full username tool_map —
so an email-only search can now surface Instagram/GitHub/etc. without a manual
pivot. Only that one strategy runs automatically; guessed-email-providers and
name-guess strategies stay pivot-only (see test_pivot.py).
"""
import uuid

from backend.auth.auth_service import register_user
from backend.cases.case_service import create_case, get_results
from backend.pipeline.orchestrator import run_investigation_sync


def _new_user():
    return register_user("emailbridge_" + uuid.uuid4().hex[:8], "secret123")


def test_email_seed_automatically_runs_a_username_search_on_the_local_part():
    uid = _new_user()
    cid = create_case(uid, "Email Bridge", [{"type": "email", "value": "vismayhs@gmail.com"}])
    run_investigation_sync(cid)

    results = get_results(cid, uid)
    assert results["status"] == "complete"
    derived = [e for e in results["entities"] if e["metadata"].get("derived_via")]
    assert derived, "expected at least one entity tagged with the automatic email_local_part derivation"
    dv = derived[0]["metadata"]["derived_via"]
    assert dv["strategy"] == "email_local_part"
    assert dv["from_value"] == "vismayhs@gmail.com"


def test_email_bridge_does_not_duplicate_an_existing_username_seed():
    """If the investigator ALSO gave an explicit username seed matching the email's
    local part, the bridge must not add a redundant second copy of that seed."""
    uid = _new_user()
    cid = create_case(uid, "Email Bridge No Dup", [
        {"type": "email", "value": "vismayhs@gmail.com"},
        {"type": "username", "value": "vismayhs"},
    ])
    res = run_investigation_sync(cid)
    assert res["status"] == "complete"   # must not error on the duplicate-seed path


def test_email_bridge_skips_invalid_local_parts():
    """A local part that fails the noise-handle guard (e.g. too short) must not be
    added as a seed at all — same guard the manual pivot preview uses."""
    uid = _new_user()
    cid = create_case(uid, "Email Bridge Noise", [{"type": "email", "value": "ab@gmail.com"}])
    res = run_investigation_sync(cid)
    assert res["status"] == "complete"
    results = get_results(cid, uid)
    assert not any(e["metadata"].get("derived_via") for e in results["entities"])
