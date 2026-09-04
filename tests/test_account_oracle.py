"""
Tests for AccountOracleScraper (extensible account-existence oracle registry).

Network stubbed. The safety test (notifying oracles never run) is the important one —
an existence check that emails/OTPs the subject would tip off an investigation.
"""
import asyncio

import pytest

import backend.ingestion.account_oracle_scraper as mod
from backend.ingestion.account_oracle_scraper import (AccountOracleScraper, Oracle,
                                                      RawProfile)


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def json(self):
        return self._p


def _stub(monkeypatch, responder):
    """Patch AsyncClient.get so each oracle URL yields a scripted response."""
    class _Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, url, headers=None):
            return responder(url)
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _Client())


def test_username_hit_returns_existence_and_enrichment(monkeypatch):
    def responder(url):
        if "chess.com" in url:
            return _Resp({"username": "vismay_hs", "name": "V HS", "joined": 111,
                          "country": "https://api.chess.com/pub/country/IN"})
        if "lichess" in url:
            return _Resp({"id": "vismay_hs", "username": "Vismay_HS", "createdAt": 222})
        return _Resp([], 404)   # gitlab (list) / duolingo miss
    _stub(monkeypatch, responder)
    out = asyncio.run(AccountOracleScraper().resolve("vismay_hs", "live"))
    got = {p.platform: p.metadata for p in out}
    assert set(got) == {"chess.com", "lichess"}
    assert all(p.type == "account_existence" for p in out)
    assert got["chess.com"]["name"] == "V HS"
    assert got["lichess"]["display_username"] == "Vismay_HS"


def test_clean_miss_yields_nothing(monkeypatch):
    _stub(monkeypatch, lambda url: _Resp([], 404) if "gitlab" in url
          else _Resp({"users": []}) if "duolingo" in url else _Resp({}, 404))
    assert asyncio.run(AccountOracleScraper().resolve("nobody_xyz", "live")) == []


def test_email_identifier_runs_no_username_oracles(monkeypatch):
    """All shipped oracles are username-type; an email seed must trigger zero requests."""
    def _boom(*a, **k):
        raise AssertionError("no HTTP client should be created for an email identifier")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _boom)
    assert asyncio.run(AccountOracleScraper().resolve("a@b.com", "live")) == []


def test_blank_identifier_makes_no_request(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("no request for a blank identifier")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _boom)
    assert asyncio.run(AccountOracleScraper().resolve("", "live")) == []


def test_a_failing_oracle_never_sinks_the_others(monkeypatch):
    def responder(url):
        if "chess.com" in url:
            raise RuntimeError("network blew up")
        if "lichess" in url:
            return _Resp({"id": "u", "username": "U", "createdAt": 1})
        return _Resp([], 404)
    _stub(monkeypatch, responder)
    out = asyncio.run(AccountOracleScraper().resolve("u", "live"))
    assert [p.platform for p in out] == ["lichess"]


# ---- the safety invariant -----------------------------------------------------------
def test_notifying_oracles_are_never_executed(monkeypatch):
    """A notifies_target=True oracle must NEVER fire — running it would email/OTP the
    investigation subject. Inject one and assert its URL is never requested."""
    called = []
    poison = Oracle("evilbank", "evilbank.com", "username", True,
                    lambda v: "https://evilbank.com/reset",
                    lambda r: {"exists": True})
    monkeypatch.setattr(mod, "_ORACLES", [poison])

    def responder(url):
        called.append(url)
        return _Resp({}, 200)
    _stub(monkeypatch, responder)

    out = asyncio.run(AccountOracleScraper().resolve("someone", "live"))
    assert out == []
    assert called == [], "a notifies_target=True oracle was executed"


def test_every_shipped_oracle_is_non_notifying():
    """Nothing in the always-on registry may notify the subject."""
    assert all(o.notifies_target is False for o in mod._ORACLES)


def test_wired_into_username_seed_path(monkeypatch):
    from backend import config
    from backend.pipeline.orchestrator import _seed_tool_map
    monkeypatch.setattr(config, "DATA_MODE", "live")
    tm = _seed_tool_map()
    assert any(t.name == "account_oracle" for t in tm["username"])
