"""
backend/agentic_browser/smart.py — smart OSINT lookup orchestration.

Given an identifier (value + type), route it to every registered source that handles that
type, fetch each with the right backend (Supadata for public, the authed browser for
login-gated), extract a per-source OsintDossier, and merge them into one combined dossier —
the multi-entity view (names / usernames / emails / phones / locations / accounts / timeline)
that OSINT tools present.

Never raises; each source succeeds or fails independently with a reason.
"""
from __future__ import annotations

from .sources import sources_for, build_url
from . import supadata, extractor, authed_browser
from .extractor import OsintDossier, _dedupe


def _fetch(source: dict, query: str):
    url = build_url(source, query)
    if not url:
        return None, "no result URL for this source"
    if source["auth"] == "public":
        if not supadata.available():
            return None, "SUPADATA_API_KEY not configured"
        res = supadata.scrape(url)
        if res is None:
            return None, "supadata unavailable"
        if not res.get("ok"):
            return None, f"scrape failed ({res.get('status')}): {res.get('error')}"
        return {"content": res["content"], "name": res.get("name"),
                "description": res.get("description"), "url": url}, None
    # login-gated → authed browser (dedicated profile)
    if not authed_browser.is_set_up():
        return None, "login profile not set up — run the one-time authed_browser login"
    res = authed_browser.fetch(url)
    if not res.get("ok"):
        return None, res.get("error")
    if res.get("needs_login"):
        return None, "session expired — re-run the authed_browser login"
    return {"content": res["content"], "name": res.get("title"),
            "description": None, "url": url}, None


def lookup_source(source: dict, query: str) -> dict:
    base = {"source": source["id"], "name": source["name"]}
    # API-backed sources (IntelBase) — no scraping, no quota cost.
    if source.get("auth") == "api":
        if source.get("api") == "intelbase":
            from . import intelbase
            d = intelbase.to_dossier(source.get("kind", "email"), query)
            if isinstance(d, dict):   # error dict
                return {**base, "ok": False, "error": d.get("error", "intelbase error")}
            return {**base, "ok": True, "dossier": d}
        return {**base, "ok": False, "error": f"unknown api: {source.get('api')}"}
    # scrape-backed sources (public → Supadata, login → authed browser)
    fetched, err = _fetch(source, query)
    if err:
        return {**base, "ok": False, "error": err}
    d = extractor.extract(fetched["content"], query, source["id"],
                          fetched.get("name"), fetched.get("description"))
    return {**base, "ok": True, "url": fetched["url"], "dossier": d}


def merge(dossiers: list[OsintDossier]) -> OsintDossier:
    m = OsintDossier()
    for d in dossiers:
        m.names += d.names
        m.usernames += d.usernames
        m.emails += d.emails
        m.phones += d.phones
        m.locations += d.locations
        m.accounts += d.accounts
        m.timeline += d.timeline
        m.photos += d.photos
    m.names = _dedupe(m.names, 20)
    m.usernames = _dedupe(m.usernames, 30)
    m.emails = _dedupe(m.emails, 30)
    m.phones = _dedupe(m.phones, 30)
    m.locations = _dedupe(m.locations, 20)
    m.photos = _dedupe(m.photos, 20)
    seen, acc = set(), []
    for a in m.accounts:
        k = (a.platform.lower(), (a.handle or a.url or "").lower())
        if k not in seen:
            seen.add(k)
            acc.append(a)
    m.accounts = acc[:50]
    seen_t, tl = set(), []
    for t in m.timeline:
        k = (t.date or "", t.event.lower())
        if k not in seen_t:
            seen_t.add(k)
            tl.append(t)
    m.timeline = tl[:50]
    return m


def dossier_to_profiles(d: OsintDossier, query: str, id_type: str) -> list:
    """Convert a merged dossier into RawProfiles for the correlation pipeline (the bridge
    from Quick Lookup → a full investigation)."""
    from backend.ingestion.base_module import make_profile
    profs = []
    name = d.names[0] if d.names else None
    loc = d.locations[0] if d.locations else None
    for a in d.accounts:
        plat = (a.platform or "web").lower()
        val = (a.handle or (a.url or "").rstrip("/").split("/")[-1] or query).lstrip("@")
        url = a.url or f"https://{plat}.com/{val}"
        md = {"agentic_source": True}
        if name:
            md["name"] = name
        if loc:
            md["location"] = loc
        profs.append(make_profile("social_account", val, plat, url, md, data_mode="agentic_web"))
    for e in d.emails:
        profs.append(make_profile("email", e, "email", f"mailto:{e}", {"email": e}, data_mode="agentic_web"))
    for p in d.phones:
        profs.append(make_profile("phone", p, "phone", "", {"phone": p}, data_mode="agentic_web"))
    return profs


def smart_lookup(id_type: str, query: str, include_login: bool = True,
                 max_public: int = 6) -> dict:
    """Route + fetch + extract + merge. Returns {query, type, per_source[], combined}.

    API sources (IntelBase) always run — they're free of the Supadata quota. Public
    (Supadata) sources are capped at `max_public` per lookup, highest-priority first, so a
    single lookup can't drain the ~100-request free tier. Login sources run if set up.
    """
    srcs = sources_for(id_type, include_login)
    per: list[dict] = []
    public_used = 0
    for s in srcs:
        if s["auth"] == "public":
            if public_used >= max_public:
                per.append({"source": s["id"], "name": s["name"], "ok": False,
                            "error": f"skipped (Supadata cap {max_public}/lookup reached)"})
                continue
            public_used += 1
        per.append(lookup_source(s, query))
    combined = merge([r["dossier"] for r in per if r.get("ok")])
    return {"query": query, "type": id_type, "per_source": per, "combined": combined}
