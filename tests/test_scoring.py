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


# ---- precision regressions (correlation-accuracy audit) ----
def test_common_name_plus_hours_not_hard_anchor():
    """REGRESSION: two unrelated people sharing a COMMON name + evening posting hours must
    NOT be treated as hard-anchored and must not reach HIGH. Fuzzy name + one soft context
    signal is not enough evidence."""
    from backend.scoring.scoring_engine import _has_hard_anchor
    # fuzzy name (common) + a single context signal -> NOT an anchor
    assert not _has_hard_anchor({"fuzzy_name_match": 20, "posting_hours_overlap": 15})
    # fuzzy name needs TWO independent context signals to anchor
    assert _has_hard_anchor({"fuzzy_name_match": 20, "posting_hours_overlap": 15,
                             "location_overlap": 15})
    # an EXACT name is distinctive enough to anchor on one context signal
    assert _has_hard_anchor({"exact_name_match": 35, "posting_hours_overlap": 15})
    # a real hard identifier always anchors on its own
    assert _has_hard_anchor({"exact_email_match": 60})


def test_common_name_evening_hours_capped_below_high():
    """Two 'Rahul Sharma' / 'Rahul Verma' accounts both posting evenings must not link HIGH."""
    md_a = {"name": "Rahul Sharma", "posting_hours": [18, 19, 20, 21]}
    md_b = {"name": "Rahul Verma", "posting_hours": [18, 19, 20, 21]}
    a = make_profile("social_account", "rahul_s", "instagram", "u1", md_a)
    b = make_profile("social_account", "rahul_v", "twitter", "u2", md_b)
    clusters = score([a, b], correlate([a, b]))
    assert all(c.tier != "HIGH" for c in clusters), "common name + hours must never reach HIGH"


def test_short_username_fragment_not_substring_match():
    """REGRESSION: a <4-char fragment contained in a longer handle is not a substring match."""
    from backend.correlation.correlation_engine import _username_signal
    assert _username_signal("jo", "john123") is None  # "jo" in "john123" is noise
    # a real >=4-char shared stem still fires
    sig = _username_signal("john", "john123")
    assert sig is not None and sig[0] in ("username_substring_match", "username_exact_match")


def test_photo_phash_lookalike_not_matched():
    """REGRESSION: two DIFFERENT photos ~8 bits apart must not fire the photo hard anchor,
    while the SAME image with minor re-encoding (<6 bits) still matches."""
    from backend.correlation.correlation_engine import _photo_match
    base = 0x0000000000000000
    same_reencoded = 0x000000000000000F   # 4 bits apart -> same image
    lookalike = 0x00000000000000FF        # 8 bits apart -> different photo
    hx = lambda n: format(n, "016x")
    assert _photo_match({"photo_phash": hx(base)}, {"photo_phash": hx(same_reencoded)})
    assert not _photo_match({"photo_phash": hx(base)}, {"photo_phash": hx(lookalike)})
    # two profiles with NO photo are "no signal", never a match
    assert not _photo_match({}, {})
