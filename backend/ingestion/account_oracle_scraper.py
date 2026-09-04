"""
backend/ingestion/account_oracle_scraper.py — extensible account-existence oracles.

This is the "how does fingerprint.to find a Snapdeal/Duolingo account?" mechanism:
per-service checks that reveal whether an email or username has an account there,
using each service's own public/registration API — the same technique holehe uses,
but as an IN-REPO registry we can extend, instead of holehe's frozen module set.

WHY A SEPARATE FILE FROM holehe_scraper.py:
  holehe is shelled out to as a CLI with a fixed ~120-site list; we can't add sites to
  it. This registry is where VERTEX-specific oracles live — especially ones holehe does
  NOT cover (verified at build time: chess.com, lichess, gitlab, duolingo). Each oracle
  that returns rich profile fields (name, location, join date) also enriches, so these
  beat holehe's binary yes/no.

THE ONE SAFETY RULE — `notifies_target`:
  Some existence checks silently email/OTP the account owner (any "forgot password"
  flow). For an investigation that means TIPPING OFF THE SUBJECT. Every oracle declares
  `notifies_target`; this scraper runs ONLY oracles with notifies_target=False. A
  notifying oracle can be added to the registry for documentation, but it is never
  executed here — running it would require a separate, explicit, logged opt-in that
  does not exist yet. Do not flip this to run notifying oracles without that opt-in.

  This is why the Indian consumer apps in the fingerprint.to demo (Jio, Snapdeal, AJIO,
  Zomato, Swiggy) are NOT here: they authenticate by phone+OTP, so an existence probe
  sends the subject an OTP (notifies_target=True) AND needs per-app reverse-engineering
  of an undocumented mobile API with ongoing upkeep. They belong in a future, opt-in,
  individually-reviewed batch — not this always-on, safe-by-default set.

Adding an oracle: append one Oracle(...) to _ORACLES with a check(resp)->bool|dict.
Fail-safe throughout: any oracle that errors/times out contributes nothing.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import httpx

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

_TIMEOUT = 10.0
_CONCURRENCY = 8
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


@dataclass
class Oracle:
    name: str                 # service name (also the profile.platform)
    domain: str               # service domain
    id_type: str              # "username" | "email"
    notifies_target: bool     # True => sends the subject a mail/OTP => NEVER auto-run
    url: Callable[[str], str] # identifier -> request URL
    # check(response) -> False if no account, or a dict of extra metadata if it exists
    # (an empty dict still counts as "exists"). Must never raise on a normal response.
    check: Callable[[httpx.Response], "bool | dict"]


# -------------------------------------------------------------------------------------
# Verified oracles. Each was confirmed live at build time against a real identifier, is
# non-notifying, and is NOT already covered by holehe. All four return rich fields, so
# they enrich as well as confirm existence.
# -------------------------------------------------------------------------------------
def _chesscom_check(r):
    if r.status_code != 200:
        return False
    d = r.json()
    if not d.get("username"):
        return False
    meta = {}
    if d.get("name"):
        meta["name"] = d["name"]
    if d.get("joined"):
        meta["joined_ts"] = d["joined"]
    if isinstance(d.get("country"), str):
        meta["country_url"] = d["country"]
    return meta


def _lichess_check(r):
    if r.status_code != 200:
        return False
    d = r.json()
    if not (d.get("id") or d.get("username")):
        return False
    meta = {}
    if d.get("username"):
        meta["display_username"] = d["username"]
    if d.get("createdAt"):
        meta["created_at_ms"] = d["createdAt"]
    return meta


def _gitlab_check(r):
    if r.status_code != 200:
        return False
    d = r.json()
    if not (isinstance(d, list) and d):
        return False
    u = d[0]
    meta = {}
    if u.get("name"):
        meta["name"] = u["name"]
    if u.get("public_email"):
        meta["email"] = u["public_email"]
    if u.get("avatar_url"):
        meta["photo_url"] = u["avatar_url"]
    if u.get("id"):
        meta["platform_id"] = str(u["id"])
    return meta


def _duolingo_check(r):
    if r.status_code != 200:
        return False
    users = (r.json() or {}).get("users") or []
    if not users:
        return False
    u = users[0]
    meta = {}
    if u.get("name"):
        meta["name"] = u["name"]
    if u.get("username"):
        meta["display_username"] = u["username"]
    return meta


_ORACLES: list[Oracle] = [
    Oracle("chess.com", "chess.com", "username", False,
           lambda v: f"https://api.chess.com/pub/player/{v.lower()}", _chesscom_check),
    Oracle("lichess", "lichess.org", "username", False,
           lambda v: f"https://lichess.org/api/user/{v}", _lichess_check),
    Oracle("gitlab", "gitlab.com", "username", False,
           lambda v: f"https://gitlab.com/api/v4/users?username={v}", _gitlab_check),
    Oracle("duolingo", "duolingo.com", "username", False,
           lambda v: f"https://www.duolingo.com/2017-06-30/users?username={v}", _duolingo_check),
]


class AccountOracleScraper(BaseDataSource):
    name = "account_oracle"

    async def _check_one(self, client, sem, oracle: Oracle, identifier: str):
        async with sem:
            try:
                r = await client.get(oracle.url(identifier),
                                     headers={"User-Agent": _UA, "Accept": "application/json"})
            except Exception:
                return None
        try:
            result = oracle.check(r)
        except Exception:
            return None
        if result is False:
            return None
        extra = result if isinstance(result, dict) else {}
        return make_profile(
            "account_existence", identifier, oracle.name, f"https://{oracle.domain}",
            metadata={
                "registered": True,
                "service": oracle.name,
                "checked_by": oracle.id_type,
                "source": "account_oracle",
                **extra,
            },
        )

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        ident = (identifier or "").strip()
        if not ident:
            return []
        id_type = "email" if "@" in ident else "username"
        # SAFETY: only ever run non-notifying oracles matching this identifier type.
        oracles = [o for o in _ORACLES
                   if o.id_type == id_type and not o.notifies_target]
        if not oracles:
            return []
        sem = asyncio.Semaphore(_CONCURRENCY)
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            results = await asyncio.gather(
                *[self._check_one(client, sem, o, ident) for o in oracles],
                return_exceptions=True,
            )
        return [p for p in results if isinstance(p, RawProfile)]
