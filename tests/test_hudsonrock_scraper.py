"""
Tests for HudsonRockScraper (free, key-less info-stealer exposure lookup).

Network is stubbed — these pin PARSING and the over-claiming guards, not Hudson Rock's
live data. The guards matter: a username is not a unique identity, and the free tier
returns masked passwords we deliberately refuse to store.
"""
import asyncio

import pytest

from backend.ingestion.hudsonrock_scraper import HudsonRockScraper

HIT = {
    "message": "This email address is associated with a computer that was infected...",
    "stealers": [
        {"stealer_family": "RedLine", "computer_name": "DESKTOP-ABC (Arjun)",
         "operating_system": "Windows 11 Home", "date_compromised": "2026-08-29T00:00:00.000Z",
         "ip": "Not Found", "malware_path": "Not Found",
         "top_passwords": ["s********8", "p*****d"],
         "top_logins": ["a**********@gmail.com", "arjun***"],
         "total_user_services": 32, "total_corporate_services": 0},
        {"stealer_family": "Generic Stealer", "computer_name": "Not Found",
         "operating_system": "Windows 10", "date_compromised": "2026-09-03T00:43:32.000Z",
         "top_passwords": ["x*****1"], "top_logins": ["a**********@gmail.com"]},
    ],
    "total_user_services": 32, "total_corporate_services": 0,
}
MISS = {"message": "...not associated...", "stealers": [],
        "total_user_services": 0, "total_corporate_services": 0}


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def json(self):
        return self._p


class _Client:
    """Stub httpx.AsyncClient; records the URL/params the scraper chose."""
    last = {}
    def __init__(self, payload, status=200):
        self._payload, self._status = payload, status
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, url, params=None, headers=None):
        _Client.last = {"url": url, "params": params}
        return _Resp(self._payload, self._status)


def _run(monkeypatch, ident, payload, status=200):
    import backend.ingestion.hudsonrock_scraper as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient",
                        lambda *a, **k: _Client(payload, status))
    return asyncio.run(HudsonRockScraper().resolve(ident, "live"))


def test_email_hit_extracts_fields(monkeypatch):
    out = _run(monkeypatch, "arjun@example.com", HIT)
    assert len(out) == 1
    m = out[0].metadata
    assert out[0].type == "breach" and out[0].platform == "hudsonrock"
    assert m["infostealer_infection"] is True
    assert m["stealer_count"] == 2
    assert m["stealer_families"] == ["RedLine", "Generic Stealer"]
    assert m["compromised_computers"] == ["DESKTOP-ABC (Arjun)"]   # "Not Found" dropped
    assert m["date_compromised"] == "2026-09-03T00:43:32.000Z"     # most recent
    assert m["total_user_services"] == 32
    assert m["masked_logins"] == ["a**********@gmail.com", "arjun***"]   # deduped


def test_passwords_are_never_stored(monkeypatch):
    """Masked partial credentials are liability without investigative value."""
    m = _run(monkeypatch, "arjun@example.com", HIT)[0].metadata
    assert "top_passwords" not in m
    assert "s********8" not in str(m)


def test_never_feeds_breach_co_occurrence(monkeypatch):
    """metadata['breaches'] drives a correlation signal. "Was infected by a stealer" is
    a non-discriminating property — two unrelated infected people must not correlate."""
    m = _run(monkeypatch, "arjun@example.com", HIT)[0].metadata
    assert "breaches" not in m


def test_email_match_is_identity_bearing(monkeypatch):
    m = _run(monkeypatch, "arjun@example.com", HIT)[0].metadata
    assert m["identifier_kind"] == "email"
    assert m["identity_confirmed"] is True


def test_username_match_is_flagged_lead_only(monkeypatch):
    """A username is NOT unique — Hudson Rock returns every infected machine whose
    stolen credentials contained the handle, so this must never read as 'the subject's
    machine was infected'."""
    m = _run(monkeypatch, "arjun", HIT)[0].metadata
    assert m["identifier_kind"] == "username"
    assert m["identity_confirmed"] is False
    assert "lead only" in m["note"].lower()


def test_endpoint_selected_by_identifier_shape(monkeypatch):
    _run(monkeypatch, "arjun@example.com", HIT)
    assert _Client.last["url"].endswith("search-by-email")
    assert _Client.last["params"] == {"email": "arjun@example.com"}
    _run(monkeypatch, "arjun", HIT)
    assert _Client.last["url"].endswith("search-by-username")
    assert _Client.last["params"] == {"username": "arjun"}


@pytest.mark.parametrize("payload,status", [
    (MISS, 200),            # clean miss
    (HIT, 500),             # server error
    ({"stealers": None}, 200),
    ({}, 200),
    ("not-a-dict", 200),
])
def test_fail_safe_returns_empty(monkeypatch, payload, status):
    assert _run(monkeypatch, "arjun@example.com", payload, status) == []


def test_blank_identifier_makes_no_request(monkeypatch):
    import backend.ingestion.hudsonrock_scraper as mod
    def _boom(*a, **k):
        raise AssertionError("must not make a network call for a blank identifier")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _boom)
    assert asyncio.run(HudsonRockScraper().resolve("", "live")) == []


def test_wired_into_username_and_email_seed_paths(monkeypatch):
    """conftest forces DATA_MODE=mock, and mock mode REPLACES the whole tool map with
    MockScraper — so live mode has to be forced to assert real wiring."""
    from backend import config
    from backend.pipeline.orchestrator import _seed_tool_map
    monkeypatch.setattr(config, "DATA_MODE", "live")
    tm = _seed_tool_map()
    for seed in ("username", "email"):
        assert any(t.name == "hudsonrock" for t in tm[seed]), f"missing from {seed}"
