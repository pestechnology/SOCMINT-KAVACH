"""Tests for URLScraper and deduplication merging logic."""
import asyncio
from backend.ingestion.url_scraper import URLScraper
from backend.pipeline.orchestrator import _dedup
from backend.ingestion.base_module import make_profile

def test_url_scraper_extracts_and_cascades():
    scraper = URLScraper()
    out = asyncio.run(scraper.resolve("https://instagram.com/suspect_username", "live"))
    assert len(out) == 2
    assert any(p.type == "url" and p.platform == "instagram" and p.metadata.get("handle") == "suspect_username" for p in out)
    assert any(p.type == "username" and p.platform == "derived" and p.metadata.get("cascade") is True for p in out)

def test_url_scraper_fallback():
    scraper = URLScraper()
    out = asyncio.run(scraper.resolve("https://someblog.com/path/to/my_user", "live"))
    assert len(out) == 2
    assert any(p.metadata.get("handle") == "my_user" for p in out)

def test_dedup_merges_social_accounts():
    p1 = make_profile("social_account", "torvalds", "github", "https://github.com/torvalds", {"bio": "Linux creator", "followers": 100})
    p2 = make_profile("social_account", "torvalds", "github", "", {"location": "US", "followers": 100})
    
    deduped = _dedup([p1, p2])
    assert len(deduped) == 1
    merged = deduped[0]
    assert merged.platform == "github"
    assert merged.value == "torvalds"
    assert merged.source_url == "https://github.com/torvalds"
    assert merged.metadata.get("bio") == "Linux creator"
    assert merged.metadata.get("location") == "US"
