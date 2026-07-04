"""Tests for the dedicated, cross-both-paths LinkedIn search mechanism
(backend/pipeline/orchestrator.py's discover_real_names / linkedin_candidates /
linkedin_search) and the Serper num-cap fix it's built on
(backend/ingestion/serper_scraper.py).

Root cause this whole mechanism was built to work around (verified live,
deterministically reproducible — see serper_scraper.py's own comment): Serper's free
tier rejects ANY site:-scoped query with HTTP 400 whenever num > 10. Every site: dork
in this codebase (the entire "name" seed tool list, plus LinkedIn) was silently
returning zero results whenever this was hit, since SerperScraper hardcoded num=20.
"""
from backend.ingestion.base_module import make_profile
from backend.pipeline.orchestrator import (
    _linkedin_relevant, discover_real_names, linkedin_candidates, linkedin_search,
)


def _li(handle, title):
    return make_profile("web_mention", handle, "linkedin",
                        f"https://linkedin.com/in/{handle}", metadata={"title": title})


# ---- relevance filter (drops "merely mentions the target" noise) ----

def test_relevance_keeps_exact_handle_match():
    assert _linkedin_relevant("satyanadella", _li("satyanadella", "Satya Nadella - CEO at Microsoft - LinkedIn"))


def test_relevance_keeps_name_matching_the_owner_segment():
    assert _linkedin_relevant("Satya Nadella", _li("satya-nadella-b1566318", "Satya Nadella - Technical Support - LinkedIn"))


def test_relevance_keeps_handle_variant_for_a_name():
    # "Vismay HS" -> handle 'vismay-h-s' collapses to 'vismayhs' == candidate collapsed
    assert _linkedin_relevant("Vismay HS", _li("vismay-h-s", "Vismay H.S - Aspiring SOC Analyst - LinkedIn"))


def test_relevance_drops_profile_that_merely_mentions_the_name():
    # J.D. Meier's headline mentions Satya Nadella but HE is the profile owner -> drop
    assert not _linkedin_relevant("Satya Nadella", _li("jdmeier", "J.D. Meier - Satya Nadella's Former Head Coach - LinkedIn"))


def test_relevance_drops_unrelated_profile():
    assert not _linkedin_relevant("Satya Nadella", _li("rolfharms", "Rolf Harms - Corporate VP, AI Strategy - LinkedIn"))


# ---- linkedin_candidates ----

def test_linkedin_candidates_username_includes_raw_and_recovered_name():
    cands = linkedin_candidates("username", "vismayhs")
    assert "vismayhs" in cands
    assert "Vismay HS" in cands


def test_linkedin_candidates_name_seed_is_just_the_name():
    assert linkedin_candidates("name", "Vismay HS") == ["Vismay HS"]


def test_linkedin_candidates_includes_discovered_names_deduped():
    cands = linkedin_candidates("username", "vismayhs", discovered_names={"Vismay HS", "Someone Else"})
    lowered = [c.lower() for c in cands]
    assert lowered.count("vismay hs") == 1   # not duplicated even though it's both
                                              # the recovered guess AND a "discovered" name
    assert "someone else" in lowered


def test_linkedin_candidates_capped():
    many_names = {f"Person Number{i}" for i in range(20)}
    cands = linkedin_candidates("username", "vismayhs", discovered_names=many_names, cap=4)
    assert len(cands) <= 4


def test_linkedin_candidates_noise_handle_yields_no_recovered_name():
    # "a03" is a noise handle (orchestrator._NOISE_HANDLES) — no plausible name recovery,
    # so only the raw value itself is a candidate.
    assert linkedin_candidates("username", "a03") == ["a03"]


# ---- discover_real_names ----

def test_discover_real_names_extracts_from_legitimate_platform():
    p = make_profile("social_account", "vismayhs", "github", "https://github.com/vismayhs",
                     metadata={"fullname": "Vismay Real Person"})
    assert "Vismay Real Person" in discover_real_names([p])


def test_discover_real_names_ignores_non_legitimate_platform():
    p = make_profile("email_registration", "x@y.com", "some-random-breach-site", "https://x",
                     metadata={"name": "Should Not Count"})
    assert discover_real_names([p]) == set()


def test_discover_real_names_excludes_single_token_and_digit_bearing():
    p1 = make_profile("social_account", "a", "github", "u1", metadata={"fullname": "Solo"})
    p2 = make_profile("social_account", "b", "github", "u2", metadata={"fullname": "Name123 Two"})
    assert discover_real_names([p1, p2]) == set()


def test_discover_real_names_excludes_handle_echoed_as_name():
    p = make_profile("social_account", "john doe handle", "github", "u",
                     metadata={"fullname": "john doe handle"})
    assert discover_real_names([p]) == set()


# ---- linkedin_search (network-calling — only test the safe no-op path here; the
# actual live-network behavior is verified manually per serper_scraper.py's comment) ----

def test_linkedin_search_empty_candidates_is_a_safe_noop():
    import asyncio
    assert asyncio.run(linkedin_search([])) == []
