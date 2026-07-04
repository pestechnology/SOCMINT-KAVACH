"""Fail-safe / no-op path tests for the new Tier-1 OSINT modules (gravatar_scraper.py,
emailrep_scraper.py, socid_enrich.py). Deterministic and fully offline: every case here
short-circuits BEFORE any network call, so these never depend on network access or a
configured key — the live-with-a-real-key paths are exercised manually (see SETUP.md)."""
import asyncio

import backend.config as config
from backend.ingestion.base_module import make_profile
from backend.ingestion.emailrep_scraper import EmailRepScraper
from backend.ingestion.gravatar_scraper import GravatarScraper
from backend.ingestion.socid_enrich import enrich_via_socid


def test_gravatar_returns_empty_for_non_email():
    out = asyncio.run(GravatarScraper().resolve("not-an-email", "live"))
    assert out == []


def test_emailrep_returns_empty_without_key(monkeypatch):
    monkeypatch.setattr(config, "EMAILREP_API_KEY", "")
    out = asyncio.run(EmailRepScraper().resolve("someone@example.com", "live"))
    assert out == []


def test_emailrep_returns_empty_for_non_email(monkeypatch):
    monkeypatch.setattr(config, "EMAILREP_API_KEY", "some-key")
    out = asyncio.run(EmailRepScraper().resolve("not-an-email", "live"))
    assert out == []


def test_new_scrapers_never_raise_in_mock_mode():
    """resolve() always routes to _run_mock in mock data mode; neither scraper
    overrides it, so BaseDataSource's default (empty list, no network) applies."""
    assert asyncio.run(GravatarScraper().resolve("a@b.com", "mock")) == []
    assert asyncio.run(EmailRepScraper().resolve("a@b.com", "mock")) == []


def test_enrich_via_socid_noop_on_empty_list():
    assert asyncio.run(enrich_via_socid([])) == 0


def test_enrich_via_socid_skips_profiles_that_already_have_a_name():
    p = make_profile("social_account", "user1", "github", "https://github.com/user1",
                     metadata={"name": "Already Known"})
    assert asyncio.run(enrich_via_socid([p])) == 0
    assert p.metadata["name"] == "Already Known"   # untouched


def test_enrich_via_socid_skips_profiles_without_http_source():
    p = make_profile("social_account", "user1", "github", "")
    assert asyncio.run(enrich_via_socid([p])) == 0
