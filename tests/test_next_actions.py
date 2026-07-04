"""Tests for the officer 'what to do next' recommender (backend/analysis/next_actions.py).

The deterministic baseline must always produce useful, well-formed actions (so the feature
survives the LLM being rate-limited), and the LLM path must never crash the pipeline.
"""
from backend.analysis import next_actions as na
from backend.analysis.next_actions import deterministic_actions, recommend, _norm_action


def _case(seeds=None, country="ALL", status="complete"):
    return {"case_id": "c1", "seeds": seeds or [{"type": "username", "value": "ghost_rider99"}],
            "country_filter": country, "status": status}


def _ent(eid, value, platform, etype="social_account", meta=None, url=""):
    return {"entity_id": eid, "value": value, "platform": platform, "type": etype,
            "metadata": meta or {}, "source_url": url, "confidence": 0}


def _cluster(eids, match_tier="LOW", tier="LOW", identity=None):
    return {"entity_ids": eids, "match": {"tier": match_tier}, "tier": tier,
            "identity": identity or {}}


# ---- normalization ----
def test_norm_action_clamps_and_defaults():
    a = _norm_action({"title": "Do X", "priority": "urgent", "action": "nope", "target": "t"})
    assert a["priority"] == "medium"          # invalid priority -> medium
    assert a["action"] == "manual_review"     # unknown tag -> manual_review
    assert a["title"] == "Do X"

def test_norm_action_rejects_titleless():
    assert _norm_action({"detail": "no title"}) is None
    assert _norm_action("not a dict") is None


# ---- deterministic baseline ----
def test_medium_lead_yields_fetch_profile():
    ents = [_ent("e1", "ghost_rider99", "instagram", url="https://instagram.com/ghost_rider99")]
    clusters = [_cluster(["e1"], match_tier="MEDIUM")]
    acts = deterministic_actions(_case(), ents, clusters)
    assert any(a["action"] == "fetch_profile" for a in acts)


def test_discovered_email_yields_breach_lookup():
    ents = [
        _ent("e1", "ghost_rider99", "github", url="https://github.com/ghost_rider99"),
        _ent("e2", "leaked@example.com", "email", etype="email", meta={"email": "leaked@example.com"}),
    ]
    clusters = [_cluster(["e1", "e2"], match_tier="HIGH", tier="HIGH")]
    acts = deterministic_actions(_case(), ents, clusters)
    breach = [a for a in acts if a["action"] == "breach_lookup"]
    assert breach and "leaked@example.com" in breach[0]["target"]


def test_seed_identifier_not_recommended_as_pivot():
    """The email the officer already searched must not be suggested back as a 'new' pivot."""
    ents = [_ent("e1", "seed@example.com", "email", etype="email", meta={"email": "seed@example.com"})]
    clusters = [_cluster(["e1"], match_tier="LOW")]
    case = _case(seeds=[{"type": "email", "value": "seed@example.com"}])
    acts = deterministic_actions(case, ents, clusters)
    assert not any(a["action"] == "breach_lookup" and "seed@example.com" in a["target"] for a in acts)


def test_few_accounts_suggests_agentic_lookup():
    ents = [_ent("e1", "x", "instagram")]
    clusters = [_cluster(["e1"], match_tier="LOW")]
    acts = deterministic_actions(_case(), ents, clusters)
    assert any(a["action"] == "agentic_lookup" for a in acts)


def test_recovered_name_yields_records_search():
    ents = [_ent("e1", "gr99", "github"), _ent("e2", "gr_99", "reddit")]
    clusters = [_cluster(["e1", "e2"], match_tier="HIGH", tier="HIGH",
                         identity={"name": "Sushil Kumar"})]
    acts = deterministic_actions(_case(), ents, clusters)
    rec = [a for a in acts if a["action"] == "records_search"]
    assert rec and "Sushil Kumar" in rec[0]["target"]


def test_actions_are_ranked_and_capped():
    ents = [
        _ent("e1", "gr99", "instagram", url="https://instagram.com/gr99"),
        _ent("e2", "a@b.com", "email", etype="email", meta={"email": "a@b.com"}),
        _ent("e3", "gr99", "github", meta={"photo_url": "https://x/y.jpg"}),
    ]
    clusters = [_cluster(["e1"], match_tier="MEDIUM"),
                _cluster(["e2", "e3"], match_tier="HIGH", tier="HIGH")]
    acts = deterministic_actions(_case(), ents, clusters)
    ranks = [ {"high": 0, "medium": 1, "low": 2}[a["priority"]] for a in acts ]
    assert ranks == sorted(ranks), "actions must be ordered by priority"
    assert len(acts) <= 6


# ---- full recommend() with a stubbed LLM ----
class _StubLLM:
    def _chat_with_failover(self, model, messages, temperature=0.0, max_tokens=0):
        return ('[{"priority":"high","action":"fetch_profile","title":"LLM says fetch",'
                '"detail":"because reasons","target":"https://x/y"}]')


def test_recommend_merges_llm_and_deterministic(monkeypatch):
    ents = [_ent("e1", "gr99", "instagram", url="https://instagram.com/gr99")]
    clusters = [_cluster(["e1"], match_tier="MEDIUM")]
    na._CACHE.clear()
    out = recommend(_case(), ents, clusters, llm=_StubLLM(), use_cache=False)
    assert any(a["title"] == "LLM says fetch" for a in out)
    assert len(out) <= 5
    assert all(a["action"] in na._ACTION_TAGS for a in out)


def test_recommend_never_raises_on_bad_llm(monkeypatch):
    class _BadLLM:
        def _chat_with_failover(self, *a, **k):
            raise RuntimeError("429 rate limited")
    ents = [_ent("e1", "gr99", "github", url="https://github.com/gr99")]
    clusters = [_cluster(["e1"], match_tier="MEDIUM")]
    na._CACHE.clear()
    out = recommend(_case(), ents, clusters, llm=_BadLLM(), use_cache=False)
    assert isinstance(out, list) and len(out) >= 1  # deterministic baseline survives
