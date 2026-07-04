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
    """INDIA scope keeps major global platforms + Indian sites and drops foreign-regional
    networks. Gaming sites (League of Legends) are KEPT (visible) — they're scored low
    separately, not filtered out."""
    profiles = [
        make_profile("social_account", "user1", "xing", "https://www.xing.com/profile/user1"),
        make_profile("social_account", "user1", "ixbt", "https://ixbt.com/user1"),
        make_profile("social_account", "user1", "instagram", "https://instagram.com/user1"),
        make_profile("social_account", "user1", "linkedin", "https://linkedin.com/in/user1"),
        make_profile("social_account", "user1", "leagueoflegends", "https://leagueoflegends.com/user1"),
        make_profile("phone", "+919876543210", "truecaller", "https://truecaller.com/search/+919876543210"),
    ]
    filtered = filter_profiles_by_country(profiles, "INDIA")
    platforms = {p.platform for p in filtered}

    # Global majors + Indian sites kept
    assert "instagram" in platforms
    assert "linkedin" in platforms
    assert "truecaller" in platforms
    # Gaming kept (visible, scored low elsewhere)
    assert "leagueoflegends" in platforms
    # Foreign-regional networks still dropped
    assert "xing" not in platforms
    assert "ixbt" not in platforms
    assert len(filtered) == 4


def test_is_low_value_platform():
    from backend.ingestion.country_filter import is_low_value_platform
    assert is_low_value_platform("leagueoflegends", "")
    assert is_low_value_platform("", "https://op.gg/summoner/xyz")
    assert is_low_value_platform("steam", "")
    assert not is_low_value_platform("github", "https://github.com/x")
    assert not is_low_value_platform("linkedin", "")
