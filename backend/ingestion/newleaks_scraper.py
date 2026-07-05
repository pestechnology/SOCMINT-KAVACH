"""
backend/ingestion/newleaks_scraper.py — OPTIONAL breach/PII add-on via the
@NewleaksOsintBot Telegram bot.

WHY A USER SESSION (not a bot token):
    Telegram forbids bots from messaging other bots, so the existing bot-token
    Telethon client (telethon_scraper.py) cannot talk to @NewleaksOsintBot. This
    module drives a **user** session instead — created once, interactively, by
    scripts/telegram_login.py — which sends the seed value to the bot as a chat
    message and parses the reply.

SAFETY (this is a pure add-on — see the pipeline's "don't break anything" rule):
    _run_live() returns [] IMMEDIATELY unless ALL of these hold:
      • config.NEWLEAKS_ENABLED is true, AND
      • TELEGRAM_API_ID / TELEGRAM_API_HASH are set, AND
      • a user .session file already exists on disk (we NEVER trigger the
        interactive phone-login from inside the request pipeline).
    Every failure path returns [] (BaseDataSource.resolve() also wraps this
    fail-safe), so a disabled, unconfigured, blocked, or slow bot can never affect
    any other scraper or the case pipeline. It is also never used in mock mode
    (the orchestrator swaps in MockScraper there).

CONCURRENCY:
    A single user session must not fire overlapping queries at the bot, so all
    lookups are serialized behind a module-level asyncio.Lock, and every bot round
    trip has a hard timeout (config.NEWLEAKS_TIMEOUT_SECONDS).

OUTPUT:
    One breach-type RawProfile shaped exactly like dehashed_scraper.py / hibp:
    metadata carries `breaches`, `breach_count`, `breach_name`, `source`, and is
    flagged `sensitive_source: True` (the reply can contain passwords/PII), plus a
    truncated `raw_text` and any regex-extracted emails/phones. The parser is
    intentionally GENERIC — refine _parse_reply() once a real sample reply is
    available; until then it still yields useful, honestly-labelled evidence.
"""
from __future__ import annotations

import asyncio
import os
import re

from backend import config
from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

# Serialize all queries through the one user session (see module docstring).
_LOCK = asyncio.Lock()

