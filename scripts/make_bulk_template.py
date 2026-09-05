"""
scripts/make_bulk_template.py — regenerate the bulk-search templates.

    python -m scripts.make_bulk_template

Writes bulk_template.xlsx and bulk_template.csv into frontend/public/, which Next serves
as static files — so the "Download template" links in the bulk-upload screen point
straight at them and there is exactly ONE copy of each file in the repo.

Columns are exactly the identifiers VERTEX can search on. No field is required — fill in
what you have and leave the rest blank; one row per subject, and identifiers are never
merged across rows.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from backend.ingestion.bulk_subjects import _xlsx

ROOT = Path(__file__).resolve().parent.parent

HEADER = ["Name", "Phone", "Email", "Username", "UPI", "Profile URLs", "Photo URL"]

# Two worked examples, then blank rows to type into. The first shows several profile
# URLs in ONE cell (space- or comma-separated, any platform); the second shows that a
# single identifier with no name is a perfectly valid subject.
EXAMPLES = [
    ["Arjun Mehta", "9876543210", "arjun.mehta@example.com", "arjunm_92",
     "9876543210@ybl", "https://facebook.com/arjun.mehta https://instagram.com/arjunm_92",
     ""],
    ["", "9800011122", "", "", "", "", ""],
]
BLANK_ROWS = 8


def build() -> tuple[Path, Path]:
    rows = [HEADER] + EXAMPLES + [[""] * len(HEADER) for _ in range(BLANK_ROWS)]

    out_dir = ROOT / "frontend" / "public"
    out_dir.mkdir(parents=True, exist_ok=True)

    xlsx_path = out_dir / "bulk_template.xlsx"
    xlsx_path.write_bytes(_xlsx(rows))

    csv_path = out_dir / "bulk_template.csv"
    buf = io.StringIO(newline="")
    csv.writer(buf).writerows([HEADER] + EXAMPLES)   # blank rows are noise in a CSV
    csv_path.write_text(buf.getvalue(), encoding="utf-8-sig")   # BOM: Excel opens it as UTF-8

    return xlsx_path, csv_path


if __name__ == "__main__":
    for p in build():
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
