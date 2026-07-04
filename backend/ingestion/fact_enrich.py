"""
backend/ingestion/fact_enrich.py — structured fact extraction from bio text
(employer/school, city) into metadata["employer_candidates"] / ["location_candidates"].

Model choice: LLM extraction (backend.llm.llm_client.LLMClient.extract_facts) rather
than spaCy's en_core_web_sm NER model, which requirements.txt had planned but never
wired up. Reasoning:
  - spaCy itself installs cleanly on Windows (pure wheel), but en_core_web_sm is a
    ~12 MB model that must be downloaded separately (`python -m spacy download
    en_core_web_sm`) — the exact "bundle a binary the user must fetch" problem this
    project already solved once for the face-matching ONNX models. Reusing the LLM
    client avoids a SECOND such dependency in one pass.
  - The LLM client is already wired into this exact pipeline stage (orchestrator.py's
    entity-extraction step) with the same fail-safe/timeout/degrade conventions this
    module reuses verbatim.
  - Per the correlation-accuracy discipline established in reranker.py: LLM-derived
    facts are inherently less reliable than a deterministic library, so
    employer_overlap/city_match are wired as _CONTEXT_SIGNALS (never a hard anchor)
    in scoring_engine.py regardless of which extraction path is used — spaCy would
    not have earned a higher tier here either, so the accuracy cost of skipping it
    is zero at the tier level.

NER is noisy: metadata["employer_candidates"] / ["location_candidates"] are LISTS,
never collapsed to a single guessed value — correlation_engine.py's employer_overlap/
city_match require an exact (normalized) shared entry between two profiles' candidate
lists, not a single best guess compared naively.

Fail-safe: any LLM/parsing error yields empty candidate lists for that profile; it
never raises. Bounded to profiles with real bio/text_sample content, capped like the
existing entity-extraction step, to keep the LLM call budget predictable.
Only meaningful in DATA_MODE=live; the orchestrator guards the call.
"""
from __future__ import annotations

import asyncio
import re

from backend.llm.llm_client import LLMClient

_MAX_PROFILES = 6    # Keeps the per-investigation LLM call budget small. This fires one
                      # call per profile; combined with entity-extraction + per-cluster
                      # explanations + rerank, a higher cap saturates the LLM provider's
                      # free-tier per-minute limit and forces the whole run onto slow
                      # 429-retry paths. 6 covers the richest-bio profiles, which is where
                      # employer/city facts actually come from.

# -------------------------------------------------------------------------- #
#  Deterministic fallback (used when the LLM is unavailable — e.g. Groq 429'd
#  and NVIDIA timed out). Conservative, high-precision patterns only: these
#  feed context-tier signals (employer_overlap / city_match), so recall matters
#  less than not manufacturing a shared "University" token that could falsely
#  link two unrelated people. Deliberately generic across platforms — any bio
#  text, not GitHub-specific.
# -------------------------------------------------------------------------- #

# A proper-noun token: starts capitalized, no interior '.' (so "University." can't
# swallow the following sentence's first word). Allows &, ', - for "AT&T", "O'Reilly".
_TOK = r"[A-Z][A-Za-z0-9&'-]*"
# "<role> at/@ <Proper Noun>" — captures the employer/school after a role verb.
_ROLE_AT_RE = re.compile(
    r"(?i:\b(?:works?|working|worked|employed|studies|studying|student|intern|interning|"
    r"engineer|developer|sde|swe|analyst|manager|founder|co-?founder|ceo|cto|researcher|"
    r"scientist|consultant|associate|freelancer)\s+(?:at|@)\s+)"
    rf"({_TOK}(?:\s+{_TOK}){{0,4}})"
)
# Explicit institution phrases ending in a school/company keyword.
_INSTITUTION_RE = re.compile(
    rf"\b({_TOK}(?:\s+{_TOK}){{0,4}}\s+"
    r"(?:University|College|Institute|Polytechnic|Academy|School|Technologies|Technology|Labs|Systems|Solutions))\b"
)
# Well-known Indian institute acronyms (optionally with a campus name).
_ACRONYM_INST_RE = re.compile(
    r"\b((?:IIT|NIT|IIIT|BITS|VIT|SRM|PES|RVCE|BMSCE|MSRIT|DTU|NSUT|VTU|IIM|IISc|AIIMS)"
    r"(?:\s+[A-Z][a-zA-Z]+){0,2})\b"
)
# City cues — only unambiguous ones ("from X" is deliberately excluded; it mis-fires,
# e.g. "photos from Ashwin", per profile_page_fetcher's same note).
_CITY_RE = re.compile(
    r"(?i:\b(?:based\s+in|lives?\s+in|living\s+in|located\s+in|location[:\-]\s*|currently\s+in)\s*|📍\s*)"
    rf"({_TOK}(?:\s+{_TOK}){{0,2}})"
)

# Single generic words that must NEVER stand alone as an employer/school candidate —
# they'd match across unrelated people and manufacture a false employer_overlap.
_GENERIC_ORG = {
    "university", "college", "institute", "school", "academy", "technology",
    "technologies", "labs", "systems", "solutions", "polytechnic", "company",
}


def _clean_candidate(s: str, max_len: int = 60) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().strip(".,;:").strip()[:max_len]


def _dedupe_ci(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = _clean_candidate(v)
        k = v.lower()
        if v and k not in seen and k not in _GENERIC_ORG and len(v) >= 3:
            seen.add(k)
            out.append(v)
    return out


def deterministic_facts(text: str) -> dict:
    """Regex-only employer/school + city extraction. Never raises; used as a fallback
    (and augmenter) for the LLM path so bio facts still surface when the LLM is down."""
    text = str(text or "")
    if not text.strip():
        return {"employers": [], "locations": []}
    employers = _dedupe_ci([
        *_ROLE_AT_RE.findall(text),
        *_INSTITUTION_RE.findall(text),
        *_ACRONYM_INST_RE.findall(text),
    ])[:5]
    locations = _dedupe_ci(_CITY_RE.findall(text))[:5]
    return {"employers": employers, "locations": locations}


def _text_of(meta: dict) -> str:
    return " ".join(str(meta.get(k) or "") for k in ("bio", "text_sample", "snippet")).strip()


async def enrich_facts(profiles) -> int:
    """Extract employer/city candidates for profiles with bio/text_sample content.

    LLM first (NER-style), then unioned with a deterministic regex pass so the fields
    still populate when the LLM provider is rate-limited or down (the common case on a
    free tier). Mutates profile.metadata in place. Returns the count of profiles that
    yielded at least one candidate.
    """
    targets = [p.metadata for p in profiles
              if isinstance(getattr(p, "metadata", None), dict)
              and _text_of(p.metadata)
              and "employer_candidates" not in p.metadata]
    targets = targets[:_MAX_PROFILES]
    if not targets:
        return 0

    llm = LLMClient()

    async def _one(meta: dict) -> None:
        text = _text_of(meta)
        try:
            facts = await asyncio.to_thread(llm.extract_facts, text)
        except Exception:
            facts = {"employers": [], "locations": []}
        det = deterministic_facts(text)
        meta["employer_candidates"] = _dedupe_ci([*(facts.get("employers") or []), *det["employers"]])
        meta["location_candidates"] = _dedupe_ci([*(facts.get("locations") or []), *det["locations"]])

    await asyncio.gather(*[_one(m) for m in targets], return_exceptions=True)
    return sum(1 for m in targets
              if m.get("employer_candidates") or m.get("location_candidates"))
