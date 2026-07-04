"""
backend/analysis/le_directory.py — law-enforcement data-request directory.

Officers constantly lose time answering "we found the suspect's Snapchat — now WHERE do I
send the legal request for subscriber data?". Every major platform publishes an LE portal
and/or contact for exactly this, but they're scattered across help centers. This module is
a small, static, verifiable directory of those channels, plus a resolver that looks at what
a case actually FOUND and surfaces the matching request contacts.

Design rules:
  - Static data only — entries are publicly documented LE channels (no scraping, no LLM,
    nothing invented at runtime). Anything uncertain is phrased in the note, not the URL.
  - Deterministic + cheap: safe to compute on every results poll once a case is complete.
  - This NEVER filters or reranks results. It is guidance layered on top of them.

Each entry: {platform, label, portal, email, note, accounts}
  `accounts` = the concrete handles found in THIS case on that platform, so the officer can
  paste them straight into a preservation / BNSS s.94 data-request letter.
"""
from __future__ import annotations

# Canonical directory. Keys are our internal platform slugs; ALIASES below maps the many
# platform strings scrapers emit onto these keys.
_DIRECTORY: dict[str, dict] = {
    "meta": {
        "label": "Meta (Instagram / Facebook)",
        "portal": "https://www.facebook.com/records",
        "email": "records@facebook.com",
        "note": "Meta Law Enforcement Online Request System — file a preservation request "
                "first (90 days), then subscriber info/IP logs with a BNSS s.94 notice.",
    },
    "whatsapp": {
        "label": "WhatsApp (Meta)",
        "portal": "https://www.whatsapp.com/records",
        "email": "",
        "note": "WhatsApp has its own Meta LE portal — subscriber, registration and "
                "IP data on valid legal process; message content is end-to-end encrypted.",
    },
    "snapchat": {
        "label": "Snapchat",
        "portal": "https://lesa.snapchat.com",
        "email": "lawenforcement@snapchat.com",
        "note": "Snap Law Enforcement Service Site (LESA) — preservation + subscriber "
                "info, device and IP logs; memories/snap content needs stronger process.",
    },
    "telegram": {
        "label": "Telegram",
        "portal": "https://telegram.org/faq#q-do-you-process-data-requests",
        "email": "abuse@telegram.org",
        "note": "Since the 2024 policy change Telegram discloses a suspect's IP + phone "
                "number on a valid judicial order — route it via I4C / the jurisdictional "
                "court; CSAM reports go to stopca@telegram.org.",
    },
    "google": {
        "label": "Google (Gmail / YouTube)",
        "portal": "https://lers.google.com",
        "email": "",
        "note": "Google Law Enforcement Request System — register with an official LE "
                "email; covers Gmail, YouTube, Drive, location and account metadata.",
    },
    "x": {
        "label": "X (Twitter)",
        "portal": "https://legalrequests.twitter.com",
        "email": "",
        "note": "X legal request portal — preservation, subscriber info and IP logs on "
                "valid legal process from an official LE account.",
    },
    "discord": {
        "label": "Discord",
        "portal": "https://discord.com/safety",
        "email": "lawenforcement@discord.com",
        "note": "Email from an official LE address with the user ID/tag — Discord honors "
                "preservation requests and subscriber/IP disclosures on legal process.",
    },
    "reddit": {
        "label": "Reddit",
        "portal": "https://legalrequests.reddit.com",
        "email": "",
        "note": "Reddit legal request portal — account registration + IP data on valid "
                "legal process; include the exact u/ username.",
    },
    "github": {
        "label": "GitHub",
        "portal": "https://docs.github.com/en/site-policy/security-policies/guidelines-for-legal-requests-of-user-data",
        "email": "legal@support.github.com",
        "note": "GitHub discloses account records on valid legal process — email their "
                "legal team with the username and the offence reference.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "portal": "https://www.linkedin.com/help/linkedin",
        "email": "",
        "note": "Use LinkedIn Help → 'Law Enforcement Data Request' form — subscriber "
                "info and IP logs on valid legal process.",
    },
    "truecaller": {
        "label": "Truecaller (India LEA)",
        "portal": "https://lea.truecaller.com",
        "email": "",
        "note": "Truecaller runs a dedicated India law-enforcement portal — number "
                "lookup and account data for registered LEA officers.",
    },
    "pinterest": {
        "label": "Pinterest",
        "portal": "https://help.pinterest.com/en/article/law-enforcement-guidelines",
        "email": "lawenforcement@pinterest.com",
        "note": "Email with the profile URL — subscriber and log data on legal process.",
    },
    "roblox": {
        "label": "Roblox",
        "portal": "https://en.help.roblox.com/hc/en-us/articles/360000357348",
        "email": "lawenforcement@roblox.com",
        "note": "Roblox responds to preservation and data requests from verified LE — "
                "include the username and any known game/server context.",
    },
    # Always-relevant India channel — appended to every case (see resolver below).
    "i4c": {
        "label": "I4C / National Cybercrime Portal",
        "portal": "https://cybercrime.gov.in",
        "email": "",
        "note": "Register/link the case on NCRP (helpline 1930 for financial fraud — "
                "triggers the bank/UPI freeze chain) and use the MHA Sahyog portal for "
                "expedited notices to intermediaries.",
    },
}

