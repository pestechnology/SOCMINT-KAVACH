"""
backend/analysis/name_intel.py — name plausibility, genericness, and cluster identity.

Two OSINT realities this handles, plus a false-link guard:

  1. Suspects use FAKE / gibberish DISPLAY names ("xk3vzq", "asdfgh"). Such a string must
     never be shown as a real name, never drive a link, and is an alias — not an identity.
     `is_plausible_name` scores whether a string looks like a real human name
     (pronounceable, vowel-bearing, digit-free). It applies to the DISPLAY-NAME field
     ONLY — usernames are *expected* to be gibberish and must be exempt, otherwise a
     gibberish-handle investigation (a strong, unique selector) would be penalised.

  2. Even a suspect who hides their name on the main account usually LEAKS it on one
     careless/old account that hard signals tie into the same cluster.
     `resolve_cluster_identity` lifts the best real name found on ANY member up to label
     the whole persona — the "leak-account pivot".

  3. A shared PLACEHOLDER name ("John Doe") or a lone common first name ("Ashwin") is not
     identifying evidence. `is_generic_name` flags these so the correlation engine can
     demote the name signal and two unrelated accounts can't be linked on the name alone.

Dependency-free and deterministic (stdlib only). Never raises.
"""
from __future__ import annotations

import html as _htmllib
import json
import re

_VOWELS = set("aeiouy")

# Placeholder / throwaway "names" that are never a real person.
_PLACEHOLDER_NAMES = {
    "john doe", "jane doe", "john smith", "jane smith", "test user", "test test",
    "user", "username", "admin", "administrator", "test", "guest", "member",
    "unknown", "unknown user", "anonymous", "anon", "no name", "noname", "n/a",
    "na", "null", "none", "nil", "default", "profile", "account", "asdf", "asdfgh",
    "asdfasdf", "qwerty", "abc", "abcd", "abcde", "xyz", "foo", "bar", "foobar",
    "lorem ipsum", "first last", "firstname lastname", "your name", "full name",
}

# Common given names that, ALONE (no surname), aren't identifying. Kept moderate and
# focused on the tool's likely target population + common Western names.
_COMMON_FIRST_NAMES = {
    "aarav", "aditya", "akash", "amit", "ananya", "anil", "anita", "anjali", "ankit",
    "arjun", "arun", "ashwin", "deepak", "divya", "gaurav", "harish", "karan", "kavya",
    "kiran", "krishna", "manish", "meera", "mohan", "neha", "nikhil", "pooja", "prakash",
    "pranav", "priya", "rahul", "raj", "rajesh", "ram", "ravi", "rohit", "sagar", "sanjay",
    "shreya", "shyam", "sneha", "sourav", "sri", "sunil", "suresh", "swati", "varun",
    "vijay", "vikas", "vikram", "vishal", "vivek", "yash", "vismay", "dhanush",
    "aaron", "adam", "alex", "alice", "amy", "andrew", "anna", "ben", "bob", "brian",
    "carol", "chris", "dan", "dave", "david", "emily", "emma", "eric", "james", "jane",
    "jason", "jeff", "jenny", "john", "jose", "josh", "julia", "kevin", "laura", "lee",
    "linda", "lisa", "mark", "mary", "matt", "max", "mike", "nick", "paul", "peter",
    "rachel", "rob", "ryan", "sam", "sara", "sarah", "sean", "steve", "tom", "will",
}


def _clean(s) -> str:
    return _htmllib.unescape(str(s or "")).strip()


def _token_plausible(tok: str) -> bool:
    """Is a single word pronounceable enough to be part of a real name?"""
    letters = [c for c in tok.lower() if c.isalpha()]
    n = len(letters)
    if n < 2:
        return False
    vowels = sum(1 for c in letters if c in _VOWELS)
    if vowels == 0:                       # "xkvzq", "bcdfg" — no vowel at all
        return False
    if n >= 4 and vowels / n < 0.20:      # far too few vowels for a real name
        return False
    run = mx = 0                          # longest consonant run
    for c in letters:
        if c in _VOWELS:
            run = 0
        else:
            run += 1
            mx = max(mx, run)
    if mx >= 5:                           # "brzczk" — implausible consonant cluster
        return False
    return True


