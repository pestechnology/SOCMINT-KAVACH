"""Regression test — a WhatsMyName-style enumerator hit (Maigret/Sherlock finding
e.g. gist.github.com/{user}) and a direct-API profile fetch (GitHubScraper finding the
real github.com/{user} page) canonicalize to the SAME (platform, value) key in
orchestrator._dedup(). The enumerator's URL must never win just because it happened to
be scraped first (an accident of tool-list ordering) once the authoritative source's
own profile URL is available.
"""
from backend.ingestion.base_module import make_profile
from backend.pipeline.orchestrator import _dedup


def _gist_hit():
    # A realistic enumerator hit: existence-check tools like Maigret/Sherlock don't
    # extract page content, so no bio/name — just confirms the account exists.
    return make_profile("social_account", "vismayhs", "github",
                        "https://gist.github.com/vismayhs", metadata={})


def _real_profile_hit():
    return make_profile("social_account", "vismayhs", "github",
                        "https://github.com/VismayHS",
                        metadata={"bio": "real bio", "name": "Vismay HS", "_authoritative_url": True})


def test_authoritative_url_wins_when_it_arrives_second():
    # enumerator hit scraped first (matches real tool-list ordering: Maigret/Sherlock
    # run before GitHubScraper), authoritative profile arrives after
    out = _dedup([_gist_hit(), _real_profile_hit()])
    assert len(out) == 1
    assert out[0].source_url == "https://github.com/VismayHS"


def test_authoritative_url_wins_when_it_arrives_first():
    # authoritative hit already present; a later enumerator hit for the same
    # platform/handle must NOT overwrite it
    out = _dedup([_real_profile_hit(), _gist_hit()])
    assert len(out) == 1
    assert out[0].source_url == "https://github.com/VismayHS"


def test_metadata_still_merges_regardless_of_url_winner():
    """The pre-existing per-field metadata merge (fill gaps, never overwrite a
    non-empty existing value) is UNCHANGED by this fix — only source_url selection
    gained the authoritative-source override."""
    out = _dedup([_gist_hit(), _real_profile_hit()])
    assert out[0].metadata.get("name") == "Vismay HS"
    assert out[0].metadata.get("bio") == "real bio"


def test_two_non_authoritative_hits_keep_first_url_as_before():
    """Unchanged behavior for the common case — neither source is authoritative,
    so the original fill-if-empty rule still applies (first URL wins, not overwritten)."""
    a = make_profile("social_account", "x", "twitter", "https://twitter.com/x", metadata={"bio": "a"})
    b = make_profile("social_account", "x", "twitter", "https://x.com/x", metadata={"bio": "b"})
    out = _dedup([a, b])
    assert len(out) == 1
    assert out[0].source_url == "https://twitter.com/x"
