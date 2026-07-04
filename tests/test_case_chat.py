"""Tests for the grounded case-chat assistant (backend/analysis/case_chat.py).

The assistant must answer only from case data, degrade gracefully when the LLM is down,
and produce sensible suggested queries. LLM/DB are stubbed so tests are offline+deterministic.
"""
import backend.analysis.case_chat as cc
from backend.analysis.case_chat import build_context, suggested_queries, answer


def _case():
    return {"case_id": "c1", "seeds": [{"type": "username", "value": "arjun"}], "country_filter": "ALL"}


def _ent(eid, value, platform, etype="social_account", meta=None):
    return {"entity_id": eid, "value": value, "platform": platform, "type": etype, "metadata": meta or {}}


def _cluster(eids, match="HIGH", identity=None, signals=None, expl=""):
    return {"entity_ids": eids, "match": {"tier": match, "score": 100 if match == "HIGH" else 55},
            "tier": match, "identity": identity or {}, "signals": signals or {}, "explanation": expl}


def test_build_context_includes_case_facts():
    ents = [_ent("e1", "arjun", "github"),
            _ent("e2", "arjun", "reddit", meta={"email": "a@b.com", "location": "Bengaluru"})]
    cl = [_cluster(["e1", "e2"], identity={"name": "Arjun K"}, signals={"exact_email_match": 60},
                   expl="They share the same email.")]
    ctx = build_context(_case(), ents, cl, {})
    assert "arjun" in ctx.lower()
    assert "a@b.com" in ctx
    assert "Bengaluru" in ctx
    assert "Arjun K" in ctx
    assert "CONFIRMED" in ctx


def test_suggested_queries_are_relevant():
    ents = [_ent("e1", "arjun", "github", meta={"phone": "+9111"}),
            _ent("e2", "arjun", "reddit", meta={"location": "Delhi"})]
    cl = [_cluster(["e1", "e2"])]
    qs = suggested_queries(_case(), ents, cl)
    assert 3 <= len(qs) <= 6
    assert any("phone" in q.lower() or "email" in q.lower() for q in qs)
    assert any("location" in q.lower() for q in qs)
    assert len(qs) == len(set(qs))  # no duplicates


def test_answer_grounded_via_nvidia(monkeypatch):
    monkeypatch.setattr(cc, "_chat_nvidia", lambda msgs, timeout=30.0: "Yes — see github/arjun.")
    monkeypatch.setattr("backend.cases.case_service.get_results",
                        lambda cid, uid: {"case": _case(), "entities": [_ent("e1", "arjun", "github")],
                                          "clusters": [], "forensics": {}})
    res = answer("c1", "u1", "who is the subject?")
    assert res["grounded"] is True
    assert "github/arjun" in res["answer"]


def test_answer_passes_history_and_context(monkeypatch):
    captured = {}
    def _stub(msgs, timeout=30.0):
        captured["msgs"] = msgs
        return "ok"
    monkeypatch.setattr(cc, "_chat_nvidia", _stub)
    monkeypatch.setattr("backend.cases.case_service.get_results",
                        lambda cid, uid: {"case": _case(), "entities": [_ent("e1", "arjun", "github")],
                                          "clusters": [], "forensics": {}})
    answer("c1", "u1", "follow up", history=[{"role": "user", "content": "hi"},
                                             {"role": "assistant", "content": "hello"}])
    roles = [m["role"] for m in captured["msgs"]]
    assert roles[0] == "system" and "CASE DATA" in captured["msgs"][0]["content"]
    assert "hi" in [m["content"] for m in captured["msgs"]]
    assert captured["msgs"][-1]["content"] == "follow up"


def test_answer_empty_question():
    res = answer("c1", "u1", "   ")
    assert res["grounded"] is False


def test_answer_deterministic_fallback_when_llm_down(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("no llm")
    monkeypatch.setattr(cc, "_chat_nvidia", _raise)
    import backend.llm.llm_client as llm
    monkeypatch.setattr(llm.LLMClient, "_chat_with_failover",
                        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr("backend.cases.case_service.get_results",
                        lambda cid, uid: {"case": _case(), "entities": [_ent("e1", "arjun", "github")],
                                          "clusters": [], "forensics": {}})
    res = answer("c1", "u1", "summarise the case")
    assert res["grounded"] is False
    assert "SEARCH SEED" in res["answer"] or "case data" in res["answer"].lower()


def test_answer_missing_case(monkeypatch):
    monkeypatch.setattr("backend.cases.case_service.get_results", lambda cid, uid: None)
    res = answer("nope", "u1", "hi")
    assert res["grounded"] is False
    assert "could not be found" in res["answer"].lower()
