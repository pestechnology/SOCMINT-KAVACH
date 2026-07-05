"""
backend/ingestion/leak_classify.py — classify NewLeaks bot dumps into canonical fields.

The @NewleaksOsintBot scraper (newleaks_scraper.py) returns a breach profile whose
metadata carries the raw leak text. This step sorts that text into the case's canonical
identity fields (name/location/address/region/…) and a "leftover" bucket for anything
that doesn't map, writing both back onto the profile's metadata:

    metadata["leak_classified"] = {full_name, location, address, region, phone, ...}
    metadata["leak_leftover"]   = {"Father's name": ..., source-db names, links, ...}

WHY LLM + DETERMINISTIC FALLBACK (mirrors fact_enrich.py's discipline): the bot's output
is fully LABELLED ("👤Full name:", "🏘️Adres:", "🗺️ Region:", "📞Telephone:"), so a
deterministic label parser can place fields reliably and for FREE. During a live run the
shared LLM (Groq/NVIDIA) is often rate-limited (429) by the pipeline's other calls, which
would otherwise leave classification empty — so we ALWAYS run the deterministic parser,
and OVERLAY the LLM result on top when it succeeds (the LLM refines and catches anything
unlabelled). Result: fields land even when the LLM is down.

DISPLAY-ONLY (per product decision): leak_classified / leak_leftover are read ONLY by the
frontend "Leak Data" tab. They are NOT consumed by correlation_engine.py or
scoring_engine.py, so this can never shift a match tier or trip the red-herring rule.
Scoped strictly to NewLeaks output (metadata.source == "newleaks_bot").
"""
from __future__ import annotations

import asyncio

from backend.llm.llm_client import LLMClient

_MAX_PROFILES = 4          # one LLM call per NewLeaks hit; cap the shared LLM budget
_MAX_PER_FIELD = 50        # cap values per field so a huge dump can't bloat a DB row

# Header/menu lines that are never a data field.
_SKIP = ("request", "subjects made", "number of leaks", "number of results",
         "search time", "store", "limit", "mirror", "please note", "subscription",
         "random of them", "results were found")

# Label keyword (found in the bot's field label, lowercased) -> destination.
# A plain string routes to that canonical field; ("leftover", "Nice Label") routes to the
# leftover bucket. ORDER MATTERS: the most specific labels come first so, e.g., "name of
# the father" is caught before the generic "name".
_LABEL_MAP = [
    ("name of the father", ("leftover", "Father's name")),
    ("father",             ("leftover", "Father's name")),
    ("full name",          "full_name"),
    ("first name",         "first_name"),
    ("last name",          "last_name"),
    ("adres",              "address"),
    ("address",            "address"),
    ("region",             "region"),
    ("location",           "location"),
    ("city",               "city"),
    ("country",            "country"),
    ("telephone",          "phone"),
    ("phone",              "phone"),
    ("email",              "email"),
    ("mail",               "email"),
    ("password",           "password"),
    ("username",           "username"),
    ("login",              "username"),
    ("nick",               "username"),
    ("date of birth",      "date_of_birth"),
    ("birth",              "date_of_birth"),
    ("aadhaar",            ("leftover", "Document / Aadhaar")),
    ("passport",           ("leftover", "Document")),
    ("document",           ("leftover", "Document")),
    ("ip",                 "ip"),
    ("link",               ("leftover", "Links")),
    ("name",               "full_name"),   # generic 'name' LAST
]


def _is_newleaks(profile) -> bool:
    m = getattr(profile, "metadata", None) or {}
    return m.get("source") == "newleaks_bot" and bool(m.get("raw_text"))


def _clean(line: str) -> str:
    return line.replace("**", "").replace("`", "").strip()


def _deterministic_classify(raw_text: str) -> dict:
    """Place the bot's LABELLED fields into canonical + leftover buckets. Reliable and
    free — used as the always-on base (and the fallback when the LLM is rate-limited)."""
    fields: dict[str, list[str]] = {}
    leftover: dict[str, list[str]] = {}

    def add(dst: dict, key: str, value: str) -> None:
        value = value.strip().strip(",").strip()
        if not value:
            return
        lst = dst.setdefault(key, [])
        if value not in lst and len(lst) < _MAX_PER_FIELD:
            lst.append(value)

    for line in (raw_text or "").splitlines():
        c = _clean(line)
        if ":" not in c:
            continue
        label, _, value = c.partition(":")
        label_l = label.lower()
        if any(s in label_l for s in _SKIP):
            continue
        value = value.strip()
        if not value:
            continue
        for kw, target in _LABEL_MAP:
            if kw in label_l:
                if isinstance(target, tuple):
                    add(leftover, target[1], value)
                else:
                    add(fields, target, value)
                break

    # single-value lists -> scalars, for cleaner display
    def collapse(d: dict) -> dict:
        return {k: (v[0] if len(v) == 1 else v) for k, v in d.items()}

    return {"fields": collapse(fields), "leftover": collapse(leftover)}


async def enrich_leak_classification(profiles) -> int:
    """Classify NewLeaks breach dumps into canonical + leftover fields, in place.

    Deterministic parse always runs (labelled data, no cost); the LLM result is overlaid
    when available. Never raises; returns the count of profiles that got a classification."""
    targets = [p for p in profiles if _is_newleaks(p)][:_MAX_PROFILES]
    if not targets:
        return 0

    llm = LLMClient()

    async def _one(profile) -> None:
        raw = (profile.metadata or {}).get("raw_text")
        if not raw:
            return
        # 1) reliable, free base
        base = _deterministic_classify(raw)
        fields = dict(base.get("fields") or {})
        leftover = dict(base.get("leftover") or {})
        # 2) overlay the LLM when it answers (refines/adds; {} if rate-limited/down)
        try:
            llm_out = await asyncio.to_thread(llm.classify_leak_data, raw)
        except Exception:
            llm_out = {}
        if llm_out:
            fields.update(llm_out.get("fields") or {})
            leftover.update(llm_out.get("leftover") or {})
        if fields:
            profile.metadata["leak_classified"] = fields
        if leftover:
            profile.metadata["leak_leftover"] = leftover

    await asyncio.gather(*[_one(p) for p in targets], return_exceptions=True)
    return sum(1 for p in targets if "leak_classified" in (p.metadata or {}))
