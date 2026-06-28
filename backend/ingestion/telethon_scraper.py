"""
backend/ingestion/telethon_scraper.py — Telegram user lookup via Telethon.

Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env.
Looks up a username on Telegram to extract their Name, ID, and bio.
"""
from __future__ import annotations

import os

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class TelethonScraper(BaseDataSource):
    name = "telethon"

    async def _run_live(self, username: str) -> list[RawProfile]:
        api_id = os.environ.get("TELEGRAM_API_ID") or getattr(config, "TELEGRAM_API_ID", None)
        api_hash = os.environ.get("TELEGRAM_API_HASH") or getattr(config, "TELEGRAM_API_HASH", None)
        
        if not api_id or not api_hash:
            return []
            
        try:
            # Import telethon here so it's not a hard dependency if unused
            from telethon import TelegramClient
            from telethon.tl.functions.users import GetFullUserRequest
            
            # Using an in-memory or throwaway session for stateless API lookups
            # Note: Telegram requires phone number login for the first run, 
            # so for a fully automated backend, a bot token is better.
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            
            if not bot_token:
                return []
                
            client = TelegramClient('anon', api_id, api_hash)
            await client.start(bot_token=bot_token)
            
            try:
                full_user = await client(GetFullUserRequest(username))
                user = full_user.user
                
                name = " ".join(filter(None, [user.first_name, user.last_name]))
                meta = {
                    "name": name,
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "bio": full_user.about,
                    "premium": user.premium,
                }
                return [make_profile(
                    "social_account", username, "telegram", f"https://t.me/{username}",
                    metadata=meta
                )]
            finally:
                await client.disconnect()
        except Exception:
            return []
