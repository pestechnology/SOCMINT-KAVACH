"""Tests for the user-facing MATCH CONFIDENCE layer (backend/scoring/confidence.py).

Match confidence (LOW/MEDIUM/HIGH) is a SEPARATE axis from the forensic linkage tier:
it answers "is this a correct match for the search?", not "are these the same person?".
Key contract:
  - exact username/seed match -> HIGH, always;
  - deterministic hard-evidence correlation grades on its own strength;
  - a confirmed AI adjudication can reach HIGH;
  - LLM relevance ALONE is capped below HIGH (a lead, not a confirmed match);
  - no-signal accounts are LOW (never REJECT — this axis has 3 tiers only).
"""
from backend.correlation.correlation_engine import correlate
from backend.ingestion.base_module import make_profile
from backend.scoring.scoring_engine import score
from backend.scoring import confidence
from backend.scoring.confidence import (
    compute, stamp_clusters, tier_for, seed_value_set, RELEVANCE_SOLO_CAP,
)


# ---- tier mapping ----
def test_tier_thresholds_three_levels():
    assert tier_for(100) == "HIGH"
    assert tier_for(70) == "HIGH"
    assert tier_for(69) == "MEDIUM"
    assert tier_for(40) == "MEDIUM"
    assert tier_for(39) == "LOW"
    assert tier_for(0) == "LOW"
    # never REJECT on this axis
    assert tier_for(0) != "REJECT"


# ---- exact match -> HIGH ----
class _Cl:
    """Minimal stand-in for a Cluster for the pure-compute tests."""
    def __init__(self, **kw):
        self.member_indices = kw.get("member_indices", [])
        self.confidence_score = kw.get("confidence_score", 0.0)
        self.relevance_score = kw.get("relevance_score", 0)
        self.ai_confirmed = kw.get("ai_confirmed", False)
        self.ai_confidence = kw.get("ai_confidence", 0)


def test_exact_seed_flag_is_high():
    p = make_profile("social_account", "vismayhs", "github", "u", {"username": "vismayhs"})
    p.metadata["exact_seed_match"] = True
    res = compute(_Cl(member_indices=[0], confidence_score=0.0), [p], set())
    assert res["tier"] == "HIGH"
    assert res["score"] == 100


def test_exact_username_equals_seed_is_high():
    p = make_profile("social_account", "vismayhs", "instagram", "u", {"username": "vismayhs"})
    seed_vals = seed_value_set([{"type": "username", "value": "vismayhs"}])
    res = compute(_Cl(member_indices=[0], confidence_score=0.0), [p], seed_vals)
    assert res["tier"] == "HIGH"


def test_relevance_100_flag_is_high():
    p = make_profile("social_account", "x", "web", "u", {})
    res = compute(_Cl(member_indices=[0], relevance_score=100), [p], set())
    assert res["tier"] == "HIGH"


# ---- algorithmic grading ----
def test_hard_evidence_grades_high():
    p = make_profile("social_account", "x", "p1", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=80.0), [p], set())
    assert res["tier"] == "HIGH"
    assert res["score"] == 80


def test_medium_algo_stays_medium():
    p = make_profile("social_account", "x", "p1", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=55.0), [p], set())
    assert res["tier"] == "MEDIUM"


def test_no_signal_is_low_never_reject():
    p = make_profile("social_account", "x", "p1", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=0.0), [p], set())
    assert res["tier"] == "LOW"


# ---- LLM relevance is capped below HIGH ----
def test_relevance_alone_capped_below_high():
    """A singleton the LLM rates relevance=95 but with ZERO hard evidence is a LEAD, not a
    confirmed match — it must never reach HIGH on the model's word alone."""
    p = make_profile("social_account", "x", "web", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=0.0, relevance_score=95), [p], set())
    assert res["tier"] == "MEDIUM"
    assert res["score"] <= RELEVANCE_SOLO_CAP


# ---- AI adjudication ----
def test_ai_confirmed_reaches_high():
    p = make_profile("social_account", "x", "web", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=30.0,
                      ai_confirmed=True, ai_confidence=88), [p], set())
    assert res["tier"] == "HIGH"


def test_ai_confidence_ignored_when_not_confirmed():
    """ai_confidence must not count unless the adjudicator actually confirmed the link."""
    p = make_profile("social_account", "x", "web", "u", {})
    res = compute(_Cl(member_indices=[0], confidence_score=20.0,
                      ai_confirmed=False, ai_confidence=90), [p], set())
    assert res["tier"] == "LOW"


