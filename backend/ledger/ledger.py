"""Audit ledger — immutable tamper-evident hash chain for investigation actions."""

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.database.db import get_connection

logger = logging.getLogger(__name__)

GENESIS_HASH: str = hashlib.sha256("VERTEX:GENESIS:2026".encode("utf-8")).hexdigest()


def _canonical_hash(data: dict) -> str:
    """Compute SHA-256 of canonical JSON (sort_keys=True, separators=(',', ':'))."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLedger:
    """Tamper-evident append-only audit ledger."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = settings.DB_PATH
        self.db_path = Path(db_path)

    def get_previous_hash(self, case_id: str) -> str:
        """Fetch the most recent ledger row's output_hash for this case; returns GENESIS_HASH if none."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT output_hash FROM audit_ledger WHERE case_id = ? "
                "ORDER BY timestamp DESC, rowid DESC LIMIT 1",
                (case_id,),
            )
            row = cursor.fetchone()
            if row and row["output_hash"]:
                return str(row["output_hash"])
            return GENESIS_HASH
        finally:
            conn.close()

    def record(
        self,
        case_id: str,
        action: str,
        input_data: dict,
        output_data: dict,
        actor: str = "Inspector Kumar",
    ) -> str:
        """Write an append-only ledger row and return the new row's hash (output_hash)."""
        previous_hash = self.get_previous_hash(case_id)
        input_hash = _canonical_hash(input_data)
        output_hash = _canonical_hash(output_data)

        ledger_id = f"LED-{uuid.uuid4().hex[:8]}"
        search_id = input_data.get("search_id")
        search_id_str = "" if search_id is None else str(search_id)
        ts = datetime.now(timezone.utc).isoformat()

        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO audit_ledger "
                "(ledger_id, case_id, action, search_id, input_hash, output_hash, previous_hash, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ledger_id,
                    case_id,
                    action,
                    search_id_str,
                    input_hash,
                    output_hash,
                    previous_hash,
                    actor,
                    ts,
                ),
            )
            conn.commit()
            logger.debug(
                "[ledger] recorded %s for case=%s (ledger_id=%s, hash=%s...)",
                action,
                case_id,
                ledger_id,
                output_hash[:16],
            )
        finally:
            conn.close()

        return output_hash

    def verify_chain(self, case_id: str) -> tuple[bool, str]:
        """Walk all rows for a case in timestamp order, verifying previous_hash links.

        Returns (True, "") if intact or (False, "broken at row X") if broken.
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT previous_hash, output_hash FROM audit_ledger WHERE case_id = ? "
                "ORDER BY timestamp ASC, rowid ASC",
                (case_id,),
            )
            rows = cursor.fetchall()
            expected_prev = GENESIS_HASH
            for idx, row in enumerate(rows, 1):
                if row["previous_hash"] != expected_prev:
                    logger.warning(
                        "[ledger] verification failed at row %d for case=%s (expected prev=%s..., got %s...)",
                        idx,
                        case_id,
                        expected_prev[:16],
                        str(row["previous_hash"])[:16],
                    )
                    return False, f"broken at row {idx}"
                expected_prev = row["output_hash"]
            return True, ""
        finally:
            conn.close()
