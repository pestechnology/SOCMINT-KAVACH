"""Anchor-keyword booster: rarity weighting must defeat the common-name trap.

The booster only ROUTES candidates to the LLM adjudicator; it must never let a stranger
who merely shares a common first name (or a generic interest) score enough to be surfaced,
while a candidate sharing the anchor's DISTINCTIVE terms (rare handle / employer / city)
must surface.
"""
from backend.analysis.anchor_keywords import build_anchor_keywords, score_candidate
from backend.ingestion.base_module import make_profile


def _case():
    anchor = make_profile("social_account", "ash29_03", "instagram", "https://instagram.com/ash29_03",
                          {"username": "ash29_03", "name": "Ashwin Harish",
                           "bio": "AI intern @GreyWiz, Kozhikode", "exact_seed_match": True})
    filler = [make_profile("social_account", f"user{i}", "site", f"u{i}",
                           {"bio": "gaming and music lover"}) for i in range(10)]
    return anchor, filler


def test_common_first_name_does_not_surface():
    anchor, filler = _case()
    stranger = make_profile("social_account", "ashwin_gaming", "twitch", "u",
                            {"bio": "just a gamer named ashwin who loves music"})
    kws = build_anchor_keywords([anchor, stranger] + filler)
    # 'ashwin' and 'harish' (common names) and 'gaming'/'music' (generic) must NOT be anchor keywords
    kw_set = {k for k, _ in kws}
    assert "ashwin" not in kw_set
    assert "gaming" not in kw_set and "music" not in kw_set
    score, matched = score_candidate(stranger.metadata["bio"], kws)
    assert score == 0.0 and matched == [], "a common-name-only stranger must never surface"


def test_distinctive_terms_surface():
    anchor, filler = _case()
    realmatch = make_profile("social_account", "harish_dev", "github", "u2",
                             {"bio": "Ashwin Harish - building at GreyWiz, from Kozhikode"})
    kws = build_anchor_keywords([anchor, realmatch] + filler)
    score, matched = score_candidate(realmatch.metadata["bio"], kws)
    assert score >= 2.0, "a candidate sharing rare employer/city terms must surface"
    assert "kozhikode" in matched or "greywiz" in matched


def test_no_anchor_returns_empty():
    # No exact_seed_match anchor -> booster is inert (never affects a run without an anchor).
    profiles = [make_profile("social_account", f"u{i}", "site", f"x{i}", {"bio": "hello"}) for i in range(6)]
    assert build_anchor_keywords(profiles) == []
    assert score_candidate("anything", []) == (0.0, [])
