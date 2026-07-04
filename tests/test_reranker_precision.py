"""Precision + policy tests for the LLM reranker/adjudicator.

Policy (user-chosen): the LLM adjudicator MAY confirm a same-person link on its own, but:
  - a CONFIRM-strength verdict (P(same) >= 80) links the candidate AND tags the cluster
    `ai_confirmed` (so the UI/report label it "AI-assessed", distinct from hard evidence);
  - a softer positive (65-79) adds the member for recall but does NOT elevate tier/confidence;
  - batch-rerank RELEVANCE alone (no adjudication) never confirms an unlinked singleton.

The LLM is stubbed so the tests are deterministic and offline.
"""
import backend.analysis.adjudicator as adjudicator_mod
from backend.analysis import reranker
from backend.ingestion.base_module import make_profile
from backend.correlation.correlation_engine import correlate
from backend.scoring.scoring_engine import score


class _StubLLM:
    """Batch reranker returns high relevance for everything; adjudication is stubbed
    separately (via the adjudicate() function) so we control confirm vs promote vs reject."""
    def rerank_profiles(self, seed_type, seed_value, persona, candidates):
        return [{"index": c["index"], "relevance": 90, "reason": "looks identical"}
                for c in candidates]


def _stub_adjudicate(verdicts):
    """verdicts: {handle: (same_person, confidence)} -> a fake adjudicate()."""
    def _fake(anchor, candidate, shared_signals=None, llm=None):
        h = (candidate.get("username") or candidate.get("value") or "").lower()
        same, conf = verdicts.get(h, (False, 20))
        return {"same_person": same and conf >= 50, "confidence": conf, "reason": f"stub:{h}"}
    return _fake


def _setup(monkeypatch, verdicts):
    monkeypatch.setattr(reranker, "LLMClient", _StubLLM)
    monkeypatch.setattr(adjudicator_mod, "adjudicate", _stub_adjudicate(verdicts))
    # Confirmed MEDIUM cluster: shared email (hard anchor, 60) + posting_hours (15) = 75.
    p0 = make_profile("social_account", "alpha", "instagram", "u0",
                      {"email": "x@y.com", "posting_hours": [1, 2, 3]})
    p1 = make_profile("social_account", "beta", "twitter", "u1",
                      {"email": "x@y.com", "posting_hours": [1, 2, 3]})
    p2 = make_profile("social_account", "gamma", "github", "u2", {"bio": "loves crypto"})
    p3 = make_profile("social_account", "delta", "reddit", "u3", {"bio": "crypto investor"})
    profiles = [p0, p1, p2, p3]
    clusters = score(profiles, correlate(profiles))
    return profiles, clusters


def test_adjudicator_confirm_links_and_tags_ai_confirmed(monkeypatch):
    """A CONFIRM-strength verdict (P>=80) links the candidate and tags the cluster."""
    profiles, clusters = _setup(monkeypatch, {"gamma": (True, 90), "delta": (False, 20)})
    base = [c for c in clusters if 0 in c.member_indices and len(c.member_indices) >= 2][0]
    assert base.tier == "MEDIUM"

    new_clusters, promoted = reranker.rerank_and_promote("username", "alpha", profiles, clusters)

    assert 2 in promoted, "gamma should be linked by a confident adjudication"
    merged = [c for c in new_clusters if 0 in c.member_indices and 2 in c.member_indices][0]
    assert merged.ai_confirmed is True
    assert merged.ai_confidence == 90
    assert merged.tier == "HIGH", "a confirmed AI-assessed link elevates the match"
    assert "llm_same_person" in merged.signals


def test_soft_promotion_adds_member_but_does_not_elevate(monkeypatch):
    """A soft positive (65-79) adds the member for recall but keeps the deterministic tier."""
    profiles, clusters = _setup(monkeypatch, {"gamma": (True, 70), "delta": (False, 20)})
    new_clusters, promoted = reranker.rerank_and_promote("username", "alpha", profiles, clusters)

    assert 2 in promoted
    merged = [c for c in new_clusters if 0 in c.member_indices and 2 in c.member_indices][0]
    assert merged.ai_confirmed is False, "soft promotion must not tag ai_confirmed"
    assert merged.tier == "MEDIUM", "soft promotion must not elevate tier"
    assert merged.confidence_score <= 75.0


def test_relevance_alone_does_not_confirm_a_singleton(monkeypatch):
    """delta is rated relevance=90 by the batch reranker but the adjudicator rejects it —
    it must stay an unlinked LOW/REJECT lead, never confirmed on relevance alone."""
    profiles, clusters = _setup(monkeypatch, {"gamma": (True, 90), "delta": (False, 20)})
    new_clusters, promoted = reranker.rerank_and_promote("username", "alpha", profiles, clusters)

    assert 3 not in promoted
    delta = [c for c in new_clusters if c.member_indices == [3]][0]
    assert delta.tier in ("LOW", "REJECT")
    assert delta.confidence_score < 50.0
    assert delta.relevance_score == 90   # the lead is still surfaced


def test_exact_seed_match_ranks_first_and_preserves_score(monkeypatch):
    """REGRESSION: an exact seed match singleton (relevance_score=100) ranks #1."""
    monkeypatch.setattr(reranker, "LLMClient", _StubLLM)
    monkeypatch.setattr(adjudicator_mod, "adjudicate", _stub_adjudicate({}))
    p0 = make_profile("social_account", "ash2903_var1", "twitter", "u0", {"phone": "+1234567890"})
    p1 = make_profile("social_account", "ash2903_var2", "reddit", "u1", {"phone": "+1234567890"})
    p2 = make_profile("social_account", "ash29_03", "instagram", "u2", {"username": "ash29_03"})
    p2.metadata["exact_seed_match"] = True
    profiles = [p0, p1, p2]
    seeds = [{"type": "username", "value": "ash29_03"}]
    clusters = score(profiles, correlate(profiles), seeds=seeds)
    new_clusters, _ = reranker.rerank_and_promote("username", "ash29_03", profiles, clusters)
    assert new_clusters[0].member_indices == [2], "Exact seed match must be sorted at rank #1"
    assert new_clusters[0].relevance_rank == 1
    assert new_clusters[0].relevance_score == 100
