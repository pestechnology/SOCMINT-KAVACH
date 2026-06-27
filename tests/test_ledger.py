"""Unit/integration tests — audit ledger hash chain + artifact hashing."""
import hashlib
import uuid

from backend.database import get_db
from backend.ledger.audit_ledger import (
    get_artifacts, get_ledger, log_action, save_artifact, verify_chain,
)


def _fresh_case():
    return "ledgertest_" + uuid.uuid4().hex[:8]


def test_chain_intact():
    cid = _fresh_case()
    log_action(cid, "start", {"a": 1}, None, "officer")
    log_action(cid, "scrape", {"q": "x"}, {"n": 3}, "system")
    ok, detail = verify_chain(cid)
    assert ok is True
    assert "intact" in detail.lower()


def test_tamper_detected():
    """REGRESSION: editing a recorded hash must break the chain."""
    cid = _fresh_case()
    log_action(cid, "a", {"x": 1}, None, "s")
    log_action(cid, "b", {"x": 2}, None, "s")
    log_action(cid, "c", {"x": 3}, None, "s")
    assert verify_chain(cid)[0] is True
    conn = get_db()
    conn.execute("UPDATE audit_ledger SET input_hash='TAMPERED' WHERE case_id=? AND action='b'", (cid,))
    conn.commit(); conn.close()
    ok, detail = verify_chain(cid)
    assert ok is False
    assert "broken" in detail.lower()


def test_artifact_hash_matches_file():
    cid = _fresh_case()
    art = save_artifact(cid, None, "json_dump", '{"k":"v"}', suffix=".json")
    with open(art["file_path"], "rb") as f:
        independent = hashlib.sha256(f.read()).hexdigest()
    assert independent == art["sha256"]


def test_empty_case_chain_ok():
    ok, _ = verify_chain("nonexistent_" + uuid.uuid4().hex)
    assert ok is True  # zero entries = trivially intact


def test_ledger_ordering():
    cid = _fresh_case()
    for i in range(5):
        log_action(cid, f"step{i}", {"i": i}, None, "s")
    rows = get_ledger(cid)
    assert [r["action"] for r in rows] == [f"step{i}" for i in range(5)]
    assert rows[0]["previous_hash"] == "GENESIS"
