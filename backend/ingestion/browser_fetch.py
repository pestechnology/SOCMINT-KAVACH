"""
backend/ingestion/browser_fetch.py — real-browser fallback for bot-blocked pages.

Some high-value OSINT pages serve an HTTP 400/403 login/challenge stub to a plain httpx
request but render full, PUBLIC content (name, bio, a contact email, a website) to a real
browser. Facebook is the canonical case: `GET facebook.com/{handle}` returns a ~1.5 KB
login stub with no og: tags (see profile_page_fetcher, which is httpx-based and therefore
gets nothing), yet the same page rendered in a real browser shows a public "Intro" box
with the account's contact email. This module drives a stealth headless Chromium
(patchright) to render such pages and pulls the contact email / website the normal
enrichment pass can't reach.

Fully OPTIONAL and fail-safe. If patchright or its browser binary isn't installed every
function degrades to an empty/negative result and the pipeline proceeds exactly as before
(same contract as every other scraper in this package). Browser fetches are slow and
heavy, so callers must keep the target set small — this is a last-resort fallback for a
handful of known-hard hosts, not a general fetch path.
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses that are never a subject's personal contact email — platform/CDN/monitoring
# noise that shows up in rendered page text or inline scripts.
_EMAIL_BLOCK_SUBSTR = (
    "@facebook.com", "@fbcdn", "@sentry", "@example.", "@email.com",
    "noreply", "no-reply", "@w3.org", "@schema.org", "@googlegroups.com",
)

# Hosts whose PUBLIC profile pages are blocked to httpx but readable in a real browser.
_HARD_HOSTS = ("facebook.com", "fb.com", "m.facebook.com")


def browser_available() -> tuple[bool, str]:
    """(True, "ok") only if patchright is importable. Does not verify the browser binary
    is downloaded — a fetch that hits a missing binary fails safe to empty text."""
    try:
        import patchright  # noqa: F401
    except Exception as e:  # noqa: BLE001
        return False, f"patchright not installed: {e}"
    return True, "ok"


def _fetch_many_sync(urls: list[str], wait_ms: int, profile_dir: str) -> dict[str, str]:
    """Render each URL in ONE stealth Chromium context, return {url: body_text}.
    Synchronous (patchright's sync API); call via asyncio.to_thread. Never raises."""
    out: dict[str, str] = {u: "" for u in urls}
    try:
        from patchright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return out
    try:
        with sync_playwright() as p:
            try:
                ctx = p.chromium.launch_persistent_context(
                    channel="chrome", user_data_dir=profile_dir,
                    headless=True, no_viewport=True)
            except Exception:  # noqa: BLE001 - fall back to bundled chromium
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir, headless=True, no_viewport=True)
            try:
                page = ctx.new_page()
                for u in urls:
                    try:
                        page.goto(u, timeout=45000, wait_until="domcontentloaded")
                        page.wait_for_timeout(wait_ms)
                        out[u] = page.inner_text("body") or ""
                    except Exception:  # noqa: BLE001 - one bad URL must not sink the batch
                        out[u] = ""
            finally:
                ctx.close()
    except Exception:  # noqa: BLE001 - missing binary / launch failure → all-empty
        pass
    return out


async def fetch_texts(urls, wait_ms: int = 5000) -> dict[str, str]:
    """Async wrapper: render URLs in a stealth browser off the event loop. {} if none."""
    urls = [u for u in dict.fromkeys(urls) if u]   # dedup, keep order, drop empties
    if not urls:
        return {}
    pdir = os.path.join(tempfile.gettempdir(), "vertex_browser_fetch")
    return await asyncio.to_thread(_fetch_many_sync, urls, wait_ms, pdir)


def extract_emails(text: str) -> list[str]:
    """Distinct, real-looking contact emails from rendered page text (block-listed noise
    removed), preserving first-seen order."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _EMAIL_RE.findall(text or ""):
        ml = m.lower()
        if any(b in ml for b in _EMAIL_BLOCK_SUBSTR):
            continue
        if ml not in seen:
            seen.add(ml)
            out.append(m)
    return out


def is_hard_blocked_url(url: str) -> bool:
    """True for a profile URL on a host that blocks httpx but renders in a browser."""
    u = str(url or "").lower()
    return u.startswith("http") and any(h in u for h in _HARD_HOSTS)
