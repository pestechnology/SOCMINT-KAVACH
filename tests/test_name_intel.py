"""Tests for name_intel: fake-name detection, common-name guard, leak-account pivot."""
from backend.analysis.name_intel import (
    is_plausible_name, is_generic_name, resolve_cluster_identity,
)


# ---- #1a: gibberish / fake display-name detection --------------------------------
def test_real_names_are_plausible():
    for n in ["Ashwin Harish", "Vismay H S", "The Octocat", "Dhanush Shankar Reddy",
              "Sarah", "Jean-Luc Picard"]:
        assert is_plausible_name(n), n


def test_gibberish_names_are_rejected():
    for n in ["xk3vzq", "xkvzq", "asdfgh", "qwerty", "zzzzzz", "bcdfgh", "jbczxqyzsu"]:
        assert not is_plausible_name(n), n


def test_names_with_digits_rejected():
    # Usernames leak into the name field as "ash29_03" — not a human name.
    assert not is_plausible_name("ash29_03")
    assert not is_plausible_name("user12345")


def test_non_latin_names_accepted():
    # The pronounceability heuristic is Latin-specific; don't reject other scripts.
    assert is_plausible_name("अश्विन हरीश")   # Devanagari
    assert is_plausible_name("Владимир")       # Cyrillic


# ---- #1b: common-name / placeholder guard ----------------------------------------
def test_placeholder_and_lone_common_first_name_are_generic():
    assert is_generic_name("John Doe")
    assert is_generic_name("test user")
    assert is_generic_name("Ashwin")           # lone common first name
    assert is_generic_name("john")


def test_distinctive_full_name_is_not_generic():
    assert not is_generic_name("Ashwin Harish")
    assert not is_generic_name("Vismay H S")


# ---- #2: leak-account pivot (cluster identity propagation) ------------------------
def _ent(platform, name=None, anchor=False):
    m = {}
    if name:
        m["name"] = name
    if anchor:
        m["exact_seed_match"] = True
    return {"platform": platform, "metadata": m}


def test_leak_pivot_lifts_real_name_from_one_member():
    # The anchor (gibberish handle) has no name; an old GitHub leaked "Ashwin Harish".
    members = [_ent("instagram", anchor=True), _ent("threads"),
               _ent("github", name="Ashwin Harish")]
    ident = resolve_cluster_identity(members)
    assert ident and ident["name"] == "Ashwin Harish"
    assert ident["source_platform"] == "github"


def test_leak_pivot_ignores_gibberish_and_generic_names():
    members = [_ent("x", name="xk3vzq"), _ent("reddit", name="John Doe"),
               _ent("steam", name="Ashwin")]
    # all members carry only gibberish / placeholder / lone-common-first names
    assert resolve_cluster_identity(members) is None


def test_leak_pivot_prefers_more_supported_name():
    members = [_ent("github", name="Ashwin Harish"), _ent("gitlab", name="Ashwin Harish"),
               _ent("medium", name="Ashwin C H")]
    ident = resolve_cluster_identity(members)
    assert ident["name"] == "Ashwin Harish"      # appears on 2 members, wins
    assert ident["support"] == 2


def test_leak_pivot_empty_when_no_names():
    assert resolve_cluster_identity([_ent("x"), _ent("y")]) is None
    assert resolve_cluster_identity([]) is None
