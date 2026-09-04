"""
Tests for profile-URL identifier extraction (url_scraper.extract_profile_url /
extract_handle) and the url branch of derive.derive_seeds.

The reserved-path tests are the important ones: bio_url_match is a HARD ANCHOR in
scoring_engine.py, so a junk "handle" like profile.php would be standalone-sufficient
to link two unrelated accounts at HIGH confidence.
"""
import asyncio

import pytest

from backend.ingestion.derive import derive_seeds
from backend.ingestion.url_scraper import (URLScraper, extract_handle,
                                           extract_profile_url)


# --------------------------------------------------------------------------------------
# Handle extraction, per platform
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("url,platform,handle", [
    ("https://www.facebook.com/zuck", "facebook", "zuck"),
    ("https://m.facebook.com/zuck", "facebook", "zuck"),
    ("https://fb.com/zuck", "facebook", "zuck"),
    ("https://www.facebook.com/john.doe.9", "facebook", "john.doe.9"),
    ("https://www.instagram.com/instagram/", "instagram", "instagram"),
    ("https://www.instagram.com/stories/someuser/321/", "instagram", "someuser"),
    ("https://x.com/elonmusk", "twitter", "elonmusk"),
    ("https://twitter.com/elonmusk", "twitter", "elonmusk"),
    ("https://twitter.com/elonmusk/status/123", "twitter", "elonmusk"),
    ("https://twitter.com/intent/follow?screen_name=elonmusk", "twitter", "elonmusk"),
    ("https://www.youtube.com/@MrBeast", "youtube", "MrBeast"),
    ("https://www.youtube.com/user/PewDiePie", "youtube", "PewDiePie"),
    ("https://www.youtube.com/c/MKBHD", "youtube", "MKBHD"),
    ("instagram.com/no_scheme_user", "instagram", "no_scheme_user"),  # bios omit scheme
])
def test_handle_forms(url, platform, handle):
    assert extract_handle(url) == (platform, handle)


# --------------------------------------------------------------------------------------
# Platform-native IDs — recovered, and never mistaken for a handle
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("url,id_kind,platform_id", [
    ("https://www.facebook.com/profile.php?id=100012345678901",
     "facebook_numeric_id", "100012345678901"),
    ("https://www.facebook.com/100012345678901",
     "facebook_numeric_id", "100012345678901"),
    ("https://www.facebook.com/people/Arjun-Mehta/100087654321098/",
     "facebook_numeric_id", "100087654321098"),
    ("https://twitter.com/i/user/44196397", "twitter_numeric_id", "44196397"),
    ("https://twitter.com/intent/user?user_id=44196397", "twitter_numeric_id", "44196397"),
    ("https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
     "youtube_channel_id", "UCX6OQ3DkcsbYNE6H8uQQuVA"),
])
def test_platform_ids_recovered(url, id_kind, platform_id):
    info = extract_profile_url(url)
    assert info["kind"] == "profile"
    assert info["platform_id"] == platform_id
    assert info["id_kind"] == id_kind
    assert info["handle"] is None          # an id is NOT a username
    assert extract_handle(url) is None     # and must never reach a hard-anchor compare


def test_facebook_people_slug_yields_name_hint():
    info = extract_profile_url("https://www.facebook.com/people/Arjun-Mehta/100087654321098/")
    assert info["name_hint"] == "Arjun Mehta"


def test_generic_placeholder_name_is_not_used_as_a_hint():
    # "John Doe" is a placeholder, not evidence — is_generic_name() must filter it.
    info = extract_profile_url("https://www.facebook.com/people/John-Doe/100087654321098/")
    assert info["name_hint"] is None


# --------------------------------------------------------------------------------------
# Non-profile URLs: no handle, no seed. Regression guard for the hard-anchor bug.
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "https://facebook.com/groups/somegroup",
    "https://facebook.com/pages/whatever",
    "https://www.facebook.com/story.php?story_fbid=1&id=2",
    "https://instagram.com/p/CxYzAbCdEfG/",
    "https://www.instagram.com/reel/CxYzAbCdEfG/",
    "https://www.instagram.com/explore/tags/x/",
    "https://twitter.com/home",
    "https://twitter.com/search?q=test",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://www.youtube.com/results?search_query=x",
])
def test_non_profile_urls_yield_no_handle(url):
    info = extract_profile_url(url)
    assert info is not None and info["kind"] == "non_profile"
    assert info["handle"] is None
    assert extract_handle(url) is None


