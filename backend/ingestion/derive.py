"""
backend/ingestion/derive.py — deterministic identifier derivation for re-iteration.

Given one identifier already in a case (a username, name, or email), suggests other
plausible identifiers worth investigating: guessed emails from a handle, alternate
handles from a name, a name guess recovered from an opaque handle, etc.

Pure stdlib, deterministic, dependency-free (bar the two existing helpers it
reuses: username_variants() and is_plausible_name()/is_generic_name()). Every
derivation is just a NEW SEED for the existing scrape -> correlate -> score
pipeline — this module never decides linking and never fabricates evidence; a
derived username that merely LOOKS right still has to earn its signals like any
other seed (see correlation_engine.py's red-herring rule).

derive_seeds(seed_type, value) is the router callers use. The individual
emails_from_handle / handles_from_name / names_from_handle / names_from_email_local
helpers are exposed directly for reuse and unit testing.
"""
from __future__ import annotations

import re

from backend.analysis.name_intel import is_generic_name, is_plausible_name
from backend.ingestion.variants import username_variants

EMAIL_PROVIDERS = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com", "icloud.com"]

# Hard cap on total derived candidates per call — keeps a pivot's query cost bounded
# no matter how many strategies fire (see SETUP.md's "~15 queries/pivot" guard).
MAX_DERIVED_SEEDS = 20

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEP_RE = re.compile(r"[._\-\s]+")
_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def _valid_handle(v: str) -> bool:
    """Same noise/length guard the orchestrator's own expansion pipeline uses.

    Imported lazily (inside the function, not at module load time): orchestrator.py
    imports derive_seeds for the pivot task, so derive.py importing orchestrator at
    module scope would be circular. This mirrors the lazy-import pattern already used
    elsewhere in this codebase (e.g. case_service.get_results, orchestrator's own
    lazy name_intel imports).
    """
    try:
        from backend.pipeline.orchestrator import _is_valid_expansion_handle
        return _is_valid_expansion_handle(v)
    except Exception:
        v = str(v or "").strip().lower().lstrip("@")
        return 4 <= len(v) <= 40 and not v.isdigit()


def emails_from_handle(handle: str) -> list[str]:
    """h -> h@{gmail,yahoo,outlook,protonmail,icloud}.com — 5 guessed candidates."""
    h = str(handle or "").strip().lower().lstrip("@")
    if not h or not _valid_handle(h):
        return []
    if not re.fullmatch(r"[a-z0-9._+-]+", h):   # not a valid email local-part shape
        return []
    return [f"{h}@{provider}" for provider in EMAIL_PROVIDERS]


def handles_from_name(name: str, max_n: int = 5) -> list[str]:
    """Reuse the existing name -> handle variant generator."""
    return username_variants(name, max_n=max_n)


def names_from_handle(handle: str) -> list[str]:
    """Recover a plausible display name from a handle.

    "vismay_hs"    -> ["Vismay Hs"]  (separator-delimited: title-case each token)
    "vismayhs"     -> ["Vismay HS"]  (opaque blob: longest known-first-name prefix;
                                      a short (<=3 char) remainder is treated as initials)
    "ghostrider99" -> ["Ghostrider"] (de-numbered mononym, last resort)
    Returns [] when nothing plausible can be recovered (e.g. "xk3vzq99").
    """
    raw = str(handle or "").strip().lower().lstrip("@")
    if not raw:
        return []
    de_num = _TRAILING_DIGITS_RE.sub("", raw)
    if not de_num:
        return []

    out: list[str] = []

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in out and is_plausible_name(c) and not is_generic_name(c):
            out.append(c)

    spaced = _CAMEL_RE.sub(" ", de_num)               # camelCase counts as a separator too
    tokens = [t for t in _SEP_RE.split(spaced) if t]

    if len(tokens) >= 2:
        add(" ".join(t.capitalize() for t in tokens))
        return out

    # Single opaque token — try the longest known first-name prefix.
    from backend.analysis.name_intel import _COMMON_FIRST_NAMES
    token = tokens[0] if tokens else de_num
    best_prefix = ""
    for first in _COMMON_FIRST_NAMES:
        if token.startswith(first) and token != first and len(first) > len(best_prefix):
            best_prefix = first
    if best_prefix:
        remainder = token[len(best_prefix):]
        if remainder and len(remainder) <= 3:
            add(f"{best_prefix.capitalize()} {remainder.upper()}")
        elif remainder and is_plausible_name(remainder):
            add(f"{best_prefix.capitalize()} {remainder.capitalize()}")

    if not out and len(token) >= 4:
        add(token.capitalize())   # de-numbered mononym — weak, last-resort guess

    return out


