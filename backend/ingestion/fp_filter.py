"""
backend/ingestion/fp_filter.py — control-probe false-positive filter.

Maigret and Sherlock use stale HTTP-response heuristics to detect "claimed"
accounts; many of their site definitions have rotted and fire for ANY username
regardless of whether the account actually exists.

Mitigation: run the tool against a random, virtually-guaranteed-unclaimed control
string IN PARALLEL with the real query.  Any site that fires for the control string
is broken and is excluded from the real results for that run.

Cache: results are written to reports/false_positive_sites.json with a 6-hour TTL
so the extra probe runs roughly once per demo session, not once per case.

Note on other tools:
  • Socialscan uses a real registration-flow check (available=False AND valid AND
    success) — not an HTTP-response heuristic — and does not exhibit this problem.
  • Blackbird CLI is not installed in this venv; its scraper returns [] harmlessly.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

_CACHE_PATH = os.path.join("reports", "false_positive_sites.json")
_TTL = 6 * 3600  # seconds — re-probe once per 6-hour window


# --------------------------------------------------------------------------- #
#  Cache helpers
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def control_username() -> str:
    """Random 20-char alphanumeric string starting with a letter.

    Letter prefix satisfies sites that require ^[a-zA-Z]; the UUID hex body
    makes it virtually unclaimed on any real platform.  A new value is generated
    on every stale-cache refresh so no site can special-case a known string.
    """
    return "z" + uuid.uuid4().hex[:19]


def _load_cache() -> dict:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(tool_name: str, entry: dict) -> None:
    # Read-merge-write: load the current file so a parallel tool's entry (written
    # between our cache load and now) is preserved rather than overwritten.
    # asyncio is single-threaded so the load+write here runs atomically (no awaits).
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH) or ".", exist_ok=True)
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[tool_name] = entry
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _is_fresh(entry: dict) -> bool:
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(entry["timestamp"])).total_seconds()
        return age < _TTL
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #

async def filter_with_control(
    tool_name: str,
    real_username: str,
    run_fn,           # async (str) -> list[RawProfile]
) -> tuple[list, dict]:
    """Run run_fn(real_username) with false-positive filtering.

    Sites that also fire for a random control username are excluded from the
    real results.  When the cache is fresh (< 6 h), cached FP sites are used
    without re-running the control probe.  When stale, real + control run IN
    PARALLEL so the total wall time stays roughly the same as one run.

    Args:
        tool_name:     Key used for the per-tool cache entry ("maigret", "sherlock").
        real_username: The actual username being investigated.
        run_fn:        Async callable (username: str) -> list[RawProfile].

    Returns:
        (filtered_profiles, fp_info_dict)
        fp_info_dict keys: tool, control_username, excluded_sites, cache_hit, removed.
    """
    cache = _load_cache()
    entry = cache.get(tool_name, {})

    if _is_fresh(entry):
        fp_sites = set(entry.get("excluded_sites", []))
        ctrl = entry.get("control_username", "(cached)")
        real_profiles = await run_fn(real_username)
        before = len(real_profiles)
        filtered = [p for p in real_profiles if p.platform.lower() not in fp_sites]
        return filtered, {
            "tool": tool_name,
            "control_username": ctrl,
            "excluded_sites": sorted(fp_sites),
            "cache_hit": True,
            "removed": before - len(filtered),
        }

    # Stale or absent cache — run real + control in parallel (same timeout budget)
    ctrl = control_username()
    real_task = asyncio.create_task(run_fn(real_username))
    ctrl_task = asyncio.create_task(run_fn(ctrl))
    real_res, ctrl_res = await asyncio.gather(real_task, ctrl_task,
                                              return_exceptions=True)

    real_profiles = real_res if isinstance(real_res, list) else []
    ctrl_profiles = ctrl_res if isinstance(ctrl_res, list) else []

    fp_sites = {p.platform.lower() for p in ctrl_profiles}
    new_entry = {
        "timestamp": _now(),
        "control_username": ctrl,
        "excluded_sites": sorted(fp_sites),
    }
    _save_cache(tool_name, new_entry)

    before = len(real_profiles)
    filtered = [p for p in real_profiles if p.platform.lower() not in fp_sites]
    return filtered, {
        "tool": tool_name,
        "control_username": ctrl,
        "excluded_sites": sorted(fp_sites),
        "cache_hit": False,
        "removed": before - len(filtered),
    }
