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


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "VERTEX-OSINT"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


def _profile_from_user(user: dict) -> RawProfile:
    return make_profile(
        "social_account", user.get("login", ""), "github",
        user.get("html_url", ""),
        metadata={
            "name": user.get("name"),
            "location": user.get("location"),
            "bio": user.get("bio"),
            "followers": user.get("followers"),
            "public_repos": user.get("public_repos"),
            "photo_url": user.get("avatar_url"),
            "email": user.get("email"),
            "blog": user.get("blog"),
            "created_at": user.get("created_at")
        },
    )


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
                        out.append(_profile_from_user(ur.json()))
                return out
            # username seed -> profile
            r = await client.get(f"{_API}/users/{ident}")
            if r.status_code != 200:
                return []
            return [_profile_from_user(r.json())]
