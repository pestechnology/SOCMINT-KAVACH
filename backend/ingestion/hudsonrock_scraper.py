"""
backend/ingestion/hudsonrock_scraper.py — free info-stealer exposure lookup (no API key).

Hudson Rock's Cavalier "osint-tools" endpoints answer a question none of the other
breach sources here can: was this person's MACHINE infected by an info-stealer, and
when. That is a different signal from breach membership — a breach says "a site you
used was hacked years ago", an info-stealer hit says "this individual's own computer
was compromised and everything saved in their browser was exfiltrated", usually
recently. For an investigation the second is far higher-signal.

Free, key-less, and supports BOTH an email and a username, so it plugs into both seed
paths. Endpoint chosen by whether the identifier contains "@".

Response shape (identical for both endpoints):
    {"message": "...", "stealers": [ {...}, ... ],
     "total_corporate_services": N, "total_user_services": N}
A miss returns stealers: [] — detection keys off that array being non-empty rather
than string-matching `message`, which is marketing copy and can change.

DELIBERATE OMISSION — `top_passwords`: the free tier returns them masked
("s********8"). Masked partial credentials carry PII/liability for a court-facing
tool while adding almost nothing an investigator can act on, so they are dropped.
`top_logins` IS kept: partially-masked logins ("e**********@gmail.com") are a genuine
pivot lead toward an address, and the domain is visible.

NOT fed into metadata["breaches"]: that field drives correlation_engine's
breach_co_occurrence signal, which deliberately ignores mega-breaches because millions
of unrelated people share them. "Was infected by a stealer" is the same kind of
non-discriminating property — two unrelated infected people must never correlate on it.

Fail-safe: returns [] on any error, non-200, or malformed body.
"""
from __future__ import annotations

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_BASE = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools"
_TIMEOUT = 15.0
_UA = "Mozilla/5.0 (compatible; VERTEX-OSINT/1.0)"
# Cap what we store: a heavily-infected identifier can return many stealer records.
_MAX_STEALERS = 10


def _clean(value) -> str | None:
    """Hudson Rock uses the literal string 'Not Found' for absent fields."""
    s = str(value or "").strip()
    if not s or s.lower() in ("not found", "none", "null", "unknown"):
        return None
    return s


class HudsonRockScraper(BaseDataSource):
    name = "hudsonrock"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        ident = (identifier or "").strip()
        if not ident:
            return []
        if "@" in ident:
            url = f"{_BASE}/search-by-email"
            params = {"email": ident}
        else:
            url = f"{_BASE}/search-by-username"
            params = {"username": ident}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(url, params=params, headers={"User-Agent": _UA})
                if r.status_code != 200:
                    return []
                data = r.json()
        except Exception:
            return []

        if not isinstance(data, dict):
            return []
        stealers = data.get("stealers")
        if not isinstance(stealers, list) or not stealers:
            return []          # clean miss — not an error

        families, computers, systems, logins, dates = [], [], [], [], []
        for s in stealers[:_MAX_STEALERS]:
            if not isinstance(s, dict):
                continue
            for value, bucket in (
                (_clean(s.get("stealer_family")), families),
                (_clean(s.get("computer_name")), computers),
                (_clean(s.get("operating_system")), systems),
                (_clean(s.get("date_compromised")), dates),
            ):
                if value and value not in bucket:
                    bucket.append(value)
            for lg in (s.get("top_logins") or []):
                lg = _clean(lg)
                if lg and lg not in logins:
                    logins.append(lg)

        is_email = "@" in ident
        meta = {
            "infostealer_infection": True,
            "stealer_count": len(stealers),
            "source": "hudsonrock",
            "identifier_kind": "email" if is_email else "username",
            # Info-stealer output is credential-adjacent: flag it the same way the
            # other credential-bearing sources are, so the UI/report can treat it
            # distinctly from an ordinary discovered profile.
            "sensitive_source": True,
        }
        if not is_email:
            # A username is NOT a unique identity. Hudson Rock returns every infected
            # machine whose stolen credentials contained this handle, so a common
            # handle conflates unrelated people — a live probe for "admin" came back
            # with machines named ShahJalal, rohan and SaiTheONE in one response.
            # An email match is identity-bearing; a username match is a LEAD ONLY.
            # Stated explicitly so neither the report nor an analyst reads this as
            # "the subject's machine was compromised".
            meta["identity_confirmed"] = False
            meta["note"] = ("Handle-scoped match: these infections belong to accounts using "
                            "this username, which may be different people. Lead only — "
                            "not evidence that the subject's own machine was infected.")
        else:
            meta["identity_confirmed"] = True
        if families:
            meta["stealer_families"] = families
        if computers:
            # Machine names very often embed a real name ("DESKTOP-XXX (ShahJalal)").
            meta["compromised_computers"] = computers
        if systems:
            meta["operating_systems"] = systems
        if dates:
            meta["date_compromised"] = sorted(dates)[-1]      # most recent
            meta["dates_compromised"] = sorted(dates)
        if logins:
            meta["masked_logins"] = logins[:20]
        for key in ("total_user_services", "total_corporate_services"):
            value = data.get(key)
            if isinstance(value, int):
                meta[key] = value

        return [make_profile(
            "breach", ident, "hudsonrock", "https://www.hudsonrock.com/free-tools",
            metadata=meta,
        )]
