"""
scripts/telegram_login.py — ONE-TIME interactive login to create the Telethon USER
session that the NewLeaks add-on (backend/ingestion/newleaks_scraper.py) needs.

Bots can't message other bots, so querying @NewleaksOsintBot requires a real user
account. Run this once, from a terminal, on the machine that will run the backend:

    python -m scripts.telegram_login

It will ask for your phone number and the login code Telegram sends you (and your
2FA password if you have one), then write the session file to
config.TELEGRAM_USER_SESSION (default: <repo>/user_session.session). After that, set
NEWLEAKS_ENABLED=true in .env and the scraper activates. Nothing else changes.

The session file is a credential — it is gitignored (*.session) and must never be
committed or shared.
"""
from __future__ import annotations

import asyncio
import os
import sys

from backend import config


async def main() -> None:
    api_id = os.environ.get("TELEGRAM_API_ID") or config.TELEGRAM_API_ID
    api_hash = os.environ.get("TELEGRAM_API_HASH") or config.TELEGRAM_API_HASH
    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID / TELEGRAM_API_HASH are not set in .env.")
        print("Get them (free) from https://my.telegram.org -> API development tools.")
        sys.exit(1)

    try:
        from telethon import TelegramClient
    except ImportError:
        print("ERROR: telethon is not installed. Run: pip install telethon")
        sys.exit(1)

    session = config.TELEGRAM_USER_SESSION
    print(f"Creating Telegram USER session at: {session}.session")
    client = TelegramClient(session, int(api_id), api_hash)
    # client.start() prompts for phone + code (+ 2FA password) on first run.
    await client.start()

    me = await client.get_me()
    who = " ".join(filter(None, [getattr(me, "first_name", ""), getattr(me, "last_name", "")]))
    print(f"\n✅ Logged in as: {who} (@{getattr(me, 'username', None)}, id={me.id})")

    bot = config.NEWLEAKS_BOT_USERNAME
    try:
        entity = await client.get_entity(bot)
        print(f"✅ Reached @{bot} (id={entity.id}). You can now set NEWLEAKS_ENABLED=true.")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  Logged in, but could not resolve @{bot}: {e}")
        print("   Open Telegram, press Start on the bot once, then it should resolve.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
