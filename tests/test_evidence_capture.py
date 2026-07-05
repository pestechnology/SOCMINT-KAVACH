"""Tests for Phase-1 court-grade evidence capture (backend/evidence/capturer.py).

Covers the pure logic (redaction, Merkle root, RFC-3161 request builder) and the full
capture→hash→ledger→manifest flow using a FAKE capture_fn (no live browser, no network),
against a throwaway SQLite DB. The external-timestamp anchor is exercised via an injected
post_fn so no real TSA call is made.
"""
import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from backend import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    from backend.database import init_db, get_db
    init_db()
    conn = get_db()
    conn.execute("INSERT INTO users (user_id, username, password_hash) VALUES ('u1','off','x')")
    conn.execute("INSERT INTO cases (case_id,user_id,title,seeds_json,status,capture_evidence,"
                 "created_at,updated_at) VALUES ('c1','u1','t','[]','complete',1,'now','now')")
    conn.commit()
    conn.close()
    return "c1"


def _real_png() -> bytes:
    """A genuine tiny PNG so the evidence-report embed path is exercised for real."""
    from io import BytesIO
    from PIL import Image as _PILImage
    buf = BytesIO()
    _PILImage.new("RGB", (6, 6), (180, 20, 40)).save(buf, "PNG")
    return buf.getvalue()


def _fake_capture(url):
    return {"ok": True, "title": "Suspect Profile", "final_url": url, "status": 200,
            "dom": "<html>bio Authorization: Bearer LEAKME123456</html>",
            "png": _real_png(),
            "mhtml": b"From: <snapshot>\nCookie: sess=LEAKME999999\n\nbody",
            "scroll_count": 3, "versions": {"engine": "patchright"}}


# ── pure logic ──
def test_redaction_strips_secrets_keeps_content():
    from backend.evidence.capturer import redact_secrets
    r = redact_secrets("Cookie: sid=SECRETVALUE123\nAuthorization: Bearer abcdef123456\n"
                       "hello token=ZZZZZZZZ99 world")
    assert "SECRETVALUE123" not in r and "abcdef123456" not in r and "ZZZZZZZZ99" not in r
    assert "hello" in r and "world" in r  # non-secret content preserved


def test_redaction_handles_bytes_and_inline_bearer():
    from backend.evidence.capturer import redact_secrets
    rb = redact_secrets(b"Set-Cookie: x=YYYYYYYY12345\nvisible-body")
    assert isinstance(rb, (bytes, bytearray))
    assert b"YYYYYYYY12345" not in rb and b"visible-body" in rb
    assert "LEAKME123456" not in redact_secrets("x Authorization: Bearer LEAKME123456 y")


def test_redaction_catches_inline_nonkeyword_cookie():
    # Regression: an inline `Set-Cookie: s=…` (non-keyword cookie name, embedded in body/JS,
    # NOT a line-anchored header) must still be redacted — a live-capture probe caught this
    # leaking into the stored MHTML because the old pattern was line-anchored.
    from backend.evidence.capturer import redact_secrets
    out = redact_secrets("<div>Set-Cookie: s=LEAK_XYZ_123456</div>")
    assert "LEAK_XYZ_123456" not in out
    assert "<div>" in out and "</div>" in out  # surrounding markup preserved
    # quoted-printable MHTML form ('=' encoded as '=3D')
    assert "LEAK_XYZ_123456" not in redact_secrets("Set-Cookie: s=3DLEAK_XYZ_123456")


def test_merkle_root():
    from backend.evidence.capturer import merkle_root
    assert merkle_root([]) == ""
    assert merkle_root(["aa"]) == "aa"
    assert len(merkle_root(["aa", "bb", "cc"])) == 64
    # stable / deterministic
    assert merkle_root(["11", "22"]) == merkle_root(["11", "22"])


def test_rfc3161_request_builder_and_graceful_failure():
    from backend.evidence.capturer import _build_tsq, request_timestamp
    assert isinstance(_build_tsq("de" * 32), bytes) and len(_build_tsq("de" * 32)) > 10
    # TSA unreachable / returns nothing / raises → None, never an exception
    assert request_timestamp("aa" * 32, post_fn=lambda u, q, t: None) is None
    assert request_timestamp("aa" * 32, post_fn=lambda u, q, t: (_ for _ in ()).throw(OSError())) is None


def test_verify_timestamp_rejects_garbage():
    from backend.evidence.capturer import verify_timestamp
    assert verify_timestamp(b"not-a-token", "ab" * 32) is False
    assert verify_timestamp(b"", "ab" * 32) is False


def test_verify_timestamp_roundtrip_live():
    """When FreeTSA is reachable, a token verifies against its digest and rejects a wrong one.
    Skips cleanly offline so CI stays deterministic."""
    import hashlib
    from backend.evidence.capturer import request_timestamp, verify_timestamp
    digest = hashlib.sha256(b"vertex-test").hexdigest()
    tok = request_timestamp(digest, timeout=10)
    if not tok:
        pytest.skip("FreeTSA unreachable (offline)")
    assert verify_timestamp(tok["tsr"], digest) is True
    assert verify_timestamp(tok["tsr"], "ff" * 32) is False


