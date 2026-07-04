"""
backend/agentic_browser/sources.py — the OSINT source registry.

Each source declares which identifier TYPES it handles, its fetch backend, how to turn a
query into a result URL, what it yields, and a priority (1 = high-value, scraped first).

`auth` / backend:
  "public" → Supadata web reader (server-side, bypasses Cloudflare, no login).
  "login"  → the authed_browser (your dedicated logged-in Chrome profile).
  "api"    → a first-party API client (e.g. IntelBase) — no scraping at all.

QUOTA NOTE: Supadata's free tier is ~100 requests total, so `smart_lookup` scrapes only the
top-N public sources per lookup (by priority), not the whole list. The registry is the *menu*;
add a website later = append one dict here.
"""
from __future__ import annotations

import urllib.parse

TYPES = ["username", "email", "name", "instagram", "phone"]


def _h(q: str) -> str:
    return (q or "").strip().lstrip("@")


def _u(q: str) -> str:
    return urllib.parse.quote((q or "").strip())


# --- public profile sites: username → a direct profile URL Supadata can read -------------
def _profile(id_, name, tmpl, priority=2, yields=("name", "username", "location", "bio")):
    return {"id": id_, "name": name, "supports": ["username"], "auth": "public",
            "url": (lambda t: (lambda q: t.format(h=_h(q))))(tmpl),
            "yields": list(yields), "priority": priority}


_USERNAME_SITES = [
    _profile("github", "GitHub", "https://github.com/{h}", 1, ("name", "location", "accounts")),
    _profile("gitlab", "GitLab", "https://gitlab.com/{h}", 2),
    _profile("reddit", "Reddit", "https://www.reddit.com/user/{h}/", 1),
    _profile("x", "X / Twitter", "https://x.com/{h}", 1),
    _profile("tiktok", "TikTok", "https://www.tiktok.com/@{h}", 2),
    _profile("youtube", "YouTube", "https://www.youtube.com/@{h}", 2),
    _profile("pinterest", "Pinterest", "https://www.pinterest.com/{h}/", 3),
    _profile("twitch", "Twitch", "https://www.twitch.tv/{h}", 3),
    _profile("medium", "Medium", "https://medium.com/@{h}", 3),
    _profile("devto", "Dev.to", "https://dev.to/{h}", 3),
    _profile("keybase", "Keybase", "https://keybase.io/{h}", 2, ("name", "accounts")),
    _profile("gravatar", "Gravatar", "https://gravatar.com/{h}", 2, ("name", "location", "accounts")),
    _profile("aboutme", "About.me", "https://about.me/{h}", 2),
    _profile("steam", "Steam", "https://steamcommunity.com/id/{h}", 3),
    _profile("soundcloud", "SoundCloud", "https://soundcloud.com/{h}", 3),
    _profile("telegram", "Telegram", "https://t.me/{h}", 2),
    _profile("behance", "Behance", "https://www.behance.net/{h}", 3),
    _profile("dribbble", "Dribbble", "https://dribbble.com/{h}", 3),
    _profile("lichess", "Lichess", "https://lichess.org/@/{h}", 3),
    _profile("chesscom", "Chess.com", "https://www.chess.com/member/{h}", 3),
    _profile("replit", "Replit", "https://replit.com/@{h}", 3),
    _profile("producthunt", "Product Hunt", "https://www.producthunt.com/@{h}", 3),
    _profile("linktree", "Linktree", "https://linktr.ee/{h}", 2, ("accounts", "name")),
    _profile("hackernews", "Hacker News", "https://news.ycombinator.com/user?id={h}", 3),
]


SOURCES: list[dict] = [
    # --- Instagram ---
    {"id": "instagram", "name": "Instagram (public profile)", "supports": ["instagram", "username"],
     "auth": "public", "url": lambda q: f"https://www.instagram.com/{_h(q)}/",
     "yields": ["name", "username", "location", "photo", "bio"], "priority": 1},
    {"id": "inflact", "name": "Inflact (Instagram viewer)", "supports": ["instagram"],
     "auth": "public", "url": lambda q: f"https://inflact.com/profiles/instagram-viewer/{_h(q)}/",
     "yields": ["name", "followers", "bio", "photo"], "priority": 2,
     "note": "Cloudflare-walled; Supadata gets past it."},

    *_USERNAME_SITES,

    # --- IntelBase API (email / username / phone / name) — needs IP whitelist + key ---
    {"id": "intelbase_email", "name": "IntelBase (email)", "supports": ["email"], "auth": "api",
     "api": "intelbase", "kind": "email", "yields": ["accounts", "usernames", "breaches"], "priority": 1},
    {"id": "intelbase_username", "name": "IntelBase (username)", "supports": ["username"], "auth": "api",
     "api": "intelbase", "kind": "username", "yields": ["accounts", "emails"], "priority": 1},
    {"id": "intelbase_phone", "name": "IntelBase (phone)", "supports": ["phone"], "auth": "api",
     "api": "intelbase", "kind": "phone", "yields": ["accounts", "names"], "priority": 1},
    {"id": "intelbase_name", "name": "IntelBase (name)", "supports": ["name"], "auth": "api",
     "api": "intelbase", "kind": "name", "yields": ["accounts", "usernames"], "priority": 2},
]


def sources_for(id_type: str, include_login: bool = True) -> list[dict]:
    """All sources supporting `id_type`, sorted by priority (1 first)."""
    out = [s for s in SOURCES if id_type in s["supports"]
           and (include_login or s["auth"] != "login")]
    return sorted(out, key=lambda s: s.get("priority", 5))


def build_url(source: dict, query: str) -> str:
    try:
        return source["url"](query)
    except Exception:  # noqa: BLE001
        return ""
