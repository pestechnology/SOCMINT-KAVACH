"""Regression tests for the Sprint 7 'more signal, more data' additions:
face_match, bio_url_match, employer_overlap, city_match, mutual_connections.

Every new signal must:
  (a) actually fire on real corroborating evidence,
  (b) NEVER fire on missing/empty data (no signal, not a false match),
  (c) respect its HARD_ANCHOR_SIGNALS / _CONTEXT_SIGNALS tier — a context-tier signal
      alone must never promote a cluster to HIGH (the single-signal red-herring cap
      already guarantees this structurally, verified here too for these signals
      specifically).
"""
from backend.correlation.correlation_engine import (
    correlate, extract_bio_urls, _face_match, _bio_links_to,
    _employer_overlap, _city_match, _mutual_connections, SIGNAL_WEIGHTS,
)
from backend.ingestion.base_module import make_profile
from backend.ingestion.url_scraper import extract_handle
from backend.scoring.scoring_engine import score, HARD_ANCHOR_SIGNALS, _CONTEXT_SIGNALS


# ---- face_match ----
def test_face_match_fires_on_close_embeddings():
    ma = {"face_embedding": [1.0, 0.0, 0.0]}
    mb = {"face_embedding": [0.99, 0.01, 0.0]}   # near-identical direction -> cosine ~1
    assert _face_match(ma, mb)


def test_face_match_rejects_dissimilar_embeddings():
    ma = {"face_embedding": [1.0, 0.0, 0.0]}
    mb = {"face_embedding": [0.0, 1.0, 0.0]}     # orthogonal -> cosine 0
    assert not _face_match(ma, mb)


def test_face_match_no_signal_when_embedding_absent():
    """REGRESSION: no embedding on either/both sides must be 'no signal', never a match."""
    assert not _face_match({}, {"face_embedding": [1.0, 0.0]})
    assert not _face_match({"face_embedding": [1.0, 0.0]}, {})
    assert not _face_match({}, {})


def test_face_match_is_hard_anchor():
    assert "face_match" in HARD_ANCHOR_SIGNALS


def test_face_match_alone_capped_low():
    """REGRESSION: even a hard-anchor face match, alone, must cap at LOW (red-herring rule)."""
    a = make_profile("social_account", "x", "p1", "u1", {"face_embedding": [1.0, 0.0, 0.0]})
    b = make_profile("social_account", "y", "p2", "u2", {"face_embedding": [0.99, 0.02, 0.0]})
    clusters = score([a, b], correlate([a, b]))
    assert all(c.tier in ("LOW", "REJECT") for c in clusters)


# ---- bio_url_match ----
def test_extract_bio_urls_finds_embedded_links():
    text = "Also on https://twitter.com/johndoe and check my site (http://example.com)."
    urls = extract_bio_urls(text)
    assert "https://twitter.com/johndoe" in urls
    assert any(u.startswith("http://example.com") for u in urls)


def test_extract_handle_matches_bio_url():
    assert extract_handle("https://twitter.com/johndoe") == ("twitter", "johndoe")


def test_bio_links_to_target_profile():
    target = make_profile("social_account", "johndoe", "twitter", "https://twitter.com/johndoe")
    assert _bio_links_to("Find me on https://twitter.com/johndoe too!", target)
    assert not _bio_links_to("Find me on https://twitter.com/someoneelse", target)
    assert not _bio_links_to("", target)


def test_bio_url_match_fires_in_pair_signals():
    a = make_profile("social_account", "jdoe", "github", "u1",
                     {"bio": "Also on https://twitter.com/johndoe"})
    b = make_profile("social_account", "johndoe", "twitter", "https://twitter.com/johndoe")
    pairs = correlate([a, b])
    assert pairs and "bio_url_match" in pairs[0].signals


def test_bio_url_match_is_hard_anchor():
    assert "bio_url_match" in HARD_ANCHOR_SIGNALS


# ---- employer_overlap / city_match ----
def test_employer_overlap_requires_exact_normalized_match():
    assert _employer_overlap({"employer_candidates": ["Acme Corp"]},
                             {"employer_candidates": ["acme corp"]})
    assert not _employer_overlap({"employer_candidates": ["Acme Corp"]},
                                 {"employer_candidates": ["Beta Inc"]})
    assert not _employer_overlap({}, {"employer_candidates": ["Acme Corp"]})


def test_city_match_distinct_from_location_overlap_field():
    """city_match reads location_candidates (NER from bio text), NOT the structured
    `location` field that location_overlap already reads — no duplicate signal firing
    on the same underlying data."""
    ma = {"location_candidates": ["Bangalore"]}
    mb = {"location": "Bangalore"}   # structured field only, no NER candidates
    assert not _city_match(ma, mb)   # must NOT match against the other field
    assert _city_match({"location_candidates": ["Bangalore"]},
                       {"location_candidates": ["bangalore"]})


def test_employer_and_city_are_context_tier_not_hard_anchor():
    assert "employer_overlap" not in HARD_ANCHOR_SIGNALS
    assert "city_match" not in HARD_ANCHOR_SIGNALS
    assert "employer_overlap" in _CONTEXT_SIGNALS
    assert "city_match" in _CONTEXT_SIGNALS


# ---- mutual_connections ----
def test_mutual_connections_below_threshold_is_no_signal():
    """REGRESSION: 1 shared follower is noise (common by chance), must not fire."""
    ma = {"followers_sample": ["alice", "bob"]}
    mb = {"followers_sample": ["alice", "carol"]}
    assert _mutual_connections(ma, mb) is None


def test_mutual_connections_weak_tier():
    ma = {"followers_sample": ["a", "b", "c"]}
    mb = {"followers_sample": ["a", "b", "x", "y"]}
    assert _mutual_connections(ma, mb) == 10


def test_mutual_connections_strong_tier_is_ceiling_weight():
    ma = {"followers_sample": ["a", "b", "c", "d", "e"]}
    mb = {"followers_sample": ["a", "b", "c", "d", "e", "f"]}
    assert _mutual_connections(ma, mb) == SIGNAL_WEIGHTS["mutual_connections"] == 20


def test_mutual_connections_is_context_tier():
    assert "mutual_connections" not in HARD_ANCHOR_SIGNALS
    assert "mutual_connections" in _CONTEXT_SIGNALS