def is_plausible_name(s: str) -> bool:
    """True if `s` looks like a real human DISPLAY name (not gibberish/placeholder).

    DISPLAY NAMES ONLY — never call on a username/handle (they are legitimately
    gibberish). Non-Latin scripts are accepted (the heuristic is Latin-specific).
    """
    s = (s or "").strip()
    if len(s) < 2 or len(s) > 60:
        return False
    if any(ch.isdigit() for ch in s):     # real human names don't contain digits
        return False
    low = s.lower()
    if low in _PLACEHOLDER_NAMES:
        return False
    alpha = [c for c in s if c.isalpha()]
    if not alpha:
        return False
    # Non-Latin (Devanagari, Cyrillic, CJK, Arabic…): can't judge pronounceability, accept.
    latin = [c for c in alpha if ord(c) < 128]
    if len(latin) < 0.6 * len(alpha):
        return True
    toks = [t for t in re.split(r"[\s._'-]+", low) if any(c.isalpha() for c in t)]
    if not toks:
        return False
    # Evaluate only tokens with >=2 letters; single-letter tokens are INITIALS ("Vismay
    # H S") and are neutral, not gibberish, so they must not drag down the vote.
    multi = [t for t in toks if sum(c.isalpha() for c in t) >= 2]
    if not multi:
        return True   # all-initials ("A B") — neutral, accept
    plausible = sum(1 for t in multi if _token_plausible(t))
    return plausible * 2 >= len(multi)   # at least half the real tokens pronounceable


def is_generic_name(s: str) -> bool:
    """A name too common/placeholder to be identifying evidence on its own: a known
    placeholder ("John Doe") or a LONE common first name ("Ashwin"). A distinctive
    multi-token name ("Ashwin Harish") is NOT generic."""
    low = (s or "").strip().lower()
    if not low:
        return False
    if low in _PLACEHOLDER_NAMES:
        return True
    toks = low.split()
    if len(toks) == 1 and toks[0] in _COMMON_FIRST_NAMES:
        return True
    return False


def resolve_cluster_identity(members: list) -> dict | None:
    """Best real name for a linked persona cluster — the leak-account pivot.

    Scans the cluster's member accounts for display names, keeps only PLAUSIBLE,
    NON-GENERIC names, and returns the strongest: preferring a name that appears on
    more members, then one carried by the exact-match anchor, then a fuller name.
    Returns None when no member leaked a usable real name.

    `members` is a list of entity dicts (each with `.metadata` dict and `.platform`).
    """
    cand: dict[str, dict] = {}
    for e in members or []:
        m = (e.get("metadata") if isinstance(e, dict) else None) or {}
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except Exception:
                m = {}
        raw = _clean(m.get("name") or m.get("fullname"))
        if not raw or not is_plausible_name(raw) or is_generic_name(raw):
            continue
        key = raw.lower()
        c = cand.setdefault(key, {"display": raw, "platforms": set(), "count": 0,
                                  "anchor": False, "tokens": len(raw.split())})
        c["count"] += 1
        plat = (e.get("platform") or "") if isinstance(e, dict) else ""
        if plat:
            c["platforms"].add(plat)
        if m.get("exact_seed_match"):
            c["anchor"] = True
    if not cand:
        return None
    best = max(cand.values(), key=lambda c: (c["count"], c["anchor"], c["tokens"]))
    return {
        "name": best["display"],
        "source_platform": sorted(best["platforms"])[0] if best["platforms"] else None,
        "support": best["count"],
        "from_anchor": best["anchor"],
    }
