import pytest
from backend.ingestion.base_module import make_profile
from backend.ingestion.country_filter import filter_profiles_by_country


def test_filter_profiles_by_country_all():
    profiles = [
        make_profile("social_account", "user1", "xing", "https://www.xing.com/profile/user1"),
        make_profile("social_account", "user1", "instagram", "https://instagram.com/user1"),
    ]
    # When ALL or None, nothing is filtered
    assert len(filter_profiles_by_country(profiles, "ALL")) == 2
    assert len(filter_profiles_by_country(profiles, None)) == 2


def test_filter_profiles_by_country_india():
    """Strict Indian-only scope: Indian domestic platforms + core identifiers are kept;
    global majors (Instagram, LinkedIn, …), foreign-regional networks, and global games
    (League of Legends) are dropped."""
    profiles = [
        make_profile("social_account", "user1", "xing", "https://www.xing.com/profile/user1"),
        make_profile("social_account", "user1", "ixbt", "https://ixbt.com/user1"),
        make_profile("social_account", "user1", "instagram", "https://instagram.com/user1"),
        make_profile("social_account", "user1", "linkedin", "https://linkedin.com/in/user1"),
        make_profile("social_account", "user1", "leagueoflegends", "https://leagueoflegends.com/user1"),
        make_profile("social_account", "user1", "sharechat", "https://sharechat.com/user1"),
        make_profile("social_account", "user1", "zerodha", "https://zerodha.com/user1"),
        make_profile("phone", "+919876543210", "truecaller", "https://truecaller.com/search/+919876543210"),
    ]
    filtered = filter_profiles_by_country(profiles, "INDIA")
    platforms = {p.platform for p in filtered}

    # Indian domestic platforms kept
    assert "sharechat" in platforms
    assert "zerodha" in platforms
    # Core identifier (phone) kept regardless of platform
    assert "truecaller" in platforms
    # Global majors and foreign/gaming platforms dropped
    assert "instagram" not in platforms
    assert "linkedin" not in platforms
    assert "leagueoflegends" not in platforms
    assert "xing" not in platforms
    assert "ixbt" not in platforms
    assert len(filtered) == 3


def test_india_drops_global_site_urls():
    """A `url`-type link to a global site is dropped; a link to an Indian site survives."""
    profiles = [
        make_profile("url", "ig", "web", "https://instagram.com/someone"),
        make_profile("url", "fk", "web", "https://flipkart.com/account/xyz"),
    ]
    filtered = filter_profiles_by_country(profiles, "INDIA")
    urls = {p.source_url for p in filtered}
    assert "https://flipkart.com/account/xyz" in urls
    assert "https://instagram.com/someone" not in urls
