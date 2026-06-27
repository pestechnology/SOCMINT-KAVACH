"""Unit + resilience tests — UPI parser, LLM fallbacks, scrapers fail-safe, config."""
import asyncio

from backend.ingestion.base_module import BaseDataSource, make_profile
from backend.ingestion.upi_module import UPIScraper, parse_upi
from backend.llm.llm_client import LLMClient, _regex_entities, _template_explanation


# ---- UPI parser ----
def test_upi_bank_map():
    assert parse_upi("arjun@oksbi")["bank"] == "State Bank of India"
    assert parse_upi("x@okhdfcbank")["bank"] == "HDFC Bank"


def test_upi_invalid():
    assert parse_upi("notaupi")["valid"] is False
    assert parse_upi("")["valid"] is False


def test_upi_embedded_phone():
    info = parse_upi("9876543210@ybl")
    assert info["embedded_phone"] == "9876543210"


def test_upi_scraper_emits_cascade_username():
    out = asyncio.run(UPIScraper().resolve("arjun.trades@oksbi", "live"))
    assert any(p.type == "username" and p.metadata.get("cascade") for p in out)


# ---- LLM fallbacks (resilience: no key / API down) ----
def test_regex_fallback_extracts():
    ents = _regex_entities("reach arjun@gmail.com or +91 98765 43210")
    types = {e["type"] for e in ents}
    assert "email" in types and "phone" in types


def test_regex_no_upi_false_positive():
    """REGRESSION: 'arjun@gmail' must not be extracted as UPI from an email."""
    ents = _regex_entities("email arjun@gmail.com")
    assert not any(e["type"] == "upi" for e in ents)


def test_template_explanation():
    txt = _template_explanation(["exact_phone_match", "profile_photo_phash"], "HIGH")
    assert "phone" in txt and "strongly" in txt


def test_llm_methods_never_raise_without_key():
    c = LLMClient(); c.api_key = ""  # force fallback
    assert isinstance(c.extract_entities("arjun@x.com"), list)
    assert isinstance(c.explain_match(["exact_phone_match"], "HIGH"), str)
    assert c.summarize_case({"x": 1}) == ""


def test_extract_entities_empty():
    c = LLMClient(); c.api_key = ""
    assert c.extract_entities("") == []
    assert c.extract_entities("   ") == []


# ---- scraper fail-safe contract ----
class _Boom(BaseDataSource):
    name = "boom"
    async def _run_live(self, identifier):
        raise RuntimeError("simulated scraper crash")


def test_scraper_failure_returns_empty_not_raise():
    """Fail-safe: a crashing scraper returns [] so the batch never dies."""
    out = asyncio.run(_Boom().resolve("anything", "live"))
    assert out == []


def test_make_profile_hash_deterministic():
    a = make_profile("t", "v", "p", "u")
    b = make_profile("t", "v", "p", "u")
    assert a.sha256 == b.sha256 and len(a.sha256) == 64


# ---- config resilience: missing keys must not crash ----
def test_validate_keys_no_crash():
    import backend.config as config
    result = config.validate_keys()  # must not raise even with keys missing
    assert "missing_required" in result
