"""Unit tests — correlation + scoring engine (the brain). Includes red-herring regression."""
import asyncio

from backend.correlation.correlation_engine import correlate, SIGNAL_WEIGHTS
from backend.ingestion.base_module import make_profile
from backend.ingestion.mock_scraper import MockScraper
from backend.scoring.scoring_engine import score, _tier, _UnionFind


def _mock():
    return asyncio.run(MockScraper().resolve("arjun", "mock"))


# ---- happy path ----
def test_same_person_clusters_high():
    profiles = _mock()
    clusters = score(profiles, correlate(profiles))
    high = [c for c in clusters if c.tier == "HIGH"]
    assert high, "expected a HIGH cluster for the same-person trio"
    assert len(high[0].member_indices) >= 2


def test_red_herring_is_low_and_isolated():
    """REGRESSION: a username-only match must NOT join the HIGH cluster and must cap at LOW."""
    profiles = _mock()
    clusters = score(profiles, correlate(profiles))
    high = [c for c in clusters if c.tier == "HIGH"][0]
    # linkedin red herring is the 4th mock profile (index 3)
    assert 3 not in high.member_indices
    rh = [c for c in clusters if 3 in c.member_indices][0]
    assert rh.tier == "LOW"
    assert rh.confidence_score < 50


def test_single_signal_capped_low():
    """REGRESSION: even a heavy single signal (phone, 40pts) must cap at LOW."""
    a = make_profile("social_account", "x", "p1", "u1", {"phone": "+919999999999"})
    b = make_profile("social_account", "y", "p2", "u2", {"phone": "+919999999999"})
    clusters = score([a, b], correlate([a, b]))
    # one signal only -> not linked, capped LOW
    assert all(c.tier in ("LOW", "REJECT") for c in clusters)


# ---- boundary / tiers ----
def test_tier_thresholds():
    assert _tier(76) == "HIGH"
    assert _tier(75) == "MEDIUM"
    assert _tier(50) == "MEDIUM"
    assert _tier(49) == "LOW"
    assert _tier(25) == "LOW"
    assert _tier(24) == "REJECT"
    assert _tier(0) == "REJECT"


# ---- edge cases ----
def test_empty_inputs():
    assert score([], []) == []


def test_single_profile_is_singleton():
    a = make_profile("social_account", "solo", "github", "url")
    clusters = score([a], correlate([a]))
    assert len(clusters) == 1
    assert clusters[0].member_indices == [0]


def test_confidence_capped_at_100():
    # pile on many signals; confidence must never exceed 100
    md = {"phone": "+911", "email": "a@b.com", "upi": "x@oksbi",
          "photo_url": "p", "posting_hours": [1, 2, 3], "bio": "alpha beta gamma delta"}
    a = make_profile("social_account", "same", "p1", "u1", dict(md))
    b = make_profile("social_account", "same", "p2", "u2", dict(md))
    clusters = score([a, b], correlate([a, b]))
    assert all(c.confidence_score <= 100 for c in clusters)


def test_unionfind():
    uf = _UnionFind(4)
    uf.union(0, 1); uf.union(1, 2)
    assert uf.find(0) == uf.find(2)
    assert uf.find(0) != uf.find(3)


def test_weights_present():
    for k in ("exact_phone_match", "username_exact_match", "profile_photo_phash"):
        assert SIGNAL_WEIGHTS[k] > 0


def test_seed_matching_subword_and_metadata():
    # Simulate finding LinkedIn profile with generated suffix or matching metadata fullname
    a = make_profile("social_account", "ashwin-harish-a628a72b2", "linkedin", "https://linkedin.com/in/ashwin-harish-a628a72b2", {"name": "Ashwin Harish - AI intern @GREYWIZ"})
    seeds = [{"type": "name", "value": "Ashwin Harish"}]
    clusters = score([a], correlate([a]), seeds=seeds)
    assert len(clusters) == 1
    assert clusters[0].confidence_score == 100.0
    assert clusters[0].tier == "HIGH"
