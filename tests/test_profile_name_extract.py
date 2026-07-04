"""Regression tests for profile-page name extraction (backend/ingestion/profile_page_fetcher).

The real-world bug: Instagram/Threads serve the display name inside an og:title whose
special characters are HTML-entity-encoded — e.g.

    <meta property="og:title" content="Ashwin Harish (&#064;ash29_03) &#x2022; Instagram photos and videos">

`&#064;` is '@' and `&#x2022;` is '•'. The name-shape regexes match on a literal '@'/'•',
so without decoding the entities first, extraction silently returns None and the real
name ("Ashwin Harish") never reaches the Names panel. These tests pin the decode.
"""
from backend.ingestion.profile_page_fetcher import _extract


def _og_title(content: str) -> str:
    return f'<html><head><meta property="og:title" content="{content}"></head></html>'


def test_instagram_entity_encoded_title_yields_real_name():
    html = _og_title("Ashwin Harish (&#064;ash29_03) &#x2022; Instagram photos and videos")
    ex = _extract(html, "ash29_03")
    assert ex["name"] == "Ashwin Harish"


def test_threads_entity_encoded_title_yields_real_name():
    html = _og_title("Ashwin Harish (&#064;ash29_03) &#x2022; Threads, Say more")
    ex = _extract(html, "ash29_03")
    assert ex["name"] == "Ashwin Harish"


def test_plain_decoded_title_still_works():
    # No regression for titles that arrive already decoded.
    html = _og_title("Vismay H S (@vismay_hs) • Instagram photos and videos")
    ex = _extract(html, "vismay_hs")
    assert ex["name"] == "Vismay H S"


def test_github_handle_paren_realname_shape():
    html = _og_title("octocat (The Octocat) &middot; GitHub")
    ex = _extract(html, "octocat")
    assert ex["name"] == "The Octocat"


def test_handle_echo_is_not_a_name():
    # A title that is just the handle (no real name) must NOT be surfaced as a name.
    html = _og_title("ash29_03 (&#064;ash29_03) &#x2022; Instagram photos and videos")
    ex = _extract(html, "ash29_03")
    assert ex["name"] is None


def test_bio_is_fully_entity_decoded():
    html = ('<html><head>'
            '<meta property="og:description" content="546 Followers &#x2022; 0 Threads &amp; more">'
            '</head></html>')
    ex = _extract(html, "ash29_03")
    assert ex["bio"] == "546 Followers • 0 Threads & more"