def names_from_email_local(local_part: str) -> list[str]:
    """Email local-part -> name guesses, using the same recovery rules as a handle."""
    return names_from_handle(local_part)


def derive_seeds(seed_type: str, value: str) -> list[dict]:
    """Router: seed_type/value -> [{type, value, strategy, confidence}, ...].

    Never raises; a strategy that produces nothing just contributes no seeds.
    Deduplicates against the original value (case-insensitive) and caps the total
    at MAX_DERIVED_SEEDS so a pivot's query cost stays bounded.
    """
    value = str(value or "").strip()
    if not value:
        return []
    seed_type = (seed_type or "").strip().lower()
    original_lower = value.lower()
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def emit(type_: str, val: str, strategy: str, confidence: float) -> None:
        if not val:
            return
        key = (type_, val.strip().lower())
        if key[1] == original_lower or key in seen:
            return
        seen.add(key)
        out.append({"type": type_, "value": val, "strategy": strategy, "confidence": confidence})

    if seed_type == "username":
        for email in emails_from_handle(value):
            emit("email", email, "username_to_email_guess", 0.3)
        # Handle variants are derived THROUGH the recovered name (an opaque blob like
        # "vismayhs" has no separator for username_variants() to work with directly;
        # names_from_handle finds the "vismay"+"hs" split first, then username_variants
        # recombines that into vismay_hs / vismay.hs / hsvismay / ...).
        for name in names_from_handle(value):
            emit("name", name, "username_to_name_guess", 0.5)
            for handle in handles_from_name(name):
                if _valid_handle(handle):
                    emit("username", handle, "username_variant", 0.6)

    elif seed_type == "name":
        for handle in handles_from_name(value):
            if _valid_handle(handle):
                emit("username", handle, "name_to_handle_variant", 0.6)
        # A multi-word name is rarely a clean email local-part; only try compact ones.
        toks = value.split()
        if len(toks) <= 2:
            compact = "".join(toks).lower()
            for email in emails_from_handle(compact):
                emit("email", email, "name_to_email_guess", 0.25)

    elif seed_type == "email":
        local = value.split("@", 1)[0] if "@" in value else value
        if _valid_handle(local):
            emit("username", local, "email_local_part", 0.7)
            for name in names_from_email_local(local):
                emit("name", name, "email_to_name_guess", 0.5)
                for handle in handles_from_name(name):
                    if _valid_handle(handle):
                        emit("username", handle, "email_local_variant", 0.5)

    elif seed_type == "url":
        # A profile URL is the one case where the identifiers are OBSERVED, not guessed:
        # the handle/name are literally in the URL, so they get high confidence, and then
        # chain into the username strategies above exactly as a typed handle would.
        # A non-profile URL (post/video/group) yields nothing — see url_scraper.py for
        # why a reserved path must never become a username seed.
        from backend.ingestion.url_scraper import extract_profile_url

        info = extract_profile_url(value)
        if info and info.get("kind") == "profile":
            handle = info.get("handle")
            name_hint = info.get("name_hint")

            if handle and _valid_handle(handle):
                emit("username", handle, "url_handle", 0.9)
                # Chain: everything derive_seeds() already knows how to do with a handle.
                for email in emails_from_handle(handle):
                    emit("email", email, "url_handle_to_email_guess", 0.3)
                for name in names_from_handle(handle):
                    emit("name", name, "url_handle_to_name_guess", 0.5)
                    for variant in handles_from_name(name):
                        if _valid_handle(variant):
                            emit("username", variant, "url_handle_variant", 0.6)

            if name_hint:
                # Observed in the URL slug, so more trustworthy than a name GUESSED
                # from an opaque handle (0.5 above).
                emit("name", name_hint, "url_slug_name", 0.8)
                for variant in handles_from_name(name_hint):
                    if _valid_handle(variant):
                        emit("username", variant, "url_name_to_handle_variant", 0.6)

            # platform_id (Facebook numeric / YouTube channel / Twitter numeric) is a
            # real identifier and is recorded in the URL profile's metadata by
            # URLScraper, but it is deliberately NOT emitted as a seed: there is no
            # scraper keyed on a platform-native id, and it is not a username (it would
            # be rejected by _valid_handle anyway).

    return out[:MAX_DERIVED_SEEDS]


def estimate_query_count(derived: list[dict]) -> int:
    """Rough Serper-query budget for running these derived seeds (the one paid
    dependency) — every username/name/email seed goes through SerperScraper once
    in _scrape_seed's tool map, so 1 candidate ~= 1 Serper query."""
    return len([d for d in derived if d.get("type") in ("username", "name", "email")])
