"""
backend/ingestion/reddit_scraper.py — Reddit user JSON scraper.

Fetches the /about.json endpoint for a Reddit user to retrieve profile metadata.
"""
from __future__ import annotations

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class RedditScraper(BaseDataSource):
    name = "reddit"

    async def _run_live(self, username: str) -> list[RawProfile]:
        url = f"https://www.reddit.com/user/{username}/about.json"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, headers=headers)
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
                    
                return [make_profile(
                    "social_account", username, "reddit", f"https://www.reddit.com/user/{username}",
                    metadata=meta
                )]
        except Exception:
            return []