# "Nothing found" replies vary; treat any of these (case-insensitive) as empty.
_EMPTY_MARKERS = (
    "not found", "no results", "nothing found", "no data", "ничего не найдено",
    "не найдено", "no records", "subjects made: 0", "the number of leaks: 0",
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# "💦The number of leaks: 66" in the bot's summary header.
_COUNT_RE = re.compile(r"number of leaks:\s*(\d+)", re.I)
# The bot's per-record field labels are emoji-prefixed, e.g. "**📩Email: ** `x@y.z`".
# We match on the WORD after stripping markdown/emoji, so it survives label churn.
_FIELD_WORDS = {
    "email": "emails", "mail": "emails",
    "password": "passwords", "pass": "passwords",
    "phone": "phones", "tel": "phones", "number": "phones",
    "link": "links", "site": "links", "url": "links", "domain": "links",
    "name": "names", "nick": "names", "login": "names", "username": "names",
    "ip": "ips",
}
# Header/menu lines that must never be mistaken for a record field.
_HEADER_LABELS = ("request", "subjects made", "number of leaks", "search time",
                  "store", "limit", "mirror", "note")
_MAX_RAW = 6000      # cap stored raw reply so a huge dump can't bloat the DB row
_MAX_ITEMS = 100     # cap each extracted list (passwords/emails/…) for the same reason


def _session_ready() -> bool:
    """True only if a Telethon USER session file actually exists on disk. Telethon
    writes `<session>.session`; we accept either the bare path or the .session file."""
    base = config.TELEGRAM_USER_SESSION
    return bool(base) and (os.path.exists(base) or os.path.exists(base + ".session"))


def _enabled() -> bool:
    return bool(
        config.NEWLEAKS_ENABLED
        and (os.environ.get("TELEGRAM_API_ID") or config.TELEGRAM_API_ID)
        and (os.environ.get("TELEGRAM_API_HASH") or config.TELEGRAM_API_HASH)
        and _session_ready()
    )


# Serialize the on-disk .session ONCE into an in-memory StringSession. Every per-query
# client is then built from this string instead of reopening the SQLite .session file —
# which avoids both the 'database is locked' errors from rapid reconnects and any event-
# loop binding. Loaded lazily on first use.
_SESSION_STRING = None


def _session_string():
    """Return the user session as an in-memory StringSession string (cached), or None."""
    global _SESSION_STRING
    if _SESSION_STRING is not None:
        return _SESSION_STRING
    try:
        from telethon.sessions import SQLiteSession, StringSession
        sess = SQLiteSession(config.TELEGRAM_USER_SESSION)
        try:
            _SESSION_STRING = StringSession.save(sess)
        finally:
            sess.close()
    except Exception as e:  # noqa: BLE001 — fail-safe; caller degrades to []
        print(f"[newleaks] session load failed: {e}")
        return None
    return _SESSION_STRING


async def _get_client():
    """Create a FRESH, connected, authorized user client bound to the CURRENT event loop
    (or None). A new client per call — built from the in-memory StringSession, not the
    cached module-level client — is required because the pipeline runs each investigation
    on its own event loop, and Telethon binds a client to the loop it connected on ('The
    asyncio event loop must not change after connection'). Building from a StringSession
    also avoids reopening the SQLite .session file ('database is locked'). The caller MUST
    disconnect() it when done. Never prompts for login."""
    from telethon import TelegramClient  # imported lazily so telethon stays optional
    from telethon.sessions import StringSession

    string = _session_string()
    if not string:
        return None

    api_id = int(os.environ.get("TELEGRAM_API_ID") or config.TELEGRAM_API_ID)
    api_hash = os.environ.get("TELEGRAM_API_HASH") or config.TELEGRAM_API_HASH

    client = TelegramClient(StringSession(string), api_id, api_hash)
    await client.connect()
    # If the session isn't an authorized USER (e.g. only a bot session exists), bail —
    # we must not block waiting for an interactive code inside the pipeline.
    if not await client.is_user_authorized():
        try:
            await client.disconnect()
        except Exception:
            pass
        return None
    return client


def _looks_empty(text: str) -> bool:
    low = text.lower()
    return (not text.strip()) or any(m in low for m in _EMPTY_MARKERS)


def _clean(line: str) -> str:
    """Strip the bot's markdown (** and `) and surrounding whitespace from one line."""
    return line.replace("**", "").replace("`", "").strip()


# Bold lines that are notices/prompts, not source-database names (the bot bolds these
# the same way it bolds a DB title). Anything containing one of these is not a DB.
_NOTICE_WORDS = ("did not fit", "download", "document", "results were found", "no results",
                 "subscription", "shop", "mirror", "limit", "please note", "random of them",
                 "search time", "request")


def _looks_like_db_title(raw_line: str, cleaned: str) -> bool:
    """A source-database heading is a SHORT, fully-bold line with no field colon, e.g.
    '**👽Alien TxtBase**'. Field rows are bold only around the label ('**📩Email: **'),
    and the bot's notice lines ('Some data did not fit this message! Download…') are
    long, sentence-like bold lines — excluded here so they don't pollute breach names."""
    s = raw_line.strip()
    if not (s.startswith("**") and s.endswith("**") and s.count("**") == 2):
        return False
    if ":" in cleaned:
        return False
    low = cleaned.lower()
    if any(w in low for w in _NOTICE_WORDS):
        return False
    if cleaned.endswith((".", "!", "?")):     # a sentence, not a title
        return False
    if len(cleaned.split()) > 6:              # DB names are short, not paragraphs
        return False
    # drop leading emoji/symbols; require a couple of real letters so we skip dividers
    letters = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    return len(letters) >= 3 and len(cleaned) <= 50


def _parse_reply(identifier: str, text: str) -> list[RawProfile]:
    """Parse @NewleaksOsintBot's real reply:
       • a summary header ('🔎Request…', '💦The number of leaks: N', free-version notes)
       • one or more data messages: '**<Source DB>**' + description, then repeating
         '📩Email: / 🔑Password: / 🔗Link: / 📱Phone: …' record rows.
    Produces a single breach-type RawProfile shaped like the other breach scrapers."""
    if _looks_empty(text):
        return []

    raw = text.strip()
    m = _COUNT_RE.search(raw)
    leaks_count = int(m.group(1)) if m else None
    if leaks_count == 0:
        return []

    fields: dict[str, list[str]] = {v: [] for v in set(_FIELD_WORDS.values())}
    databases: list[str] = []

    for line in raw.splitlines():
        cleaned = _clean(line)
        if not cleaned:
            continue
        if _looks_like_db_title(line, cleaned):
            name = re.sub(r"^[^\w]+", "", cleaned).strip()   # drop leading emoji
            if name and name not in databases:
                databases.append(name)
            continue
        if ":" not in cleaned:
            continue
        label, _, value = cleaned.partition(":")
        label_l = label.lower()
        value = value.strip()
        if not value or any(h in label_l for h in _HEADER_LABELS):
            continue   # header/menu line, never a record field
        for word, bucket in _FIELD_WORDS.items():
            if word in label_l:
                if bucket == "emails" and "@" not in value:
                    break
                lst = fields[bucket]
                if value not in lst and len(lst) < _MAX_ITEMS:
                    lst.append(value)
                break

    total_records = sum(len(v) for v in fields.values())
    # No structured records AND no named source DB => not a real hit (menu/echo). Bail.
    if total_records == 0 and not databases:
        return []

    breaches = databases or ["NewLeaks OSINT bot"]
    return [make_profile(
        "breach", identifier, "newleaks",
        f"https://t.me/{config.NEWLEAKS_BOT_USERNAME}",
        metadata={
            "breaches": breaches,
            "breach_count": leaks_count if leaks_count is not None else len(breaches),
            "breach_name": ", ".join(breaches[:5]) + ("…" if len(breaches) > 5 else ""),
            "source": "newleaks_bot",
            "sensitive_source": True,   # contains passwords / PII — UI + report flag it
            "leaks_count": leaks_count,
            "databases": databases,
            "emails": fields["emails"],
            "phones": fields["phones"],
            "passwords": fields["passwords"],
            "links": fields["links"],
            "names": fields["names"],
            "ips": fields["ips"],
            "raw_text": raw[:_MAX_RAW],
        },
    )]


class NewLeaksScraper(BaseDataSource):
    name = "newleaks"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        if not identifier or not _enabled():
            return []

        bot = config.NEWLEAKS_BOT_USERNAME
        timeout = config.NEWLEAKS_TIMEOUT_SECONDS

        async with _LOCK:
            client = await _get_client()
            if client is None:
                return []
            try:
                # conversation() cleanly pairs our send with the bot's response and
                # enforces a timeout so a silent bot can never hang the pipeline.
                async with client.conversation(bot, timeout=timeout) as conv:
                    # Send the seed EXACTLY as entered — no phone/format normalization.
                    await conv.send_message(identifier)
                    parts: list[str] = []
                    # Collect the first response, then any quick follow-ups (these bots
                    # often send a "searching…" line before the real results).
                    try:
                        while True:
                            resp = await asyncio.wait_for(conv.get_response(), timeout=timeout)
                            if resp and resp.text:
                                parts.append(resp.text)
                            # after the first message, only wait briefly for more
                            timeout = 4
                    except asyncio.TimeoutError:
                        pass
                text = "\n".join(parts)
            except Exception as e:  # noqa: BLE001 — fail-safe (base class also guards)
                print(f"[newleaks] query failed: {e}")
                return []
            finally:
                # Always tear the client down so nothing stays bound to this loop — the
                # next investigation gets a clean, freshly-connected client.
                try:
                    await client.disconnect()
                except Exception:
                    pass

        return _parse_reply(identifier, text)
