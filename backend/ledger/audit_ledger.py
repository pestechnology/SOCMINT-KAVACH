"""
backend/ledger/audit_ledger.py — the tamper-evident spine of the court story.

Public API:
    log_action(case_id, action, input_data, output_data, actor) -> ledger_id
    save_artifact(case_id, entity_id, artifact_type, content, suffix=".bin") -> dict
    verify_chain(case_id) -> (ok: bool, detail: str)
    get_ledger(case_id) -> list[dict]
    get_artifacts(case_id) -> list[dict]

Hash chain
----------
Each ledger row stores input_hash, output_hash and previous_hash. The chain value
for a row is:

    chain = SHA256(previous_hash + input_hash + output_hash + action + actor + timestamp)

previous_hash of row N is the chain value of row N-1 ("GENESIS" for the first row).
verify_chain walks the rows in insertion order and recomputes each link; if any
stored field was altered, a later row's previous_hash stops matching and the chain
fails. This is what lets a judge trust the manifest.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import uuid

from backend import config
from backend.database import get_db

GENESIS = "GENESIS"


def _sha256(data) -> str:
    if not isinstance(data, (bytes, bytearray)):
        data = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _chain_value(previous_hash: str, input_hash: str, output_hash: str,
                 action: str, actor: str, timestamp: str) -> str:
    return hashlib.sha256(
        f"{previous_hash}|{input_hash}|{output_hash}|{action}|{actor}|{timestamp}".encode()
    ).hexdigest()


def _last_chain_value(conn, case_id: str) -> str:
    """Recompute the chain value of the most recent row for this case."""
    row = conn.execute(
        "SELECT * FROM audit_ledger WHERE case_id = ? ORDER BY rowid DESC LIMIT 1",
        (case_id,),
    ).fetchone()
    if row is None:
        return GENESIS
    return _chain_value(row["previous_hash"], row["input_hash"], row["output_hash"],
                        row["action"], row["actor"], row["timestamp"])


def log_action(case_id: str, action: str, input_data=None, output_data=None,
               actor: str = "system") -> str:
    """Append a tamper-evident ledger row. Returns the ledger_id."""
    conn = get_db()
    try:
        ledger_id = uuid.uuid4().hex
        search_id = uuid.uuid4().hex
        timestamp = _now()
        input_hash = _sha256(input_data if input_data is not None else "")
        output_hash = _sha256(output_data if output_data is not None else "")
        previous_hash = _last_chain_value(conn, case_id)
        conn.execute(
            """INSERT INTO audit_ledger
               (ledger_id, case_id, action, search_id, input_hash, output_hash,
                previous_hash, actor, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (ledger_id, case_id, action, search_id, input_hash, output_hash,
             previous_hash, actor, timestamp),
        )
        conn.commit()
        return ledger_id
    finally:
        conn.close()


def save_artifact(case_id: str, entity_id: str | None, artifact_type: str,
                  content, suffix: str = ".bin") -> dict:
    """Persist an artifact to disk, hash it (SHA-256), record it. Returns the row dict."""
    os.makedirs(config.REPORT_OUTPUT_DIR, exist_ok=True)
    artifacts_dir = os.path.join(config.REPORT_OUTPUT_DIR, "artifacts", case_id)
    os.makedirs(artifacts_dir, exist_ok=True)

    if not isinstance(content, (bytes, bytearray)):
        content = str(content).encode()

    artifact_id = uuid.uuid4().hex
    file_path = os.path.join(artifacts_dir, f"{artifact_id}{suffix}")
    with open(file_path, "wb") as f:
        f.write(content)
    sha256 = _sha256(content)
    captured_at = _now()

    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO artifacts
               (artifact_id, case_id, entity_id, artifact_type, file_path, sha256, captured_at)
               VALUES (?,?,?,?,?,?,?)""",
            (artifact_id, case_id, entity_id, artifact_type, file_path, sha256, captured_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {"artifact_id": artifact_id, "file_path": file_path, "sha256": sha256,
            "artifact_type": artifact_type, "captured_at": captured_at}


def verify_chain(case_id: str) -> tuple[bool, str]:
    """Recompute the chain; return (True, "...") if intact, else (False, reason)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_ledger WHERE case_id = ? ORDER BY rowid ASC",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()

    prev = GENESIS
    for n, row in enumerate(rows):
        if row["previous_hash"] != prev:
            return False, (f"Chain broken at row {n} (action='{row['action']}'): "
                           f"stored previous_hash does not match recomputed chain.")
        prev = _chain_value(row["previous_hash"], row["input_hash"], row["output_hash"],
                            row["action"], row["actor"], row["timestamp"])
    return True, f"Chain intact across {len(rows)} ledger entries."


def get_ledger(case_id: str) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_ledger WHERE case_id = ? ORDER BY rowid ASC", (case_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_artifacts(case_id: str) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE case_id = ? ORDER BY rowid ASC", (case_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