# ── full flow ──
def test_capture_and_store_bundle(db):
    from backend.evidence.capturer import capture_and_store
    from backend.ledger.audit_ledger import get_artifacts, get_ledger, verify_chain

    res = capture_and_store(db, "e1", "https://instagram.com/suspect",
                            capture_fn=_fake_capture, anchor=False, actor="officer1")
    assert res["ok"] and res["anchored"] is False
    assert res["bundle_sha256"] and len(res["artifacts"]) == 4  # mhtml+png+dom+metadata

    arts = get_artifacts(db)
    # the 4 hashed exhibit files + the persisted manifest record (anchor off → no tsr)
    assert sorted(a["artifact_type"] for a in arts) == [
        "evidence_dom", "evidence_manifest", "evidence_metadata", "evidence_mhtml",
        "evidence_screenshot"]
    # provenance columns populated + one shared manifest_id
    mids = {a["manifest_id"] for a in arts}
    assert len(mids) == 1 and None not in mids
    mh = next(a for a in arts if a["artifact_type"] == "evidence_mhtml")
    assert mh["source_url"] == "https://instagram.com/suspect"
    assert mh["capture_method"] == "automated_headless"

    # secrets never hit disk
    dom_file = next(a for a in arts if a["artifact_type"] == "evidence_dom")["file_path"]
    assert b"LEAKME123456" not in Path(dom_file).read_bytes()
    assert b"LEAKME999999" not in Path(mh["file_path"]).read_bytes()

    # manifest welded into the tamper-evident chain, chain intact
    assert any(l["action"] == "evidence_bundle_captured" for l in get_ledger(db))
    ok, _ = verify_chain(db)
    assert ok


def test_capture_failure_is_logged_loud_not_silent(db):
    from backend.evidence.capturer import capture_and_store
    from backend.ledger.audit_ledger import get_ledger, get_artifacts
    res = capture_and_store(db, "e2", "https://x.com/y",
                            capture_fn=lambda u: {"ok": False, "error": "blank page"}, anchor=False)
    assert res["ok"] is False and res["error"] == "blank page"
    assert any(l["action"] == "evidence_capture_failed" for l in get_ledger(db))
    assert get_artifacts(db) == []  # nothing stored on failure


def test_capture_anchor_stores_tsr_when_tsa_responds(db, monkeypatch):
    # Inject a fake TSA that returns a granted response so the anchor path runs end-to-end.
    import backend.evidence.capturer as C

    def fake_request_timestamp(digest_hex, **kw):
        return {"tsr": b"FAKE-TSR-TOKEN-BYTES", "token": b"tok", "tsa_url": "https://freetsa.org/tsr",
                "digest": digest_hex}
    monkeypatch.setattr(C, "request_timestamp", fake_request_timestamp)

    res = C.capture_and_store(db, "e3", "https://t.me/x", capture_fn=_fake_capture, anchor=True)
    assert res["ok"] and res["anchored"] is True and res.get("tsr_artifact_id")
    from backend.ledger.audit_ledger import get_artifacts
    assert any(a["artifact_type"] == "evidence_tsr" for a in get_artifacts(db))


def test_evidence_report_pdf_generates_with_exhibit(db, tmp_path):
    # Capture a bundle (fake browser, no network), then render the dedicated exhibit PDF.
    from backend.evidence.capturer import capture_and_store
    from backend.report.evidence_report import generate_evidence_report, _bundles
    capture_and_store(db, "e1", "https://instagram.com/suspect",
                      capture_fn=_fake_capture, anchor=False)
    bundles, orphans = _bundles(db)
    assert len(bundles) == 1 and orphans == 0
    assert bundles[0]["source_url"] == "https://instagram.com/suspect"
    out = generate_evidence_report(db, output_path=str(tmp_path / "ev.pdf"))
    data = Path(out).read_bytes()
    assert data[:4] == b"%PDF" and len(data) > 1500  # a real, non-empty PDF


def test_evidence_report_pdf_when_no_exhibits(db, tmp_path):
    # No capture on this case → a valid PDF stating none were captured (never crashes).
    from backend.report.evidence_report import generate_evidence_report
    out = generate_evidence_report(db, output_path=str(tmp_path / "empty.pdf"))
    assert Path(out).read_bytes()[:4] == b"%PDF"


def test_capture_case_entities_dedupes_skips_nonhttp_and_caps(db, monkeypatch):
    import backend.evidence.capturer as C
    calls = []
    monkeypatch.setattr(C, "capture_and_store",
                        lambda cid, eid, url, **k: (calls.append(url) or {"ok": True}))
    C.capture_case_entities(db, [("e1", "https://a.com"), ("e2", "https://a.com"),
                                 ("e3", "ftp://nope"), ("e4", ""), ("e5", None)])
    assert calls == ["https://a.com"]  # deduped; non-http and empty skipped

    calls.clear()
    C.capture_case_entities(db, [("e%d" % i, "https://s%d.com" % i) for i in range(30)], max_pages=5)
    assert len(calls) == 5  # cost cap honored