# ---- corroboration bonus ----
def test_two_moderate_votes_get_corroboration_bonus():
    """Two independent moderate votes add a corroboration bonus over the single-vote score,
    and can tip a solid MEDIUM over the HIGH line."""
    p = make_profile("social_account", "x", "web", "u", {})
    solo = compute(_Cl(member_indices=[0], confidence_score=60.0), [p], set())
    both = compute(_Cl(member_indices=[0], confidence_score=60.0, relevance_score=60), [p], set())
    assert both["score"] > solo["score"]           # bonus applied
    assert both["tier"] == "MEDIUM"                # 60 + 8 = 68, still MEDIUM (conservative)
    # a stronger pair does cross into HIGH via corroboration
    strong = compute(_Cl(member_indices=[0], confidence_score=65.0, relevance_score=65), [p], set())
    assert strong["tier"] == "HIGH"                # 65 + 8 = 73


# ---- integration with the real scoring engine ----
def test_stamp_sets_fields_on_real_clusters():
    a = make_profile("social_account", "same", "p1", "u1", {"email": "a@b.com", "posting_hours": [1, 2, 3]})
    b = make_profile("social_account", "same", "p2", "u2", {"email": "a@b.com", "posting_hours": [1, 2, 3]})
    profiles = [a, b]
    clusters = score(profiles, correlate(profiles))
    stamp_clusters(clusters, profiles, seeds=None)
    for c in clusters:
        assert c.match_tier in ("LOW", "MEDIUM", "HIGH")
        assert 0 <= c.match_score <= 100


def test_lone_exact_username_singleton_is_high_end_to_end():
    """The exact account the investigator searched for shows HIGH match confidence even
    though it has no cross-account link (forensic tier stays REJECT/LOW)."""
    p = make_profile("social_account", "vismayhs", "github", "https://github.com/vismayhs", {"username": "vismayhs"})
    seeds = [{"type": "username", "value": "vismayhs"}]
    clusters = score([p], correlate([p]), seeds=seeds)
    stamp_clusters(clusters, [p], seeds=seeds)
    assert len(clusters) == 1
    assert clusters[0].match_tier == "HIGH"
    # forensic linkage tier is untouched — no corroborating link exists
    assert clusters[0].tier in ("LOW", "REJECT")


def test_compute_never_raises_on_garbage():
    class Bad:
        pass
    res = confidence.compute(Bad(), [], set())
    assert res["tier"] == "LOW"


# ---- gaming/low-value platforms are capped LOW even when they exactly match ----
def test_gaming_platform_capped_low_even_on_exact_match():
    """A gaming handle that exactly matches the seed is kept but must stay LOW — a game
    handle is not identity evidence (product decision)."""
    p = make_profile("social_account", "ghost_rider99", "leagueoflegends",
                     "https://leagueoflegends.com/ghost_rider99", {"username": "ghost_rider99"})
    p.metadata["exact_seed_match"] = True
    seed_vals = seed_value_set([{"type": "username", "value": "ghost_rider99"}])
    res = compute(_Cl(member_indices=[0], relevance_score=100), [p], seed_vals)
    assert res["tier"] == "LOW"


def test_mixed_cluster_with_a_game_account_not_capped():
    """A cluster mixing a real account with a game account is NOT low-value — real evidence
    stands (only ALL-gaming clusters are capped)."""
    real = make_profile("social_account", "gr99", "github", "https://github.com/gr99", {})
    game = make_profile("social_account", "gr99", "steam", "https://steamcommunity.com/id/gr99", {})
    res = compute(_Cl(member_indices=[0, 1], confidence_score=80.0), [real, game], set())
    assert res["tier"] == "HIGH"


# ---- gaming/low-value platforms are capped to LOW even on an exact match ----
def test_gaming_exact_match_capped_low():
    """A gaming handle is kept but never ranks high — even when it exactly matches the seed."""
    p = make_profile("social_account", "ghost_rider99", "leagueoflegends",
                     "https://leagueoflegends.com/ghost_rider99", {"username": "ghost_rider99"})
    p.metadata["exact_seed_match"] = True
    seed_vals = seed_value_set([{"type": "username", "value": "ghost_rider99"}])
    res = compute(_Cl(member_indices=[0], relevance_score=100), [p], seed_vals)
    assert res["tier"] == "LOW"


def test_mixed_cluster_with_one_game_account_not_capped():
    """A cluster of a real account + a game account keeps its real strength (not all low-value)."""
    real = make_profile("social_account", "x", "github", "https://github.com/x", {})
    game = make_profile("social_account", "x", "steam", "https://steamcommunity.com/id/x", {})
    res = compute(_Cl(member_indices=[0, 1], confidence_score=80.0), [real, game], set())
    assert res["tier"] == "HIGH"
