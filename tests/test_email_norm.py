"""Regression tests for _norm_email (correlation_engine.py) — Gmail/Googlemail ignore
dots in the local part and anything after a "+tag", so a guessed/derived email variant
of the seed's own address must still fire exact_email_match (a 60-pt hard anchor)."""
from backend.correlation.correlation_engine import _norm_email, correlate
from backend.ingestion.base_module import make_profile


def test_norm_email_strips_gmail_dots():
    assert _norm_email("Vismay.HS@gmail.com") == _norm_email("vismayhs@gmail.com")
    assert _norm_email("vismayhs@gmail.com") == "vismayhs@gmail.com"


def test_norm_email_strips_plus_tag():
    assert _norm_email("vismayhs+work@gmail.com") == "vismayhs@gmail.com"


def test_norm_email_normalizes_googlemail_alias():
    assert _norm_email("vismay.hs@googlemail.com") == _norm_email("vismayhs@gmail.com")


def test_norm_email_does_not_strip_dots_on_other_providers():
    """Only Gmail/Googlemail ignore dots — outlook.com etc. treat them as significant."""
    assert _norm_email("vismay.hs@outlook.com") != _norm_email("vismayhs@outlook.com")


def test_norm_email_empty_and_non_email_safe():
    assert _norm_email("") == ""
    assert _norm_email("not-an-email") == "not-an-email"


def test_exact_email_match_fires_across_gmail_dot_variants():
    a = make_profile("social_account", "acct-a", "github", "u1",
                     {"email": "vismay.hs@gmail.com"})
    b = make_profile("social_account", "acct-b", "instagram", "u2",
                     {"email": "vismayhs@gmail.com"})
    pairs = correlate([a, b])
    assert pairs and "exact_email_match" in pairs[0].signals


def test_exact_email_match_does_not_fire_for_different_addresses():
    a = make_profile("social_account", "acct-a", "github", "u1", {"email": "alice@gmail.com"})
    b = make_profile("social_account", "acct-b", "instagram", "u2", {"email": "bob@gmail.com"})
    pairs = correlate([a, b])
    assert not (pairs and "exact_email_match" in pairs[0].signals)
