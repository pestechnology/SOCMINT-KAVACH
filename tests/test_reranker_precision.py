"""Precision regressions for the LLM reranker (correlation-accuracy audit).

The reranker may reorder leads and add members for recall, but the LLM must NEVER be the
sole justification for a confirmed link:
  - a high-relevance SINGLETON with no hard signal must not have its tier/confidence raised
    above what the deterministic engine gave it (it stays a LOW/REJECT lead);
  - promoting a singleton INTO a confirmed cluster must not UPGRADE that cluster's tier.

The LLM is stubbed so the test is deterministic and offline.
"""
from backend.analysis import reranker
from backend.ingestion.base_module import make_profile
from backend.correlation.correlation_engine import correlate
from backend.scoring.scoring_engine import score


class _StubLLM:
    """Stand-in for LLMClient that always returns high, confident scores."""
    def rerank_profiles(self, seed_type, seed_value, persona, candidates):
        return [{"index": c["index"], "relevance": 90, "reason": "looks identical"}
                for c in candidates]

    def semantic_similarity_check(self, profile_a, profile_b, context=""):
        # Link only the 'gamma' singleton; 'delta' is high-relevance but not linked.
        if profile_a.get("username") == "gamma":
            return {"score": 95, "reason": "same person", "should_link": True}
        return {"score": 40, "reason": "unclear", "should_link": False}


def _setup(monkeypatch):
    monkeypatch.setattr(reranker, "LLMClient", _StubLLM)
    # Confirmed MEDIUM cluster: shared email (hard anchor, 60) + posting_hours (15) = 75,
    # two signals -> MEDIUM (not >75). Different usernames so no username_exact_match.
    p0 = make_profile("social_account", "alpha", "instagram", "u0",
                      {"email": "x@y.com", "posting_hours": [1, 2, 3]})
    p1 = make_profile("social_account", "beta", "twitter", "u1",
                      {"email": "x@y.com", "posting_hours": [1, 2, 3]})
    # Singleton the LLM will PROMOTE (no hard signal of its own).
    p2 = make_profile("social_account", "gamma", "github", "u2", {"bio": "loves crypto"})
    # Singleton the LLM rates highly but does NOT link.
    p3 = make_profile("social_account", "delta", "reddit", "u3", {"bio": "crypto investor"})
    profiles = [p0, p1, p2, p3]
    clusters = score(profiles, correlate(profiles))
    return profiles, clusters


def test_llm_promotion_does_not_upgrade_cluster_tier(monkeypatch):
    profiles, clusters = _setup(monkeypatch)
    # sanity: the base cluster is MEDIUM before reranking
    base = [c for c in clusters if 0 in c.member_indices and len(c.member_indices) >= 2][0]
    assert base.tier == "MEDIUM"

    new_clusters, promoted = reranker.rerank_and_promote("username", "alpha", profiles, clusters)

    assert 2 in promoted, "gamma should have been promoted for recall"
    merged = [c for c in new_clusters if 0 in c.member_indices and 2 in c.member_indices][0]
    # RECALL preserved (member added) but PRECISION preserved (tier NOT upgraded to HIGH)
    assert merged.tier == "MEDIUM", "LLM promotion must not upgrade the cluster tier"
    assert merged.confidence_score <= 75.0
    assert "semantic_rerank_match" in merged.signals  # recorded for transparency


def test_llm_relevance_does_not_confirm_a_singleton(monkeypatch):
    profiles, clusters = _setup(monkeypatch)
    new_clusters, promoted = reranker.rerank_and_promote("username", "alpha", profiles, clusters)

    # delta (idx 3) is rated relevance=90 by the LLM but was NOT linked.
    delta = [c for c in new_clusters if c.member_indices == [3]][0]
    # LLM relevance is a LEAD score only — it must not confirm an unlinked account.
    assert delta.tier in ("LOW", "REJECT"), "LLM relevance alone must not reach MEDIUM/HIGH"
    assert delta.confidence_score < 50.0
    # ...but the lead IS surfaced for the investigator to follow up.
    assert delta.relevance_score == 90


def test_exact_seed_match_ranks_first_and_preserves_score(monkeypatch):
    """REGRESSION: an exact seed match singleton (relevance_score=100) must rank #1
    ahead of any multi-member variant clusters and must not have its relevance_score overwritten."""
    monkeypatch.setattr(reranker, "LLMClient", _StubLLM)
    p0 = make_profile("social_account", "ash2903_var1", "twitter", "u0", {"phone": "+1234567890"})
    p1 = make_profile("social_account", "ash2903_var2", "reddit", "u1", {"phone": "+1234567890"})
    # p2 is exact seed match
    p2 = make_profile("social_account", "ash29_03", "instagram", "u2", {"username": "ash29_03"})
    p2.metadata["exact_seed_match"] = True
    profiles = [p0, p1, p2]
    seeds = [{"type": "username", "value": "ash29_03"}]
    clusters = score(profiles, correlate(profiles), seeds=seeds)
    new_clusters, _ = reranker.rerank_and_promote("username", "ash29_03", profiles, clusters)
    assert new_clusters[0].member_indices == [2], "Exact seed match must be sorted at rank #1"
    assert new_clusters[0].relevance_rank == 1
    assert new_clusters[0].relevance_score == 100, "Must preserve relevance_score=100"
