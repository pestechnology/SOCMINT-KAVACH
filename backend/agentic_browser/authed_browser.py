"""
backend/agentic_browser/authed_browser.py — logged-in fetch via a DEDICATED Chrome profile.

For login-gated OSINT sources (intelbase.is, fingerprint.to), Supadata can't help — it runs
unauthenticated from its own servers. Instead we keep a dedicated Chrome profile that YOU log
into once; automation then reuses its cookies for every future query. It is isolated from your
main Chrome, and stealth-patched (patchright) so the automated visits look human.

One-time setup (opens a real Chrome window for you to log in):
    python -m backend.agentic_browser.authed_browser            # opens intelbase.is
    python -m backend.agentic_browser.authed_browser https://fingerprint.to/

After you've logged in there, `fetch(url)` reuses that session headlessly.

NOTE on identity: everything fetched through this profile happens AS YOUR logged-in account
on those sites (ban/attribution risk). Use only for authorized investigation.
"""
from __future__ import annotations

import os
import pathlib

PROFILE_DIR = os.path.expanduser(os.getenv("VERTEX_AUTHED_PROFILE", "~/.vertex/authed_chrome"))


def profile_dir() -> str:
    pathlib.Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)
    return PROFILE_DIR


def _marker() -> pathlib.Path:
    return pathlib.Path(PROFILE_DIR) / ".vertex_login_done"


def is_set_up() -> bool:
    """True only once the user has actually completed login_setup — NOT merely because a
    fetch created cache files in the profile dir (a marker is written at the end of setup)."""
    return _marker().exists()


def _context(p, headless: bool):
    """Launch a persistent, stealth Chrome context at the dedicated profile dir."""
    kwargs = dict(user_data_dir=profile_dir(), headless=headless, no_viewport=True)
    # Prefer real Google Chrome (better fingerprint); fall back to bundled Chromium.
    try:
        return p.chromium.launch_persistent_context(channel="chrome", **kwargs)
    except Exception:  # noqa: BLE001
        return p.chromium.launch_persistent_context(**kwargs)


def fetch(url: str, wait_ms: int = 4000) -> dict:
    """Navigate to `url` in the logged-in profile (headless) and return the rendered text.
    Sync (patchright); call via asyncio.to_thread from async code. Never raises."""
    try:
        from patchright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"patchright not installed: {e}"}
    try:
        with sync_playwright() as p:
            ctx = _context(p, headless=True)
            try:
                page = ctx.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(wait_ms)
                title = page.title()
                text = page.inner_text("body")
                low = (text or "").lower()
                # crude login-wall detection so we can tell the user to re-run setup
                needs_login = any(k in low for k in ("sign in", "log in to continue", "please login")) and len(text) < 400
                return {"ok": True, "title": title, "content": text, "needs_login": needs_login}
            finally:
                ctx.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _autoscroll(page, max_scrolls: int) -> int:
    """Scroll to the bottom in steps until scrollHeight stabilises, so lazy / IntersectionObserver
    content is materialised into the DOM before we freeze it. Returns the number of scroll steps."""
    last = -1
    n = 0
    for _ in range(max_scrolls):
        try:
            h = page.evaluate("() => document.body ? document.body.scrollHeight : 0")
        except Exception:  # noqa: BLE001
            break
        if h == last:
            break
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        except Exception:  # noqa: BLE001
            break
        page.wait_for_timeout(600)
        last = h
        n += 1
    try:
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:  # noqa: BLE001
        pass
    return n


def capture_bundle(url: str, wait_ms: int = 3500, max_scrolls: int = 12) -> dict:
    """Render `url` in the logged-in profile (headless) and capture a forensic bundle:
    full-page PNG + MHTML single-file (CDP) + post-JS DOM + provenance. Sync (patchright);
    call via asyncio.to_thread from async code. NEVER raises — returns {ok: False, error} on
    any failure, and {ok: False} if the render produced nothing (fail loud, never a blank
    'success')."""
    try:
        from patchright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"patchright not installed: {e}"}
    try:
        with sync_playwright() as p:
            ctx = _context(p, headless=True)
            try:
                page = ctx.new_page()
                resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(wait_ms)
                scrolls = _autoscroll(page, max_scrolls)

                title = ""
                try:
                    title = page.title()
                except Exception:  # noqa: BLE001
                    pass
                dom = None
                try:
                    dom = page.content()
                except Exception:  # noqa: BLE001
                    pass
                png = None
                try:
                    png = page.screenshot(full_page=True)
                except Exception:  # noqa: BLE001
                    try:
                        png = page.screenshot()
                    except Exception:  # noqa: BLE001
                        png = None
                mhtml = None
                try:
                    cdp = ctx.new_cdp_session(page)
                    snap = cdp.send("Page.captureSnapshot", {"format": "mhtml"})
                    data = (snap or {}).get("data")
                    if isinstance(data, str):
                        mhtml = data.encode("utf-8", "replace")
                    elif isinstance(data, (bytes, bytearray)):
                        mhtml = bytes(data)
                except Exception:  # noqa: BLE001
                    mhtml = None

                # Fail loud: a render that produced no artifact is NOT a success.
                if not dom and not png and not mhtml:
                    return {"ok": False, "error": "render produced no artifacts (blank/blocked page?)"}

                status = getattr(resp, "status", None) if resp else None
                final_url = url
                try:
                    final_url = page.url
                except Exception:  # noqa: BLE001
                    pass
                versions = {"engine": "patchright", "channel": "chrome"}
                try:
                    import playwright
                    versions["playwright"] = getattr(playwright, "__version__", "?")
                except Exception:  # noqa: BLE001
                    pass
                return {"ok": True, "title": title, "dom": dom, "png": png, "mhtml": mhtml,
                        "status": status, "final_url": final_url, "scroll_count": scrolls,
                        "viewport": None, "versions": versions}
            finally:
                ctx.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def login_setup(start_url: str = "https://intelbase.is/") -> None:
    """Open a HEADED window on the dedicated profile so you can log in once. Blocks until you
    press Enter in the terminal, then saves the session."""
    from patchright.sync_api import sync_playwright
    print(f"\n[VERTEX] Opening a Chrome window on the dedicated profile:\n  {profile_dir()}")
    print(f"[VERTEX] Log in to your OSINT site(s). Starting at: {start_url}")
    print("[VERTEX] You can navigate to other login sites in the same window too.")
    with sync_playwright() as p:
        ctx = _context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:  # noqa: BLE001
            pass
        try:
            input("\n>>> Log in in the browser window, then press Enter here to save & finish... ")
        except EOFError:
            pass
        ctx.close()
    _marker().write_text("logged in\n")   # mark setup complete so is_set_up() is True
    print("[VERTEX] Session saved. Automation will now reuse this login.\n")


if __name__ == "__main__":
    import sys
    login_setup(sys.argv[1] if len(sys.argv) > 1 else "https://intelbase.is/")
