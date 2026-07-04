"""
backend/agentic_browser/extractor.py — turn scraped page content into structured OSINT.

Input: the Markdown/text a fetch backend returned (Supadata or the authed browser) for a
query. Output: an OsintDossier — the multi-entity view OSINT tools show (names, usernames,
emails, phones, locations, linked accounts, timeline, photos).

Design:
  * Deterministic regex first for emails & phones — high precision, zero fabrication risk,
    and it still works if the LLM is unavailable.
  * Groq LLM (text, no vision) for the judgement calls (real names vs handles, locations,
    which links are the subject's accounts, timeline events), constrained to the page content
    with a hard anti-fabrication rule.
Never raises; degrades to the regex-only dossier on any LLM failure.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from pydantic import BaseModel, Field

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# phone: optional +, then 7–15 digits with common separators; validated by digit count after.
_PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{6,18}\d(?![\w])")


class LinkedAccount(BaseModel):
    platform: str
    handle: Optional[str] = None
    url: Optional[str] = None


class TimelineEvent(BaseModel):
    date: Optional[str] = None
    event: str


class OsintDossier(BaseModel):
    names: List[str] = Field(default_factory=list)
    usernames: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    accounts: List[LinkedAccount] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    source: Optional[str] = None


def _dedupe(items, limit=25):
    out, seen = [], set()
    for it in items:
        k = str(it).strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(str(it).strip())
        if len(out) >= limit:
            break
    return out


def _regex_contacts(text: str):
    emails = _dedupe(_EMAIL_RE.findall(text or ""), 25)
    phones = []
    for m in _PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", m)
        if 7 <= len(digits) <= 15:
            phones.append(m.strip())
    return emails, _dedupe(phones, 25)


_SYSTEM = (
    "You are an OSINT extraction analyst. You are given text scraped from ONE web page about "
    "a subject. Extract ONLY facts literally present in the text into strict JSON with keys: "
    '"names" (real human names), "usernames" (handles, @ stripped), "emails", "phones", '
    '"locations" (cities/regions/countries), "accounts" (array of {platform, handle, url} for '
    'the subject\'s social/other accounts), "timeline" (array of {date, event} for dated '
    'activity), "photos" (image URLs). '
    "ABSOLUTE RULE: never invent, guess, or infer a value that is not in the text. If a field "
    "has nothing, use an empty array. Deduplicate. Output ONLY the JSON."
)


def extract(content: str, query: str = "", source: str = "",
            name_hint: Optional[str] = None, description_hint: Optional[str] = None) -> OsintDossier:
    """Extract an OsintDossier from scraped page content. Regex for contacts + LLM for the rest."""
    text = (content or "")
    if description_hint:
        text = description_hint + "\n" + text
    emails, phones = _regex_contacts(text)
    dossier = OsintDossier(emails=emails, phones=phones, source=source or None)

    # LLM enrichment (Groq via the shared client). Bounded input; fail-safe.
    try:
        from backend.llm.llm_client import LLMClient
        from backend import config
        payload = text[:6000]
        hint = f"Page title: {name_hint}\n" if name_hint else ""
        llm = LLMClient()
        out = llm._chat_with_failover(
            config.LLM_EXTRACT_MODEL,
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": f"Subject query: {query!r}\n{hint}\nPAGE TEXT:\n{payload}"}],
            temperature=0.0, max_tokens=900,
        )
        out = (out or "").strip()
        if out.startswith("```"):
            out = out.strip("`")
            out = out[4:] if out.startswith("json") else out
        s, e = out.find("{"), out.rfind("}")
        if s >= 0 and e > s:
            data = json.loads(out[s:e + 1])
            if isinstance(data, dict):
                dossier.names = _dedupe((dossier.names or []) + list(data.get("names") or []), 15)
                dossier.usernames = _dedupe(
                    [str(u).lstrip("@") for u in (data.get("usernames") or [])], 25)
                dossier.emails = _dedupe((dossier.emails or []) + list(data.get("emails") or []), 25)
                dossier.phones = _dedupe((dossier.phones or []) + list(data.get("phones") or []), 25)
                dossier.locations = _dedupe(list(data.get("locations") or []), 15)
                dossier.photos = _dedupe(list(data.get("photos") or []), 15)
                accts = []
                for a in (data.get("accounts") or []):
                    if isinstance(a, dict) and (a.get("platform") or a.get("url")):
                        accts.append(LinkedAccount(platform=str(a.get("platform") or "web"),
                                                   handle=a.get("handle"), url=a.get("url")))
                dossier.accounts = accts[:40]
                tl = []
                for t in (data.get("timeline") or []):
                    if isinstance(t, dict) and t.get("event"):
                        tl.append(TimelineEvent(date=t.get("date"), event=str(t.get("event"))[:200]))
                dossier.timeline = tl[:40]
    except Exception:  # noqa: BLE001 — keep the regex-only dossier on any failure
        pass

    # Drop gibberish / page-title junk / placeholder names (reuse the fake-name resistance).
    try:
        from backend.analysis.name_intel import is_plausible_name, is_generic_name
        dossier.names = _dedupe(
            [n for n in dossier.names if is_plausible_name(n) and not is_generic_name(n)], 15)
    except Exception:  # noqa: BLE001
        pass
    return dossier
