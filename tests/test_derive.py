"""Unit tests — backend/ingestion/derive.py (re-iteration / identifier cross-pivoting)."""
from backend.ingestion.derive import (
    derive_seeds,
    emails_from_handle,
    estimate_query_count,
    handles_from_name,
    names_from_handle,
)


def test_names_from_handle_separator_split():
    assert names_from_handle("vismay_hs") == ["Vismay Hs"]


def test_names_from_handle_opaque_prefix_split():
    assert names_from_handle("vismayhs") == ["Vismay HS"]


def test_names_from_handle_mononym_fallback():
    assert names_from_handle("ghostrider99") == ["Ghostrider"]


def test_names_from_handle_gibberish_returns_nothing():
    assert names_from_handle("xk3vzq99") == []


def test_names_from_handle_lone_common_first_name_returns_nothing():
    """A lone common first name isn't identifying evidence (is_generic_name) — even
    though "arjun" is itself a plausible name, it must not be surfaced as a "recovered"
    name guess on its own."""
    assert names_from_handle("arjun") == []


def test_emails_from_handle_five_providers():
    out = emails_from_handle("vismayhs")
    assert len(out) == 5
    assert "vismayhs@gmail.com" in out
    assert all(e.startswith("vismayhs@") for e in out)


def test_emails_from_handle_rejects_noise_handles():
    assert emails_from_handle("a03") == []   # in orchestrator's _NOISE_HANDLES
    assert emails_from_handle("ab") == []    # too short


def test_handles_from_name_reuses_username_variants():
    assert set(handles_from_name("Vismay HS")) >= {"vismay_hs", "vismay.hs"}


def test_derive_seeds_username_routes_to_email_name_and_handle_variants():
    derived = derive_seeds("username", "vismayhs")
    types = {d["type"] for d in derived}
    assert types == {"email", "name", "username"}
    strategies = {d["strategy"] for d in derived}
    assert "username_to_email_guess" in strategies
    assert "username_to_name_guess" in strategies
    assert "username_variant" in strategies
    # the recovered name itself
    assert any(d["type"] == "name" and d["value"] == "Vismay HS" for d in derived)
    # handle variants recombined THROUGH the recovered name, not the raw opaque blob
    variant_values = {d["value"] for d in derived if d["type"] == "username"}
    assert "vismay_hs" in variant_values
    assert "vismay.hs" in variant_values


def test_derive_seeds_name_routes_to_handle_variants_and_email_guess():
    derived = derive_seeds("name", "Vismay HS")
    types = {d["type"] for d in derived}
    assert "username" in types
    assert "email" in types
    handle_values = {d["value"] for d in derived if d["type"] == "username"}
    assert "vismayhs" in handle_values


def test_derive_seeds_email_treats_local_part_as_username():
    derived = derive_seeds("email", "vismayhs@gmail.com")
    assert any(d["type"] == "username" and d["value"] == "vismayhs"
              and d["strategy"] == "email_local_part" for d in derived)
    assert any(d["type"] == "name" and d["value"] == "Vismay HS" for d in derived)


def test_derive_seeds_never_reintroduces_the_original_value():
    derived = derive_seeds("username", "vismayhs")
    assert not any(d["value"].strip().lower() == "vismayhs" for d in derived)


def test_derive_seeds_noise_handle_is_a_safe_empty_result():
    assert derive_seeds("username", "a03") == []


def test_derive_seeds_unknown_type_returns_empty():
    assert derive_seeds("phone", "9876543210") == []
    assert derive_seeds("upi", "someone@upi") == []


def test_estimate_query_count_counts_query_bearing_types_only():
    derived = [
        {"type": "email", "value": "x@gmail.com"},
        {"type": "username", "value": "x"},
        {"type": "name", "value": "X Y"},
    ]
    assert estimate_query_count(derived) == 3
    assert estimate_query_count([]) == 0
