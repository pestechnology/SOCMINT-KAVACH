"""Tests for the stealth-browser enrichment fallback (browser_fetch + enrich_via_browser).

The browser itself is never launched here — fetch_texts is monkeypatched to return canned
rendered text — so these are fast, deterministic, and offline. They pin the two contracts
that matter: (1) the pure helpers (email extraction + hard-host detection), and (2)
enrich_via_browser's target selection, metadata writes, bound, and fail-safe no-op.
"""
import asyncio

import backend.pipeline.orchestrator as orch
from backend.ingestion import browser_fetch as bf
from backend.ingestion.base_module import make_profile
from backend.pipeline.orchestrator import enrich_via_browser


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- pure helpers ---------------------------------------------------------

def test_extract_emails_keeps_real_drops_noise():
    text = ("Intro: madamexofmontecito@gmail.com  site kikiastor.com "
            "tracking noreply@facebook.com asset x@fbcdn.net monitor y@sentry.io")
    assert bf.extract_emails(text) == ["madamexofmontecito@gmail.com"]


def test_extract_emails_dedups_case_insensitively():
    assert bf.extract_emails("A@gmail.com then a@gmail.com again") == ["A@gmail.com"]


def test_extract_emails_empty():
    assert bf.extract_emails("") == []
    assert bf.extract_emails("no address here") == []


def test_is_hard_blocked_url():
    assert bf.is_hard_blocked_url("https://www.facebook.com/authorkikiastor/")
    assert bf.is_hard_blocked_url("https://m.facebook.com/x")
    assert not bf.is_hard_blocked_url("https://github.com/x")
    assert not bf.is_hard_blocked_url("")


# ---- enrich_via_browser ---------------------------------------------------

def _fb(url, meta=None):
    return make_profile("social_account", "kikiastor", "facebook", url, metadata=meta or {})


def _patch_browser(monkeypatch, available=True, texts=None, record=None):
    monkeypatch.setattr(bf, "browser_available", lambda: (available, "ok" if available else "no"))

    async def fake_fetch(urls, wait_ms=5000):
        if record is not None:
            record.extend(urls)
        return dict(texts or {})
    monkeypatch.setattr(bf, "fetch_texts", fake_fetch)


def test_writes_email_from_rendered_facebook_page(monkeypatch):
    url = "https://www.facebook.com/authorkikiastor/"
    _patch_browser(monkeypatch, texts={url: "Intro madamexofmontecito@gmail.com kikiastor.com"})
    profiles = [_fb(url)]
    n = _run(enrich_via_browser(profiles))
    assert n == 1
    assert profiles[0].metadata["email"] == "madamexofmontecito@gmail.com"
    assert profiles[0].metadata["browser_enriched"] is True


def test_noop_when_browser_unavailable_no_fetch(monkeypatch):
    called = []
    _patch_browser(monkeypatch, available=False, record=called)
    profiles = [_fb("https://www.facebook.com/x/")]
    assert _run(enrich_via_browser(profiles)) == 0
    assert called == []                       # never even tried to fetch
    assert "email" not in profiles[0].metadata


def test_skips_profiles_that_already_have_an_email(monkeypatch):
    called = []
    _patch_browser(monkeypatch, texts={}, record=called)
    profiles = [_fb("https://www.facebook.com/x/", {"email": "known@gmail.com"})]
    assert _run(enrich_via_browser(profiles)) == 0
    assert called == []                       # nothing to do → no browser launch
    assert profiles[0].metadata["email"] == "known@gmail.com"


def test_ignores_non_hard_blocked_hosts(monkeypatch):
    called = []
    _patch_browser(monkeypatch, texts={}, record=called)
    gh = make_profile("social_account", "x", "github", "https://github.com/x", metadata={})
    assert _run(enrich_via_browser([gh])) == 0
    assert called == []


def test_respects_cap(monkeypatch):
    called = []
    urls = [f"https://www.facebook.com/u{i}/" for i in range(6)]
    _patch_browser(monkeypatch, texts={u: "a@gmail.com" for u in urls}, record=called)
    profiles = [_fb(u) for u in urls]
    _run(enrich_via_browser(profiles, cap=3))
    assert len(called) == 3                    # only cap URLs fetched


def test_no_email_in_render_leaves_profile_untouched(monkeypatch):
    url = "https://www.facebook.com/x/"
    _patch_browser(monkeypatch, texts={url: "log in to continue"})
    profiles = [_fb(url)]
    assert _run(enrich_via_browser(profiles)) == 0
    assert "email" not in profiles[0].metadata


def test_orchestrator_reexports_enrich_via_browser():
    assert hasattr(orch, "enrich_via_browser")
