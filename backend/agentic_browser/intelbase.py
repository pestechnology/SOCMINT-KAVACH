"""
backend/agentic_browser/intelbase.py — IntelBase OSINT lookup API client.

A proper API (no browser, no Cloudflare): POST https://api.intelbase.is/lookup/{kind} with an
`x-api-key` header. Returns accounts registered to an email/username/phone, plus breach and
infostealer-log intelligence. IntelBase requires your IP to be whitelisted in the dashboard —
until then it returns 401.

Fail-safe: never raises; returns {"ok": bool, ...}.
"""
from __future__ import annotations

import httpx

from backend import config

_BASE = "https://api.intelbase.is"
# supported lookup kinds → identifier field name in the JSON body
_KINDS = {"email": "email", "username": "username", "phone": "phone", "name": "name"}


def available() -> bool:
    return bool(config.INTELBASE_API_KEY)


def lookup(kind: str, value: str, include_breaches: bool = True, timeout_ms: int = 8000) -> dict:
    """POST /lookup/{kind}. Returns {"ok": True, "data": <json>} or {"ok": False, "error"}."""
    if not config.INTELBASE_API_KEY:
        return {"ok": False, "error": "INTELBASE_API_KEY not configured"}
    field = _KINDS.get(kind)
    if not field:
        return {"ok": False, "error": f"unsupported lookup kind: {kind}"}
    body = {field: value, "include_data_breaches": include_breaches, "timeout_ms": timeout_ms}
    try:
        r = httpx.post(f"{_BASE}/lookup/{kind}",
                       headers={"x-api-key": config.INTELBASE_API_KEY, "Content-Type": "application/json"},
                       json=body, timeout=(timeout_ms / 1000) + 15)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if r.status_code == 401:
        return {"ok": False, "status": 401,
                "error": "401 — check the key and WHITELIST YOUR IP at intelbase.is/dashboard/account"}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "error": (r.text or "")[:200]}
    try:
        return {"ok": True, "data": r.json()}
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "non-JSON response"}


def to_dossier(kind: str, value: str) -> "object | None":
    """Run an IntelBase lookup and fold it into an OsintDossier. Best-effort field mapping —
    IntelBase returns nested account/breach data; we pull the common identifiers out."""
    from .extractor import OsintDossier, LinkedAccount
    res = lookup(kind, value)
    if not res.get("ok"):
        return res  # propagate the error dict so the caller can show the reason
    data = res.get("data") or {}
    d = OsintDossier(source="intelbase")
    # IntelBase groups results under modules/accounts; harvest defensively across shapes.
    accounts = data.get("accounts") or data.get("results") or data.get("modules") or []
    if isinstance(accounts, dict):
        accounts = list(accounts.values())
    for a in accounts if isinstance(accounts, list) else []:
        if not isinstance(a, dict):
            continue
        plat = a.get("platform") or a.get("module") or a.get("name") or a.get("site") or "unknown"
        d.accounts.append(LinkedAccount(platform=str(plat),
                                        handle=a.get("username") or a.get("handle"),
                                        url=a.get("url") or a.get("profile_url")))
        for u in ([a.get("username")] if a.get("username") else []):
            d.usernames.append(u)
        for e in ([a.get("email")] if a.get("email") else []):
            d.emails.append(e)
    # de-dupe
    from .extractor import _dedupe
    d.usernames = _dedupe(d.usernames, 40)
    d.emails = _dedupe(d.emails, 40)
    if kind == "email":
        d.emails = _dedupe([value] + d.emails, 40)
    return d