# scraper platform-string → directory key. Everything is lower-cased before lookup.
_ALIASES: dict[str, str] = {
    "instagram": "meta", "facebook": "meta", "fb": "meta", "meta": "meta",
    "threads": "meta",
    "whatsapp": "whatsapp",
    "snapchat": "snapchat", "snap": "snapchat",
    "telegram": "telegram",
    "google": "google", "gmail": "google", "youtube": "google", "gravatar": "google",
    "twitter": "x", "x": "x",
    "discord": "discord",
    "reddit": "reddit",
    "github": "github", "gitlab": "github",  # GitLab: same request pattern; note is generic
    "linkedin": "linkedin",
    "truecaller": "truecaller",
    "pinterest": "pinterest",
    "roblox": "roblox",
}


def _match_tier(c: dict) -> str:
    return (c.get("match") or {}).get("tier") or c.get("tier") or "LOW"


def data_request_contacts(entities: list[dict], clusters: list[dict],
                          limit: int = 6) -> list[dict]:
    """Resolve the LE data-request contacts for the platforms THIS case surfaced.

    Only platforms sitting in a HIGH/MEDIUM match cluster count (those are the accounts an
    officer would actually request data on); if no cluster qualifies, fall back to every
    account found. The I4C/NCRP entry is always appended last. Never raises.
    """
    try:
        strong_ids: set = set()
        for c in clusters or []:
            if _match_tier(c) in ("HIGH", "MEDIUM"):
                strong_ids.update(c.get("entity_ids") or [])

        pool = [e for e in entities or [] if e.get("type") in (None, "social_account")]
        strong = [e for e in pool if e.get("entity_id") in strong_ids]
        candidates = strong or pool

        # directory key -> list of "platform/handle" strings found in the case
        found: dict[str, list[str]] = {}
        for e in candidates:
            key = _ALIASES.get(str(e.get("platform") or "").strip().lower())
            if not key:
                continue
            handle = f"{e.get('platform')}/{e.get('value')}" if e.get("value") else str(e.get("platform"))
            found.setdefault(key, [])
            if handle not in found[key]:
                found[key].append(handle)

        out = []
        for key, accounts in list(found.items())[:limit]:
            entry = _DIRECTORY.get(key)
            if not entry:
                continue
            out.append({"platform": key, "accounts": accounts[:4], **entry})

        i4c = dict(_DIRECTORY["i4c"])
        out.append({"platform": "i4c", "accounts": [], **i4c})
        return out
    except Exception:  # noqa: BLE001 — guidance layer must never break results
        return []


def lookup(platform: str) -> dict | None:
    """Directory entry for one scraper platform string, or None."""
    key = _ALIASES.get(str(platform or "").strip().lower())
    return {"platform": key, **_DIRECTORY[key]} if key and key in _DIRECTORY else None
