"""tests/test_phone_scrapers.py — unit tests for phone scrapers and helpers."""
from __future__ import annotations

import pytest
from backend.ingestion.phone_scrapers import _split_phone, IgnorantScraper, PhoneInfogaScraper, NumVerifyScraper


def test_split_phone_formatting():
    assert _split_phone("+919876543210") == ("91", "9876543210")
    assert _split_phone("+14155552671") == ("1", "4155552671")
    assert _split_phone("9876543210") == ("91", "9876543210")
    assert _split_phone("1234") == ("91", "1234")
    assert _split_phone("") == ("91", "")


@pytest.mark.anyio
async def test_ignorant_scraper_short_number():
    scraper = IgnorantScraper()
    assert await scraper._run_live("123") == []
    assert await scraper._run_live("") == []


@pytest.mark.anyio
async def test_phoneinfoga_scraper_short_number():
    scraper = PhoneInfogaScraper()
    assert await scraper._run_live("123") == []
    assert await scraper._run_live("") == []


@pytest.mark.anyio
async def test_numverify_scraper_short_number(monkeypatch):
    monkeypatch.setenv("NUMVERIFY_KEY", "fake_key")
    scraper = NumVerifyScraper()
    assert await scraper._run_live("123") == []
    assert await scraper._run_live("") == []
