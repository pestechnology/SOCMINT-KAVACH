"""Regression tests for first-pass username seed permutations (orchestrator).

The bug: an inline permutation engine treated the numeric tail of a handle as a "surname"
and emitted first-initial + tail — turning the seed "ash29_03" into "a03", a 3-char noise
handle that pulled in 33 unrelated accounts via the full Sherlock/Maigret scan. The initial-
based permutation must only apply to real alphabetic name tokens.
"""
from backend.pipeline.orchestrator import _username_seed_permutations, _is_valid_expansion_handle


def test_ash29_03_does_not_produce_a03():
    perms = _username_seed_permutations("ash29_03")
    assert "a03" not in perms, "handle+number split must not yield the 'a03' noise handle"
    # the safe concatenation/separator variants are still produced
    assert "ash2903" in perms
    assert "ash29.03" in perms


def test_numeric_tail_never_makes_initial_handle():
    # "ashwin_2003" -> must NOT produce "a2003" (initial + number)
    assert "a2003" not in _username_seed_permutations("ashwin_2003")
    # "b12" style is invalid regardless
    assert not _is_valid_expansion_handle("a03")
    assert not _is_valid_expansion_handle("b12")


def test_real_name_handle_keeps_initial_permutation():
    perms = _username_seed_permutations("arjun_mehta")
    assert "amehta" in perms, "real first+last name should still yield the initial form"
    assert "arjunmehta" in perms
    assert "arjun.mehta" in perms


def test_single_token_yields_nothing():
    assert _username_seed_permutations("ghostrider99") == []
    assert _username_seed_permutations("") == []


def test_all_permutations_pass_validity_gate():
    for seed in ("ash29_03", "arjun_mehta", "j.shankar", "a_b", "x99_03"):
        for p in _username_seed_permutations(seed):
            assert _is_valid_expansion_handle(p), f"{p!r} from {seed!r} should be a valid handle"
