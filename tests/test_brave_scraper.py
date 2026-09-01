"""Fail-safe / no-op path tests for brave_scraper.py, plus deterministic unit tests for
its site:-domain host-verification guard (the defense against Brave silently dropping
the site: operator — see the module docstring). Fully offline: every case here
short-circuits BEFORE any network call, or exercises pure helper functions directly.
The live-with-a-real-key path is exercised manually (see API_KEYS_AND_BOTS.md)."""
import asyncio

import backend.config as config
from backend.ingestion.brave_scraper import BraveScraper, _host_matches_site, _site_domain


def test_brave_returns_empty_without_key(monkeypatch):
    monkeypatch.setattr(config, "BRAVE_API_KEY", "")
    out = asyncio.run(BraveScraper().resolve("someone", "live"))
    assert out == []


def test_brave_never_raises_in_mock_mode():
    """resolve() always routes to _run_mock in mock data mode; BraveScraper doesn't
    override it, so BaseDataSource's default (empty list, no network) applies."""
    assert asyncio.run(BraveScraper().resolve("someone", "mock")) == []


def test_site_domain_extracts_from_template():
    assert _site_domain('site:pastebin.com "{q}"') == "pastebin.com"
    assert _site_domain('site:reddit.com/user "{q}"') == "reddit.com"
    assert _site_domain('"{q}"') is None


def test_host_matches_site_exact_and_subdomain():
    assert _host_matches_site("https://pastebin.com/abc123", "pastebin.com")
    assert _host_matches_site("https://www.pastebin.com/abc123", "pastebin.com")
    assert _host_matches_site("https://in.linkedin.com/in/foo", "linkedin.com")


def test_host_matches_site_rejects_offtarget_host():
    """The exact scenario the guard exists for: Brave silently drops the site: operator
    and returns a result from an unrelated domain — it must NOT be accepted as if it
    were platform-scoped evidence."""
    assert not _host_matches_site("https://totally-unrelated-site.example/page", "pastebin.com")
    assert not _host_matches_site("https://notpastebin.com/abc123", "pastebin.com")
