"""Tests for name_cross_platform_search — the post-enrichment pass that searches
Facebook/Twitter/Instagram BY a real name recovered from an enriched profile.

Regression context: a username seed (e.g. an Instagram handle "kikiastor") for a
well-known person recovered the real name ("Kiki Astor") only AFTER the profile page was
enriched — but the pre-enrichment step-3.5 name pivot had already run, so that name never
drove a Facebook/cross-platform search and a separate real-name Facebook account went
undiscovered. This function is the fix; these tests pin its contract.
"""
import asyncio

import backend.pipeline.orchestrator as orch
from backend.ingestion.base_module import make_profile
from backend.pipeline.orchestrator import name_cross_platform_search


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeSerper:
    """Stand-in for SerperScraper: returns canned hits per query template so the tests
    never touch the network. Records which (template, name) pairs were queried."""
    calls: list[tuple[str, str]] = []
    responses: dict[str, list] = {}

    def __init__(self, query_template='"{q}"', sensitive=False):
        self.query_template = query_template

    async def resolve(self, identifier, mode):
        _FakeSerper.calls.append((self.query_template, identifier))
        return list(_FakeSerper.responses.get(self.query_template, []))


def _fb(handle, url):
    return make_profile("web_mention", handle, "facebook", url, metadata={})


def _setup(monkeypatch, responses):
    _FakeSerper.calls = []
    _FakeSerper.responses = responses
    monkeypatch.setattr(orch, "SerperScraper", _FakeSerper)


def test_empty_names_is_a_noop_no_network(monkeypatch):
    _setup(monkeypatch, {})
    out = _run(name_cross_platform_search(set()))
    assert out == []
    assert _FakeSerper.calls == []          # not a single Serper call


def test_finds_facebook_by_name(monkeypatch):
    _setup(monkeypatch, {
        'site:facebook.com "{q}"': [_fb("kiki.astor", "https://facebook.com/kiki.astor")],
    })
    out = _run(name_cross_platform_search({"Kiki Astor"}))
    urls = [p.source_url for p in out]
    assert "https://facebook.com/kiki.astor/" in urls  # canonicalized (trailing slash)
    # every template was tried for the name
    assert ('site:facebook.com "{q}"', "Kiki Astor") in _FakeSerper.calls


def test_provenance_tag_set_and_name_not_stamped(monkeypatch):
    """A name search must NOT stamp metadata['name'] (would false-cluster namesakes via
    exact_name_match); it records found_via_name_search instead."""
    _setup(monkeypatch, {
        'site:facebook.com "{q}"': [_fb("kiki.astor", "https://facebook.com/kiki.astor")],
    })
    out = _run(name_cross_platform_search({"Kiki Astor"}))
    p = next(p for p in out if p.source_url == "https://facebook.com/kiki.astor/")
    assert p.metadata.get("found_via_name_search") == "Kiki Astor"
    assert "name" not in p.metadata
    assert "seed_name" not in p.metadata


def test_skips_urls_already_in_case(monkeypatch):
    _setup(monkeypatch, {
        'site:facebook.com "{q}"': [_fb("kikiastor", "https://facebook.com/kikiastor")],
    })
    # already discovered by the handle enumerator — don't re-add it
    out = _run(name_cross_platform_search(
        {"Kiki Astor"}, already_urls={"https://facebook.com/kikiastor"}))
    assert out == []


def test_dedups_same_url_across_names(monkeypatch):
    _setup(monkeypatch, {
        'site:twitter.com "{q}"': [_fb("shared", "https://twitter.com/shared")],
    })
    out = _run(name_cross_platform_search({"Kiki Astor", "Aljonchik Mi"}))
    assert [p.source_url for p in out].count("https://twitter.com/shared/") == 1


def test_cap_names_bounds_the_query_fanout(monkeypatch):
    _setup(monkeypatch, {})
    names = {f"Person {i} Name" for i in range(10)}
    _run(name_cross_platform_search(names, cap_names=2))
    # only cap_names distinct names searched, across the 3 dork templates each
    searched = {n for _, n in _FakeSerper.calls}
    assert len(searched) == 2


