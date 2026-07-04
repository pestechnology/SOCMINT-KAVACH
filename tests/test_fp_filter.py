"""
Tests for backend/ingestion/fp_filter.py — control-probe false-positive filter.

Verifies:
  1. control_username() format (letter-prefixed, 20 chars, always different)
  2. filter_with_control() removes sites returned for the control username
  3. Cache hit: control is NOT re-run when cache is fresh
  4. Cache miss: control IS run in parallel when cache is stale/absent
  5. Exception in run_fn is handled gracefully (fail-safe)
"""
import asyncio
import json
import os
import tempfile

import pytest

from backend.ingestion.base_module import make_profile
from backend.ingestion.fp_filter import (
    _CACHE_PATH, _TTL, control_username, filter_with_control,
    _is_fresh, _load_cache, _save_cache,
)


# ---------- control_username ----------

def test_control_username_starts_with_letter():
    ctrl = control_username()
    assert ctrl[0].isalpha(), f"Expected letter prefix, got: {ctrl!r}"


def test_control_username_length():
    ctrl = control_username()
    assert len(ctrl) == 20, f"Expected 20 chars, got {len(ctrl)}"


def test_control_username_alphanumeric():
    ctrl = control_username()
    assert ctrl.isalnum(), f"Expected alphanumeric, got: {ctrl!r}"


def test_control_username_unique():
    """Generate 100 control strings — must all differ (probability of collision ≈ 0)."""
    seen = {control_username() for _ in range(100)}
    assert len(seen) == 100


# ---------- cache helpers ----------

def test_is_fresh_stale_missing():
    assert not _is_fresh({})
    assert not _is_fresh({"timestamp": "2000-01-01T00:00:00+00:00"})


def test_is_fresh_recent():
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    assert _is_fresh({"timestamp": ts})


# ---------- filter_with_control ----------

def _make_profiles(platforms):
    return [make_profile("social_account", "test", p, f"https://{p}.com/test") for p in platforms]


def test_filter_removes_fp_sites(tmp_path, monkeypatch):
    """Sites returned for the control must be excluded from the real results."""
    monkeypatch.setattr("backend.ingestion.fp_filter._CACHE_PATH",
                        str(tmp_path / "fp_cache.json"))
    # Override _load_cache and _save_cache to use tmp_path
    import backend.ingestion.fp_filter as fp_mod
    monkeypatch.setattr(fp_mod, "_CACHE_PATH", str(tmp_path / "fp_cache.json"))

    real_platforms = ["github", "twitter", "instagram"]
    ctrl_platforms = ["twitter", "instagram"]  # these are "broken" detectors

    async def run_fn(username):
        if username.startswith("z") and len(username) == 20:
            # control run
            return _make_profiles(ctrl_platforms)
        return _make_profiles(real_platforms)

    filtered, fp_info = asyncio.run(filter_with_control("test_tool", "realuser", run_fn))

    # only "github" should survive (twitter + instagram are FP)
    assert [p.platform for p in filtered] == ["github"]
    assert "twitter" in fp_info["excluded_sites"]
    assert "instagram" in fp_info["excluded_sites"]
    assert fp_info["removed"] == 2
    assert not fp_info["cache_hit"]


def test_filter_cache_hit_skips_control(tmp_path, monkeypatch):
    """When cache is fresh, run_fn is called only once (for the real username)."""
    import backend.ingestion.fp_filter as fp_mod
    cache_path = str(tmp_path / "fp_cache.json")
    monkeypatch.setattr(fp_mod, "_CACHE_PATH", cache_path)

    from datetime import datetime, timezone
    fresh_cache = {
        "cached_tool": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "control_username": "zcontroluser00000000",
            "excluded_sites": ["fakebook"],
        }
    }
    with open(cache_path, "w") as f:
        json.dump(fresh_cache, f)

    call_count = {"n": 0}

    async def run_fn(username):
        call_count["n"] += 1
        return _make_profiles(["github", "fakebook"])

    filtered, fp_info = asyncio.run(
        filter_with_control("cached_tool", "realuser", run_fn)
    )
    assert call_count["n"] == 1, "Control should NOT have been called with fresh cache"
    assert fp_info["cache_hit"] is True
    # fakebook is in cached FP sites -> filtered out
    assert all(p.platform != "fakebook" for p in filtered)
    assert fp_info["removed"] == 1


def test_filter_stale_cache_runs_control(tmp_path, monkeypatch):
    """When cache is stale, run_fn is called twice (real + control in parallel)."""
    import backend.ingestion.fp_filter as fp_mod
    cache_path = str(tmp_path / "fp_cache.json")
    monkeypatch.setattr(fp_mod, "_CACHE_PATH", cache_path)

    stale_cache = {
        "stale_tool": {
            "timestamp": "2000-01-01T00:00:00+00:00",  # ancient
            "control_username": "zold000000000000000",
            "excluded_sites": [],
        }
    }
    with open(cache_path, "w") as f:
        json.dump(stale_cache, f)

    calls = []

    async def run_fn(username):
        calls.append(username)
        return _make_profiles(["github"])

    asyncio.run(filter_with_control("stale_tool", "realuser", run_fn))
    assert len(calls) == 2, "Should run real + control when cache is stale"
    assert "realuser" in calls
    ctrl_calls = [c for c in calls if c != "realuser"]
    assert ctrl_calls and ctrl_calls[0][0].isalpha() and len(ctrl_calls[0]) == 20


def test_filter_run_fn_exception_is_safe(tmp_path, monkeypatch):
    """A crashing run_fn must not propagate — returns ([], fp_info) gracefully."""
    import backend.ingestion.fp_filter as fp_mod
    monkeypatch.setattr(fp_mod, "_CACHE_PATH", str(tmp_path / "fp_cache.json"))

    async def run_fn(username):
        raise RuntimeError("simulated crash")

    filtered, fp_info = asyncio.run(
        filter_with_control("crash_tool", "realuser", run_fn)
    )
    assert filtered == []
    assert fp_info["removed"] == 0


def test_filter_saves_cache_after_stale_run(tmp_path, monkeypatch):
    """After a stale-cache run the cache file must be updated with a fresh timestamp."""
    import backend.ingestion.fp_filter as fp_mod
    cache_path = str(tmp_path / "fp_cache.json")
    monkeypatch.setattr(fp_mod, "_CACHE_PATH", cache_path)

    async def run_fn(username):
        return _make_profiles(["github"])

    asyncio.run(filter_with_control("fresh_tool", "realuser", run_fn))

    with open(cache_path) as f:
        saved = json.load(f)
    assert "fresh_tool" in saved
    assert _is_fresh(saved["fresh_tool"])