def test_two_different_facebook_id_urls_do_not_collide():
    """The exact false-positive this parser exists to prevent: two unrelated accounts
    must not both reduce to the handle 'profile.php' and satisfy bio_url_match."""
    a = "https://www.facebook.com/profile.php?id=100011111111111"
    b = "https://www.facebook.com/profile.php?id=100022222222222"
    assert extract_handle(a) is None and extract_handle(b) is None
    ia, ib = extract_profile_url(a), extract_profile_url(b)
    assert ia["platform_id"] != ib["platform_id"]   # distinguished by real identity


def test_unknown_host_returns_none():
    assert extract_profile_url("https://someblog.com/path/to/my_user") is None


# --------------------------------------------------------------------------------------
# URLScraper: what actually gets seeded back into the pipeline
# --------------------------------------------------------------------------------------
def test_scraper_cascades_handle():
    out = asyncio.run(URLScraper().resolve("https://instagram.com/suspect_user", "live"))
    url_p = [p for p in out if p.type == "url"][0]
    assert url_p.metadata["handle"] == "suspect_user"
    assert url_p.metadata["url_kind"] == "profile"
    assert any(p.type == "username" and p.value == "suspect_user"
               and p.metadata.get("cascade") is True for p in out)


def test_scraper_cascades_name_and_records_id_from_facebook_people_url():
    out = asyncio.run(URLScraper().resolve(
        "https://www.facebook.com/people/Arjun-Mehta/100087654321098/", "live"))
    url_p = [p for p in out if p.type == "url"][0]
    assert url_p.metadata["platform_id"] == "100087654321098"
    assert url_p.metadata["id_kind"] == "facebook_numeric_id"
    # the recovered name is fed back as a seed the pipeline can actually search
    assert any(p.type == "name" and p.value == "Arjun Mehta"
               and p.metadata.get("cascade") is True for p in out)


def test_scraper_records_but_never_seeds_a_non_profile_url():
    out = asyncio.run(URLScraper().resolve("https://instagram.com/p/CxYzAbCdEfG/", "live"))
    assert len(out) == 1                       # recorded as evidence...
    assert out[0].type == "url"
    assert out[0].metadata["url_kind"] == "non_profile"
    assert not [p for p in out if p.metadata.get("cascade")]   # ...but seeds nothing


def test_scraper_records_id_only_profile_without_a_username_seed():
    out = asyncio.run(URLScraper().resolve(
        "https://www.facebook.com/profile.php?id=100012345678901", "live"))
    assert [p for p in out if p.type == "url"][0].metadata["platform_id"] == "100012345678901"
    assert not [p for p in out if p.type == "username"]


def test_facebook_id_only_url_is_a_documented_dead_end():
    """Pins the KNOWN LIMITATION in _parse_facebook(): an id-only Facebook URL records
    the id as evidence but produces NO cascade seed and NO derived seed, because no
    clearnet route can resolve the id to a name. If someone later wires up an
    authenticated-browser resolver, this test is the one that should change."""
    url = "https://www.facebook.com/profile.php?id=100012345678901"
    info = extract_profile_url(url)
    assert info["kind"] == "profile"          # it IS a real person's profile...
    assert info["platform_id"] == "100012345678901"
    assert info["handle"] is None and info["name_hint"] is None   # ...with nothing searchable

    out = asyncio.run(URLScraper().resolve(url, "live"))
    assert not [p for p in out if p.metadata.get("cascade")]      # nothing fed back
    assert derive_seeds("url", url) == []                         # and nothing to pivot on


# --------------------------------------------------------------------------------------
# Re-iteration: derive_seeds("url", ...)
# --------------------------------------------------------------------------------------
def test_derive_from_profile_url_emits_observed_handle_highest():
    seeds = derive_seeds("url", "https://www.instagram.com/arjunmehta/")
    handle_seed = [s for s in seeds if s["strategy"] == "url_handle"][0]
    assert handle_seed["type"] == "username" and handle_seed["value"] == "arjunmehta"
    # observed in the URL, so it must outrank every guessed derivation
    assert handle_seed["confidence"] > max(
        s["confidence"] for s in seeds if s["strategy"] != "url_handle")


def test_derive_from_facebook_people_url_uses_the_slug_name():
    seeds = derive_seeds("url", "https://www.facebook.com/people/Arjun-Mehta/100087654321098/")
    assert any(s["type"] == "name" and s["value"] == "Arjun Mehta"
               and s["strategy"] == "url_slug_name" for s in seeds)
    assert any(s["type"] == "username" for s in seeds)   # chained handle variants


@pytest.mark.parametrize("url", [
    "https://instagram.com/p/CxYzAbCdEfG/",
    "https://facebook.com/groups/somegroup",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
])
def test_derive_from_non_profile_url_yields_nothing(url):
    assert derive_seeds("url", url) == []
