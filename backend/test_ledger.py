"""Standalone audit ledger test — run with: python -m backend.test_ledger"""

import asyncio
import logging
import sys

from backend.config import settings
from backend.database.db import get_connection, init_db
from backend.ledger.ledger import AuditLedger
from backend.main import InvestigateRequest, investigate

logging.basicConfig(level="DEBUG", format="%(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


async def run_test() -> None:
    print("\n" + "=" * 70)
    print("VERTEX Audit Ledger & Tamper-Evident Hash Chain Test")
    print("=" * 70)

    # Reset DB
    init_db(settings.DB_PATH)

    # Call /investigate 3 times with the same identifier
    req = InvestigateRequest(type="username", value="octocat")
    case_id = "case_username_octocat"

    print("\n--- Running 3 investigations ---")
    for i in range(1, 4):
        print(f"  Investigation {i}...")
        res = await investigate(req)
        print(f"    Status: {res.status}, Profiles: {res.profile_count}, Clusters: {res.cluster_count}")

    ledger = AuditLedger()

    # 1. Verify intact chain
    print("\n--- Verifying Chain (Expect Intact) ---")
    intact, reason = ledger.verify_chain(case_id)
    if not intact:
        print(f"  ✗ FAIL: Chain verification failed unexpectedly: {reason}")
        sys.exit(1)
    print('  ✓ Chain intact: (True, "")')

    # Inspect DB rows
    conn = get_connection(settings.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT ledger_id, action, substr(input_hash, 1, 16) AS in_h, "
            "substr(output_hash, 1, 16) AS out_h, substr(previous_hash, 1, 16) AS prev_h "
            "FROM audit_ledger ORDER BY timestamp ASC, rowid ASC"
        ).fetchall()
        print(f"\nLedger rows in DB ({len(rows)}):")
        for idx, r in enumerate(rows, 1):
            print(f"  Row {idx} ({r['action']}): prev={r['prev_h']}... out={r['out_h']}...")

        if len(rows) != 6:
            print(f"  ✗ FAIL: Expected 6 ledger rows, got {len(rows)}")
            sys.exit(1)

        # 2. Tamper with Row 2
        print("\n--- Tampering with Row 2 ---")
        row_to_tamper = rows[1]["ledger_id"]  # row index 1 is Row 2
        orig_hash_row = conn.execute(
            "SELECT output_hash FROM audit_ledger WHERE ledger_id = ?",
            (row_to_tamper,),
        ).fetchone()
        orig_hash = orig_hash_row["output_hash"]

        conn.execute(
            "UPDATE audit_ledger SET output_hash = 'tampered' WHERE ledger_id = ?",
            (row_to_tamper,),
        )
        conn.commit()
        print("  Row 2 output_hash changed to 'tampered'")
    finally:
        conn.close()

    # Verify broken chain
    print("\n--- Verifying Chain (Expect Broken) ---")
    intact, reason = ledger.verify_chain(case_id)
    if intact:
        print("  ✗ FAIL: Chain verification passed despite tampering!")
        sys.exit(1)
    print(f'  ✓ Tampering detected: (False, "{reason}")')
    if "broken at row 3" not in reason:
        print(f"  ✗ FAIL: Expected reason to indicate broken at row 3, got '{reason}'")
        sys.exit(1)

    # 3. Restore Row 2
    print("\n--- Restoring Row 2 ---")
    conn = get_connection(settings.DB_PATH)
    try:
        conn.execute(
            "UPDATE audit_ledger SET output_hash = ? WHERE ledger_id = ?",
            (orig_hash, row_to_tamper),
        )
        conn.commit()
        print("  Row 2 output_hash restored")
    finally:
        conn.close()

    # Verify chain restored
    print("\n--- Verifying Chain (Expect Restored) ---")
    intact, reason = ledger.verify_chain(case_id)
    if not intact:
        print(f"  ✗ FAIL: Chain verification failed after restore: {reason}")
        sys.exit(1)
    print('  ✓ Chain intact again: (True, "")')

    print("\n" + "=" * 70)
    print("  ALL ASSERTIONS PASSED ✅")
    print("=" * 70)


def main() -> None:
    asyncio.run(run_test())


if __name__ == "__main__":
    main()