def test_cap_per_name_bounds_results(monkeypatch):
    many = [_fb(f"h{i}", f"https://facebook.com/h{i}") for i in range(10)]
    _setup(monkeypatch, {'site:facebook.com "{q}"': many})
    out = _run(name_cross_platform_search({"Kiki Astor"}, cap_per_name=3))
    assert len(out) == 3


def test_recovers_account_from_post_and_video_urls_deduped(monkeypatch):
    """A name search often surfaces a specific /videos/ or /about/ page rather than the
    profile root (this is what made Facebook flaky). Those must be CANONICALIZED to the
    account root and deduped to a single entity — not discarded."""
    _setup(monkeypatch, {
        'site:facebook.com "{q}"': [
            _fb("vid", "https://www.facebook.com/authorkikiastor/videos/who-knew/1564894051267637/"),
            _fb("about", "https://www.facebook.com/authorkikiastor/about/"),
            _fb("vid2", "https://www.facebook.com/authorkikiastor/videos/origin/1894175148033994/"),
        ],
    })
    out = _run(name_cross_platform_search({"Kiki Astor"}))
    urls = [p.source_url for p in out]
    assert urls == ["https://www.facebook.com/authorkikiastor/"]   # one account, recovered


def test_instagram_post_and_twitter_status(monkeypatch):
    """instagram.com/p/{code} names no account → dropped; twitter status → account root."""
    _setup(monkeypatch, {
        'site:instagram.com "{q}"': [_fb("post", "https://instagram.com/p/ABC123/")],
        'site:twitter.com "{q}"': [_fb("tweet", "https://twitter.com/kiki/status/999")],
    })
    out = _run(name_cross_platform_search({"Kiki Astor"}))
    assert [p.source_url for p in out] == ["https://twitter.com/kiki/"]


def test_skips_account_already_in_case_across_url_shapes(monkeypatch):
    """An enumerator's facebook.com/{handle} and a name-search facebook.com/{handle}/videos
    are the same account — the name search must not re-add it."""
    _setup(monkeypatch, {
        'site:facebook.com "{q}"': [_fb("v", "https://www.facebook.com/kiki/videos/1/")],
    })
    out = _run(name_cross_platform_search(
        {"Kiki Astor"}, already_urls={"https://www.facebook.com/kiki"}))
    assert out == []


# ---- noise-platform filter (op.gg / League of Legends) --------------------

def test_dedup_drops_opgg_league_of_legends_noise():
    """Maigret emits op.gg/summoners/search?q={u} as ~15 regional 'accounts' that are just
    a search URL — permanently excluded as noise."""
    from backend.pipeline.orchestrator import _dedup
    keep = make_profile("social_account", "kiki", "instagram", "https://instagram.com/kiki")
    noise1 = make_profile("social_account", "kiki", "op.gg [leagueoflegends] korea",
                          "https://www.op.gg/summoners/search?q=kiki&region=kr")
    noise2 = make_profile("social_account", "kiki", "op.gg [leagueoflegends] brazil",
                          "https://www.op.gg/summoners/search?q=kiki&region=br")
    out = _dedup([keep, noise1, noise2])
    plats = [p.platform for p in out]
    assert "instagram" in plats
    assert not any("op.gg" in p or "leagueoflegends" in p for p in plats)


def test_canonical_profile_url_rejects_non_profiles():
    from backend.pipeline.orchestrator import _canonical_profile_url as f
    assert f("https://www.facebook.com/profile.php?id=100093") == "https://www.facebook.com/profile.php?id=100093"
    assert f("https://instagram.com/p/ABC/") is None
    assert f("https://www.facebook.com/watch/?v=1") is None
    assert f("https://twitter.com/i/lists/5") is None
    assert f("not-a-url") is None
