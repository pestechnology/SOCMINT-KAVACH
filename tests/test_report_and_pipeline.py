"""Integration tests — orchestrator, report generation, and the XSS/special-char regression."""
import asyncio
import hashlib
import os
import uuid

from backend.auth.auth_service import register_user
from backend.cases.case_service import create_case, get_results, list_cases
from backend.ledger.audit_ledger import get_artifacts
from backend.pipeline.orchestrator import run_investigation_sync
from backend.report.bsa63_generator import generate_report


def _new_user():
    return register_user("rep_" + uuid.uuid4().hex[:8], "secret123")


def test_orchestrator_end_to_end():
    uid = _new_user()
    cid = create_case(uid, "E2E", [{"type": "username", "value": "arjun"}])
    res = run_investigation_sync(cid)
    assert res["status"] == "complete"
    r = get_results(cid, uid)
    assert len(r["entities"]) >= 3
    assert any(c["tier"] == "HIGH" for c in r["clusters"])


def test_orchestrator_idempotent():
    """REGRESSION: re-running an investigation must not duplicate entities."""
    uid = _new_user()
    cid = create_case(uid, "Idem", [{"type": "username", "value": "arjun"}])
    run_investigation_sync(cid)
    n1 = len(get_results(cid, uid)["entities"])
    run_investigation_sync(cid)
    n2 = len(get_results(cid, uid)["entities"])
    assert n1 == n2


def test_report_generates_and_hash_matches():
    uid = _new_user()
    cid = create_case(uid, "Report", [{"type": "username", "value": "arjun"}])
    run_investigation_sync(cid)
    pdf = generate_report(cid)
    assert os.path.getsize(pdf) > 2000
    art = get_artifacts(cid)[0]
    with open(art["file_path"], "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == art["sha256"]


def test_report_survives_xml_special_chars():
    """REGRESSION: '&' / '<' in title or seed must not crash PDF generation."""
    uid = _new_user()
    cid = create_case(uid, 'Tom & Jerry <b>x</b> "q"',
                      [{"type": "name", "value": "A & B <script>alert(1)</script>"}])
    run_investigation_sync(cid)
    pdf = generate_report(cid)  # must not raise
    assert os.path.getsize(pdf) > 2000


def test_report_redaction_for_minor():
    uid = _new_user()
    cid = create_case(uid, "Minor case", [{"type": "username", "value": "arjun"}], minor_involved=True)
    run_investigation_sync(cid)
    pdf = generate_report(cid)
    assert os.path.exists(pdf)  # generates with redaction path active


def test_upi_cascade_identifies_bank():
    uid = _new_user()
    cid = create_case(uid, "UPI", [{"type": "upi", "value": "arjun.trades@oksbi"}])
    run_investigation_sync(cid)
    r = get_results(cid, uid)
    upi = [e for e in r["entities"] if e["type"] == "upi"]
    assert upi and "State Bank of India" in (upi[0]["metadata"].get("note") or "")


def test_list_cases_account_count():
    """REGRESSION: list_cases returns account_count via single query (was N+1)."""
    uid = _new_user()
    cid = create_case(uid, "Counted", [{"type": "username", "value": "arjun"}])
    run_investigation_sync(cid)
    rows = [c for c in list_cases(uid) if c["case_id"] == cid]
    assert rows and rows[0]["account_count"] >= 3


def test_ban_username_equals_name_double_counting():
    """NSA-Grade: Ensure name == username does not trigger exact_name_match."""
    from backend.correlation.correlation_engine import _pair_signals
    from backend.ingestion.base_module import RawProfile

    p1 = RawProfile(type="social_account", value="a03", platform="aparat", source_url="", metadata={"name": "a03"})
    p2 = RawProfile(type="social_account", value="a03_alt", platform="dailymotion", source_url="", metadata={"name": "a03"})
    signals = _pair_signals(p1, p2)
    assert "exact_name_match" not in signals
    assert "fuzzy_name_match" not in signals


def test_hard_anchor_cap():
    """NSA-Grade: Ensure clusters without a Hard Anchor are capped at 65 score / MEDIUM tier."""
    from backend.correlation.correlation_engine import CandidatePair
    from backend.ingestion.base_module import RawProfile
    from backend.scoring.scoring_engine import score

    p1 = RawProfile(type="social_account", value="ash29_03", platform="instagram", source_url="", metadata={})
    p2 = RawProfile(type="social_account", value="ash29_03", platform="github", source_url="", metadata={})
    pair = CandidatePair(
        i=0, j=1,
        signals={"username_exact_match": 45, "posting_hours_overlap": 20, "stylometry_cosine": 20}
    )
    clusters = score([p1, p2], [pair])
    assert len(clusters) == 1
    assert clusters[0].confidence_score <= 65.0
    assert clusters[0].tier == "MEDIUM"


def test_legitimate_and_target_country_filter():
    """NSA-Grade: Ensure explicit foreign locations are filtered out while Indian and non-social records are preserved."""
    from backend.ingestion.base_module import RawProfile
    from backend.pipeline.orchestrator import _is_legitimate_and_target_country

    p_foreign = RawProfile(type="social_account", value="ash29", platform="instagram", source_url="", metadata={"location": "New York, USA"})
    p_india = RawProfile(type="social_account", value="ash29", platform="instagram", source_url="", metadata={"location": "Bangalore, India"})
    p_upi = RawProfile(type="upi", value="ash@oksbi", platform="upi", source_url="", metadata={"location": "USA"})  # non-social record bypasses filter

    assert not _is_legitimate_and_target_country(p_foreign)
    assert _is_legitimate_and_target_country(p_india)
    assert _is_legitimate_and_target_country(p_upi)


def test_exact_seed_ranked_first_and_linked_high():
    """NSA-Grade: Ensure exact seed accounts are grouped into Cluster #1 with 100 confidence."""
    from backend.correlation.correlation_engine import CandidatePair
    from backend.ingestion.base_module import RawProfile
    from backend.scoring.scoring_engine import score

    p1 = RawProfile(type="social_account", value="ash2903", platform="instagram", source_url="", metadata={"username": "ash2903"})
    p2 = RawProfile(type="social_account", value="ash2903", platform="github", source_url="", metadata={"username": "ash2903"})
    p_other = RawProfile(type="social_account", value="random_guy", platform="medium", source_url="", metadata={"username": "random_guy"})
    pair = CandidatePair(i=0, j=1, signals={"username_exact_match": 45})
    
    clusters = score([p1, p2, p_other], [pair], seeds=[{"type": "username", "value": "ash29_03"}])
    assert len(clusters) >= 1
    # Cluster #1 must be our exact seed matches with 100 confidence
    assert 0 in clusters[0].member_indices and 1 in clusters[0].member_indices
    assert clusters[0].confidence_score == 100.0
    assert clusters[0].tier == "HIGH"


