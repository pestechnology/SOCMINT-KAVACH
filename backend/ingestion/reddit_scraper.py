"""
backend/ingestion/reddit_scraper.py — Reddit user scraper + activity analytics.

Fetches the user's profile and recent comments to derive REAL activity analytics from
public post timestamps: the user's active-hour fingerprint (`posting_hours`, used by
the correlation engine's posting_hours_overlap signal), posting frequency, and a
24-bucket activity histogram for the report / "most active time" insight.

Auth: if REDDIT_CLIENT_ID/SECRET are set it uses app-only OAuth (oauth.reddit.com),
which avoids the anti-bot 403s that block datacenter IPs; otherwise it falls back to
the public www.reddit.com JSON endpoints (works from residential networks).
"""
from __future__ import annotations

import datetime
import time

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_PUBLIC_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
# Module-level app-only token cache (shared across scraper instances within a run).
_token_cache = {"value": None, "exp": 0.0}


async def _oauth_token(client: httpx.AsyncClient) -> str | None:
    """Return a cached app-only Reddit token, or None if creds are absent/fail."""
    cid = getattr(config, "REDDIT_CLIENT_ID", "")
    csec = getattr(config, "REDDIT_CLIENT_SECRET", "")
    if not cid or not csec:
        return None
    now = time.time()
    if _token_cache["value"] and _token_cache["exp"] > now + 30:
        return _token_cache["value"]
    try:
        r = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(cid, csec),
            headers={"User-Agent": config.REDDIT_USER_AGENT},
            timeout=15.0,
        )
        if r.status_code != 200:
            return None
        j = r.json()
        _token_cache["value"] = j.get("access_token")
        _token_cache["exp"] = now + float(j.get("expires_in", 3600))
        return _token_cache["value"]
    except Exception:
        return None


def _activity_from_timestamps(epochs: list[float]) -> dict:
    """Turn post epochs into an active-hour fingerprint + frequency + histogram.

    `posting_hours` is the set of UTC hours where the user is busier than their own
    average — a distinctive fingerprint (NOT all 24 hours, which would match everyone).
    """
    epochs = [e for e in epochs if isinstance(e, (int, float)) and e > 0]
    if not epochs:
        return {}
    hist = [0] * 24
    for e in epochs:
        hist[datetime.datetime.utcfromtimestamp(e).hour] += 1
    avg = sum(hist) / 24.0
    active_hours = [h for h in range(24) if hist[h] > 0 and hist[h] >= avg]
    span_days = max((max(epochs) - min(epochs)) / 86400.0, 1.0)
    peak = max(range(24), key=lambda h: hist[h])
    return {
        "posting_hours": active_hours,
        "activity_by_hour": hist,
        "posts_analyzed": len(epochs),
        "posting_frequency_per_day": round(len(epochs) / span_days, 2),
        "peak_hour_utc": peak,
        "most_active_time_utc": f"{peak:02d}:00-{(peak + 1) % 24:02d}:00 UTC",
    }


class RedditScraper(BaseDataSource):
    name = "reddit"

    async def _run_live(self, username: str) -> list[RawProfile]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token = await _oauth_token(client)
                if token:
                    base = "https://oauth.reddit.com"
                    suffix = ""  # oauth host returns JSON without the .json suffix
                    headers = {"User-Agent": config.REDDIT_USER_AGENT,
                               "Authorization": f"bearer {token}"}
                else:
                    base = "https://www.reddit.com"
                    suffix = ".json"
                    headers = {"User-Agent": _PUBLIC_UA}

                r = await client.get(f"{base}/user/{username}/about{suffix}", headers=headers)
                if r.status_code != 200:
                    return []
                data = r.json().get("data", {})

                # Check if it's an actual user account (not suspended/deleted)
                if data.get("is_suspended") or data.get("is_deleted"):
                    return []

                meta = {
                    "created_utc": data.get("created_utc"),
                    "link_karma": data.get("link_karma"),
                    "comment_karma": data.get("comment_karma"),
                    "is_employee": data.get("is_employee"),
                    "has_verified_email": data.get("has_verified_email"),
                }

                sub = data.get("subreddit") or {}
                if sub:
                    meta["bio"] = sub.get("public_description", "")
                    meta["title"] = sub.get("title", "")
                    meta["name"] = sub.get("title", "")
                    meta["avatar"] = sub.get("icon_img", "").split("?")[0] if sub.get("icon_img") else ""

                # Activity analytics from recent comments (public, timestamped).
                # Fail-safe: if this fetch fails the profile is still returned.
                try:
                    cr = await client.get(
                        f"{base}/user/{username}/comments{suffix}",
                        params={"limit": 100, "raw_json": 1},
                        headers=headers,
                    )
                    if cr.status_code == 200:
                        children = cr.json().get("data", {}).get("children", [])
                        epochs = [c.get("data", {}).get("created_utc") for c in children]
                        meta.update(_activity_from_timestamps(epochs))
                        # sampled comment text -> stylometry + sentiment forensics
                        bodies = [c.get("data", {}).get("body", "") for c in children]
                        sample = " ".join(b for b in bodies if b)[:4000]
                        if sample:
                            meta["text_sample"] = sample
                except Exception:
                    pass

                return [make_profile(
                    "social_account", username, "reddit", f"https://www.reddit.com/user/{username}",
                    metadata=meta
                )]
        except Exception:
            return []
