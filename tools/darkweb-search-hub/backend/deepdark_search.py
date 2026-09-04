"""
deepdark_search.py — keyword search over the cloned deepdarkCTI curated list
(github.com/fastfire/deepdarkCTI). Not a live query: this is a static list of known
dark-web forums/marketplaces/leak-sites/Telegram channels, refreshed by re-cloning the
repo (see refresh_deepdarkcti() below) rather than queried live.

Each category .md file is mostly a markdown table: `|[Name](url)|STATUS|...|`.
We parse `[name](url)` links off each line and keep the raw line for status/context.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent / "deepdarkCTI"

# Category files use two different pipe-table styles:
#   |[Name](url)|STATUS|...|          (most files)
#   |url|STATUS|Name|Type|            (e.g. telegram_threat_actors.md)
# so rows are parsed cell-by-cell rather than with one whole-line regex.
_CELL_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)$")
_URL_RE = re.compile(r"^(https?://\S+|[a-z0-9.-]+\.onion\S*)$", re.IGNORECASE)
_STATUS_WORDS = {"ONLINE", "OFFLINE", "UNKNOWN", "EXPIRED", "DOWN", "SEIZED"}

_SKIP_FILES = {"README.md", "methods.md", "LICENSE"}


def _parse_table_row(line: str):
    """Parse one markdown table row into {name, url, status}, or None if the
    line isn't a data row (header/separator/non-table line)."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    if not cells or all(set(c) <= set("-: ") for c in cells):
        return None  # separator row like |------|------|

    name = None
    url = None
    status = "UNKNOWN"
    extra = []
    for cell in cells:
        if not cell:
            continue
        m = _CELL_LINK_RE.match(cell)
        if m:
            name = name or m.group(1)
            url = url or m.group(2)
            continue
        if _URL_RE.match(cell):
            url = url or cell
            continue
        if cell.upper() in _STATUS_WORDS:
            status = cell.upper()
            continue
        extra.append(cell)

    if name is None:
        name = extra[0] if extra else url
    if name is None and url is None:
        return None
    return {"name": name, "url": url, "status": status}


def list_categories() -> list[str]:
    if not REPO_DIR.exists():
        return []
    return sorted(
        f.stem for f in REPO_DIR.glob("*.md") if f.name not in _SKIP_FILES
    )


def refresh_deepdarkcti() -> dict:
    """Re-pull the latest curated list. Best-effort; never raises into the API."""
    try:
        if REPO_DIR.exists():
            subprocess.run(
                ["git", "-C", str(REPO_DIR), "pull", "--ff-only"],
                capture_output=True, timeout=30, check=True,
            )
            return {"ok": True, "action": "pulled"}
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/fastfire/deepdarkCTI.git", str(REPO_DIR)],
            capture_output=True, timeout=60, check=True,
        )
        return {"ok": True, "action": "cloned"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_deepdarkcti(query: str, limit: int = 100) -> dict:
    if not REPO_DIR.exists():
        return {"ok": False, "error": "deepdarkCTI not cloned locally", "results": []}

    q = query.lower()
    results = []
    for path in sorted(REPO_DIR.glob("*.md")):
        if path.name in _SKIP_FILES:
            continue
        category = path.stem
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if q not in line.lower():
                continue
            row = _parse_table_row(line)
            if row:
                results.append({"category": category, **row})
            else:
                # Non-table line that still matched (free text, a heading, etc.) —
                # keep the raw line so nothing gets silently dropped.
                results.append({
                    "category": category, "name": line.strip()[:200],
                    "url": None, "status": "UNKNOWN",
                })
            if len(results) >= limit:
                return {"ok": True, "error": None, "results": results, "truncated": True}

    return {"ok": True, "error": None, "results": results, "truncated": False}
