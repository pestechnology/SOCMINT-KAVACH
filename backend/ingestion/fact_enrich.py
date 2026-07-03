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

from backend.llm.llm_client import LLMClient

_MAX_PROFILES = 15   # same order of magnitude as orchestrator.py's blobs[:10] entity-
                      # extraction cap — keeps the LLM call budget bounded and predictable.


def _text_of(meta: dict) -> str:
    return " ".join(str(meta.get(k) or "") for k in ("bio", "text_sample")).strip()


async def enrich_facts(profiles) -> int:
    """Extract employer/city candidates for profiles with bio/text_sample content.

    Mutates profile.metadata in place. Returns the count of profiles that yielded at
    least one candidate.
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
        try:
            facts = await asyncio.to_thread(llm.extract_facts, _text_of(meta))
        except Exception:
            facts = {"employers": [], "locations": []}
        meta["employer_candidates"] = facts.get("employers", [])
        meta["location_candidates"] = facts.get("locations", [])

    await asyncio.gather(*[_one(m) for m in targets], return_exceptions=True)
    return sum(1 for m in targets
              if m.get("employer_candidates") or m.get("location_candidates"))
