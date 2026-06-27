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
