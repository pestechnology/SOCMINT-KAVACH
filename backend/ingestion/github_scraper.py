"""
backend/ingestion/github_scraper.py — GitHub via the public REST API (httpx).

Handles both seeds:
  - email     -> /search/users?q={email}+in:email  (find the account that used it)
  - username  -> /users/{username}                  (rich profile: name, bio, avatar, ...)

Token (config.GITHUB_TOKEN) raises the rate limit to 5000/h but is optional for
public data. Returns [] on any failure.
"""
from __future__ import annotations

import httpx

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_API = "https://api.github.com"

_EVENT_LABELS = {
    "PushEvent": "pushed commits to",
    "CreateEvent": "created",
    "PullRequestEvent": "opened a pull request on",
    "IssuesEvent": "opened an issue on",
    "WatchEvent": "starred",
    "ForkEvent": "forked",
    "IssueCommentEvent": "commented on",
    "ReleaseEvent": "published a release on",
    "PublicEvent": "made public",
}


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "VERTEX-OSINT"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


async def _recent_activity(client: httpx.AsyncClient, login: str) -> list[dict]:
    """Up to 10 recent public GitHub events with real timestamps. Never raises."""
    try:
        r = await client.get(f"{_API}/users/{login}/events/public", params={"per_page": 30})
        if r.status_code != 200:
            return []
        out = []
        for ev in r.json()[:30]:
            if len(out) >= 10:
                break
            repo = (ev.get("repo") or {}).get("name")
            created = ev.get("created_at")
            if not repo or not created:
                continue
            out.append({
                "kind": "activity",
                "platform": "github",
                "title": f"{_EVENT_LABELS.get(ev.get('type'), ev.get('type'))} {repo}",
                "image_url": None,   # explicit None — GitHub has no post images
                "posted_at": created,
                "permalink": f"https://github.com/{repo}",
            })
        return out
    except Exception:
        return []


async def _profile_from_user(client: httpx.AsyncClient, user: dict) -> RawProfile:
    login = user.get("login", "")
    activity = await _recent_activity(client, login) if login else []
    meta = {
        "name": user.get("name"),
        "location": user.get("location"),
        "bio": user.get("bio"),
        "followers": user.get("followers"),
        "public_repos": user.get("public_repos"),
        "photo_url": user.get("avatar_url"),
        "email": user.get("email"),
        "blog": user.get("blog"),
        "created_at": user.get("created_at")
    }
    if activity:
        meta["recent_posts"] = activity
    return make_profile("social_account", login, "github", user.get("html_url", ""), metadata=meta)


class GitHubScraper(BaseDataSource):
    name = "github"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        ident = identifier.strip()
        async with httpx.AsyncClient(timeout=15, headers=_headers()) as client:
            if "@" in ident and "." in ident.split("@")[-1]:
                # email seed -> search users
                r = await client.get(f"{_API}/search/users", params={"q": f"{ident} in:email"})
                if r.status_code != 200:
                    return []
                out = []
                for item in r.json().get("items", [])[:5]:
                    ur = await client.get(f"{_API}/users/{item.get('login')}")
                    if ur.status_code == 200:
                        out.append(await _profile_from_user(client, ur.json()))
                return out
            # username seed -> profile
            r = await client.get(f"{_API}/users/{ident}")
            if r.status_code != 200:
                return []
            return [await _profile_from_user(client, r.json())]
