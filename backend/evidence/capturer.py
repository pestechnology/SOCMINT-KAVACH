"""
backend/evidence/capturer.py — court-grade evidence capture (Phase 1).

OSINT sources are dynamic: a suspect can delete or edit a profile at any time, so a finding
you can't reproduce is a finding you can't rely on in court. This module captures a page AT
THE MOMENT OF VIEWING as a self-contained, hashed, externally-timestamped evidence bundle and
welds it into VERTEX's existing tamper-evident ledger — the bridge from "intel" to "evidence"
admissible under Bharatiya Sakshya Adhiniyam 2023 s.63 (successor to Evidence Act s.65B).

Per captured page we emit ONE bundle of up to four files, each hashed via save_artifact():
    1. MHTML   — the evidentiary anchor (self-contained, survives link-rot, re-hashes forever)
    2. PNG     — the human-facing "as-seen" full-page screenshot a judge reads with no tooling
    3. DOM     — post-JS outerHTML, searchable/diffable (proves later edits/deletes)
    4. metadata.json — final URL, HTTP status, capture UTC, tool/browser versions, actor, …
                       (the machine body of the s.63 "how it was produced" certificate)

The bundle's file hashes are rolled into a manifest; the manifest hash is appended to the
hash-chained audit_ledger AND anchored by a free RFC-3161 trusted timestamp (FreeTSA) so the
"when + unaltered" proof lives OUTSIDE the SQLite VERTEX controls — this defeats the
"the operator recomputed its own chain" attack. The external anchor is best-effort: if the TSA
is unreachable the bundle is still captured and sealed internally, flagged `anchored: false`.

Design invariants:
  - NEVER raises into the pipeline. A capture that fails is logged LOUD into the ledger
    ('evidence_capture_failed') — never silently skipped, or the officer trusts evidence that
    does not exist.
  - Secrets (cookies / Authorization / session tokens) are redacted BEFORE any byte is hashed
    or stored — authenticated captures must not persist a live session token.
  - The browser-driving half lives in agentic_browser.authed_browser.capture_bundle; this
    module is pure orchestration + hashing + timestamping and is unit-testable with a fake
    capture_fn (no live browser needed).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.request
import uuid

FREETSA_URL = "https://freetsa.org/tsr"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------------------
# Redaction — strip live secrets before anything is hashed/persisted.
# --------------------------------------------------------------------------------------
_REDACTIONS = (
    # Cookie / Set-Cookie / Authorization ANYWHERE (real header lines OR inline in body/JS,
    # incl. quoted-printable MHTML) — redact just the value TOKEN (bounded to non-space, so we
    # never gut the document). NOT line-anchored: an inline `Set-Cookie: s=…` must not slip by.
    re.compile(r"(?i)((?:set-)?(?:cookie|authorization)\s*[:=]\s*)(?:bearer\s+)?[^\s;,<>&]{4,}"),
    # token-ish key: value / key=value in JSON, query strings, inline script
    re.compile(r"(?i)((?:session(?:id)?|sid|auth|access[_-]?token|token|api[_-]?key|csrf|bearer)"
               r"\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]{8,}"),
    # inline "Bearer <token>" (space-separated, e.g. an Authorization value inside JS/JSON)
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._\-]{8,}"),
)
_REDACT_MARK = r"\1[REDACTED]"


def redact_secrets(content):
    """Redact cookies / Authorization / session tokens. Accepts str or bytes, returns same
    type. Conservative (line/keyword anchored) so it does not mangle page content."""
    is_bytes = isinstance(content, (bytes, bytearray))
    text = bytes(content).decode("latin-1") if is_bytes else str(content)
    for pat in _REDACTIONS:
        text = pat.sub(_REDACT_MARK, text)
    return text.encode("latin-1") if is_bytes else text


# --------------------------------------------------------------------------------------
# Merkle root — one external timestamp can seal many bundle hashes (per-case anchoring).
# --------------------------------------------------------------------------------------
def merkle_root(hashes: list[str]) -> str:
    """SHA-256 Merkle root over a list of hex digests. '' for empty; the value itself for one."""
    import hashlib
    level = [h for h in hashes if h]
    if not level:
        return ""
    if len(level) == 1:
        return level[0]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])  # duplicate the last (Bitcoin-style)
        level = [hashlib.sha256((level[i] + level[i + 1]).encode()).hexdigest()
                 for i in range(0, len(level), 2)]
    return level[0]


# --------------------------------------------------------------------------------------
# RFC-3161 trusted timestamp (FreeTSA, free, no key) — via asn1crypto (already installed).
# --------------------------------------------------------------------------------------
def _build_tsq(digest_hex: str) -> bytes:
    from asn1crypto import tsp, algos, core
    imprint = tsp.MessageImprint({
        "hash_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}),
        "hashed_message": bytes.fromhex(digest_hex),
    })
    req = tsp.TimeStampReq({
        "version": 1,
        "message_imprint": imprint,
        "nonce": core.Integer(int.from_bytes(os.urandom(8), "big")),
        "cert_req": True,
    })
    return req.dump()


def _http_post_tsq(tsa_url: str, tsq: bytes, timeout: int) -> bytes | None:
    req = urllib.request.Request(
        tsa_url, data=tsq,
        headers={"Content-Type": "application/timestamp-query",
                 "Accept": "application/timestamp-reply"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https TSA
        return resp.read()


def _token_from_response(resp_der: bytes) -> bytes | None:
    """Parse a TimeStampResp; return the TimeStampToken DER if status == granted, else None."""
    from asn1crypto import tsp
    resp = tsp.TimeStampResp.load(resp_der)
    status = resp["status"]["status"].native  # 'granted' / 'granted_with_mods' / …
    if status not in ("granted", "granted_with_mods"):
        return None
    token = resp["time_stamp_token"]
    return token.dump() if token else None


def request_timestamp(digest_hex: str, *, tsa_url: str = FREETSA_URL,
                      timeout: int = 8, post_fn=None) -> dict | None:
    """Best-effort RFC-3161 timestamp of a hex digest. Returns
    {tsr, token, tsa_url, digest} or None. NEVER raises (anchor is optional)."""
    try:
        tsq = _build_tsq(digest_hex)
    except Exception:  # noqa: BLE001
        return None
    try:
        resp_der = (post_fn or _http_post_tsq)(tsa_url, tsq, timeout)
        if not resp_der:
            return None
        token = _token_from_response(resp_der)
        if not token:
            return None
        return {"tsr": resp_der, "token": token, "tsa_url": tsa_url, "digest": digest_hex}
    except Exception:  # noqa: BLE001 — TSA down / offline / malformed reply → unanchored
        return None


def verify_timestamp(tsr_der: bytes, digest_hex: str) -> bool:
    """Best-effort check that a stored .tsr token stamps this exact digest. Never raises."""
    try:
        from asn1crypto import tsp, cms
        token = _token_from_response(tsr_der)
        if not token:
            return False
        content = cms.ContentInfo.load(token)["content"]["encap_content_info"]["content"]
        # asn1crypto decodes the TSTInfo content as a ParsableOctetString: `.parsed` IS the
        # TSTInfo (`.native` is an already-decoded dict, not the DER bytes TSTInfo.load wants).
        tst_info = content.parsed if hasattr(content, "parsed") else tsp.TSTInfo.load(content.native)
        return tst_info["message_imprint"]["hashed_message"].native == bytes.fromhex(digest_hex)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------------------
# Metadata — the machine body of the s.63 "how it was produced" certificate.
# --------------------------------------------------------------------------------------
def build_metadata(*, url: str, final_url: str, status, title: str, method: str,
                   actor: str, scroll_count, viewport, versions: dict,
                   artifacts: list[dict]) -> dict:
    return {
        "requested_url": url,
        "final_url": final_url,
        "http_status": status,
        "page_title": title,
        "capture_method": method,
        "captured_at_utc": _now(),
        "clock_source": "host system clock (advisory; authoritative time = RFC-3161 TSA token)",
        "actor": actor,
        "scroll_count": scroll_count,
        "viewport": viewport,
        "tool_versions": versions or {},
        "artifacts": [{"artifact_id": a.get("artifact_id"), "type": a.get("artifact_type"),
                       "sha256": a.get("sha256")} for a in artifacts],
        "note": "Capture reflects the page AS SEEN at captured_at_utc; live sources mutate, so "
                "this proves state-at-time and integrity since capture, not reproducibility.",
    }


# --------------------------------------------------------------------------------------
# Orchestration — capture one page into a sealed, anchored bundle.
# --------------------------------------------------------------------------------------
def capture_and_store(case_id: str, entity_id: str | None, url: str, *,
                      actor: str = "system", capture_fn=None, anchor: bool = True,
                      method: str = "automated_headless") -> dict:
    """Capture one page → 4-file bundle → hash each → manifest → ledger → external timestamp.
    Returns the manifest dict ({ok: True, ...}) or {ok: False, url, error}. Never raises."""
    from backend.ledger.audit_ledger import save_artifact, log_action, _sha256

    if capture_fn is None:
        from backend.agentic_browser.authed_browser import capture_bundle as capture_fn

    try:
        res = capture_fn(url)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if not isinstance(res, dict) or not res.get("ok"):
        err = (res.get("error") if isinstance(res, dict) else "capture returned no result")
        log_action(case_id, "evidence_capture_failed", {"url": url},
                   {"error": str(err)[:300]}, actor)   # FAIL LOUD
        return {"ok": False, "url": url, "error": str(err)[:300]}

    manifest_id = uuid.uuid4().hex
    title = str(res.get("title") or "")[:300]
    final_url = res.get("final_url") or url
    common = dict(source_url=url, capture_method=method, page_title=title, manifest_id=manifest_id)

    saved: list[dict] = []
    if res.get("mhtml"):
        saved.append(save_artifact(case_id, entity_id, "evidence_mhtml",
                                   redact_secrets(res["mhtml"]), ".mhtml",
                                   mime="multipart/related", **common))
    if res.get("png"):
        saved.append(save_artifact(case_id, entity_id, "evidence_screenshot",
                                   res["png"], ".png", mime="image/png", **common))
    if res.get("dom") is not None:
        saved.append(save_artifact(case_id, entity_id, "evidence_dom",
                                   redact_secrets(res["dom"]), ".html",
                                   mime="text/html", **common))

    meta = build_metadata(url=url, final_url=final_url, status=res.get("status"), title=title,
                          method=method, actor=actor, scroll_count=res.get("scroll_count"),
                          viewport=res.get("viewport"), versions=res.get("versions") or {},
                          artifacts=saved)
    saved.append(save_artifact(case_id, entity_id, "evidence_metadata",
                               json.dumps(meta, indent=2, default=str), ".json",
                               mime="application/json", **common))

    manifest = {
        "manifest_id": manifest_id, "url": url, "final_url": final_url,
        "entity_id": entity_id, "captured_at": _now(),
        "artifacts": [{"artifact_id": a["artifact_id"], "type": a["artifact_type"],
                       "sha256": a["sha256"]} for a in saved],
    }
    manifest["bundle_sha256"] = _sha256(manifest)

    anchored = False
    if anchor:
        tsr = request_timestamp(manifest["bundle_sha256"])
        if tsr and tsr.get("tsr"):
            tsr_art = save_artifact(case_id, entity_id, "evidence_tsr", tsr["tsr"], ".tsr",
                                    mime="application/timestamp-reply", source_url=url,
                                    capture_method=method, manifest_id=manifest_id)
            manifest.update(tsr_artifact_id=tsr_art["artifact_id"],
                            tsr_sha256=tsr_art["sha256"], tsa_url=tsr.get("tsa_url"))
            anchored = True
    manifest["anchored"] = anchored

    # Persist the machine-readable bundle record (bundle_sha256 + every file hash + tsr link)
    # as its own artifact so the evidence report can re-verify the external timestamp OFFLINE
    # (verify_timestamp needs the stamped digest, which is manifest["bundle_sha256"]).
    save_artifact(case_id, entity_id, "evidence_manifest",
                  json.dumps(manifest, indent=2, default=str), ".json",
                  mime="application/json", source_url=url, capture_method=method,
                  manifest_id=manifest_id)

    log_action(case_id, "evidence_bundle_captured", {"url": url}, manifest, actor)
    return {"ok": True, **manifest}


def capture_case_entities(case_id: str, entity_url_pairs, *, actor: str = "system",
                          max_pages: int = 25) -> list[dict]:
    """Capture every entity with an http(s) source_url, sequentially (concurrency 1 — avoids
    the shared-Chrome-profile lock). De-dupes URLs and caps count (cost bound); a cap hit is
    logged, never silent. Never raises."""
    from backend.ledger.audit_ledger import log_action
    seen: set[str] = set()
    results: list[dict] = []
    done = 0
    for eid, url in entity_url_pairs:
        u = str(url or "").strip()
        if not u.lower().startswith("http") or u in seen:
            continue
        seen.add(u)
        if done >= max_pages:
            log_action(case_id, "evidence_capture_capped",
                       {"cap": max_pages}, {"skipped_from": u}, actor)
            break
        try:
            results.append(capture_and_store(case_id, eid, u, actor=actor))
        except Exception as e:  # noqa: BLE001 — defensive; capture_and_store already guards
            log_action(case_id, "evidence_capture_failed", {"url": u},
                       {"error": str(e)[:200]}, actor)
        done += 1
    return results
