"""
backend/scoring/confidence.py — user-facing MATCH CONFIDENCE (LOW / MEDIUM / HIGH).

This is a SEPARATE axis from the forensic linkage tier produced by scoring_engine.py.
That tier (HIGH/MEDIUM/LOW/REJECT) answers "are these accounts the SAME PERSON?" — it is
governed by the red-herring rule, drives the BSA-63 court report, and is NOT touched here.

Match confidence answers the question an investigator actually reads off each result card:

    "How confident are we that this account is a CORRECT MATCH for what I searched?"

Rules, in priority order:

  1. EXACT username / seed match  ->  HIGH, always.
     The account that literally IS the searched-for identifier is the strongest possible
     lead. (This is the rule the product owner asked for: "exact username match — high".)

  2. Everything else  ->  a blended 0-100 score built from three independent "votes",
     each an estimate (0-100) that this account is a correct match:
       - ALGO   : the deterministic correlation strength (shared phone / email / photo /
                  face / self-disclosed bio link / …). Hard evidence — stands on its own.
       - ADJUD  : the LLM adjudicator's same-person probability, but ONLY when it actually
                  confirmed the link (ai_confirmed). A confident adjudication is strong.
       - RELEV  : the LLM reranker's relevance score. This is a LEAD signal only, so its
                  solo influence is CAPPED below HIGH — "the model thinks it's relevant"
                  must never, by itself, claim a HIGH match (mirrors reranker.py's guard).

     The strongest single vote sets the score. When two independent votes both moderately
     agree, a small corroboration bonus is added (independent agreement is meaningful).

Nothing here changes which accounts are LINKED or the forensic `tier` — it only grades and
orders results for the UI. Deterministic and fail-safe: given the same cluster it always
returns the same tier, and it never raises (a malformed cluster degrades to LOW).
"""
from __future__ import annotations

# Tier thresholds (3 tiers only — no REJECT on this axis).
HIGH_MIN = 70
MEDIUM_MIN = 40

# A pure-LLM-relevance vote can never, alone, reach HIGH — it is a lead to verify, not a
# confirmed match. Capped one point below HIGH_MIN so relevance-only tops out at MEDIUM.
RELEVANCE_SOLO_CAP = HIGH_MIN - 1        # 69

# Two independent votes each at least this strong => small additive corroboration bonus.
CORROBORATION_FLOOR = MEDIUM_MIN         # 40
CORROBORATION_BONUS = 8


def tier_for(score: float) -> str:
    """Map a 0-100 match score to a 3-level tier."""
    if score >= HIGH_MIN:
        return "HIGH"
    if score >= MEDIUM_MIN:
        return "MEDIUM"
    return "LOW"


def seed_value_set(seeds: list[dict] | None) -> set[str]:
    """Normalized set of username/name seed values (raw + alphanumeric-only), matching the
    same normalization scoring_engine.py uses for its own seed detection."""
    out: set[str] = set()
    for s in (seeds or []):
        if s.get("type") in ("username", "name") and s.get("value"):
            v = str(s["value"]).strip().lower()
            if v:
                out.add(v)
                vc = "".join(ch for ch in v if ch.isalnum())
                if vc:
                    out.add(vc)
    return out


def _is_exact_match(cluster, profiles: list, seed_vals: set[str]) -> bool:
    """True if this cluster contains the account the investigator literally searched for.

    Recognised three ways (any one is sufficient):
      - a member profile carries metadata['exact_seed_match'] (stamped by the orchestrator),
      - the cluster was flagged relevance_score >= 100 (seed match, set by scoring/rerank),
      - a member's handle/username/name equals a normalized seed value.
    """
    if getattr(cluster, "relevance_score", 0) and cluster.relevance_score >= 100:
        return True
    for idx in getattr(cluster, "member_indices", []) or []:
        if not (0 <= idx < len(profiles)):
            continue
        p = profiles[idx]
        meta = getattr(p, "metadata", None) or {}
        if meta.get("exact_seed_match"):
            return True
        if not seed_vals:
            continue
        cand = {
            str(getattr(p, "value", "") or "").strip().lower(),
            str(meta.get("username") or "").strip().lower(),
            str(meta.get("name") or meta.get("fullname") or "").strip().lower(),
        }
        cand |= {"".join(ch for ch in c if ch.isalnum()) for c in cand}
        cand.discard("")
        if cand & seed_vals:
            return True
    return False


def compute(cluster, profiles: list, seed_vals: set[str]) -> dict:
    """Return {"score": int, "tier": str, "reason": str} for one cluster. Never raises."""
    try:
        if _is_exact_match(cluster, profiles, seed_vals):
            return {"score": 100, "tier": "HIGH",
                    "reason": "Exact match for your search input."}

        algo = float(getattr(cluster, "confidence_score", 0) or 0)
        relev = float(getattr(cluster, "relevance_score", 0) or 0)
        adjud = (float(getattr(cluster, "ai_confidence", 0) or 0)
                 if getattr(cluster, "ai_confirmed", False) else 0.0)

        votes = [
            ("hard-evidence correlation", algo),
            ("AI same-person adjudication", adjud),
            ("AI relevance analysis", min(relev, float(RELEVANCE_SOLO_CAP))),
        ]
        label, score = max(votes, key=lambda kv: kv[1])

        strong = [v for _, v in votes if v >= CORROBORATION_FLOOR]
        corroborated = len(strong) >= 2
        if corroborated:
            score = min(100.0, score + CORROBORATION_BONUS)

        tier = tier_for(score)
        if score <= 0:
            reason = "No corroborating evidence and no relevance signal — treat as a weak lead."
        else:
            reason = f"Graded on {label} ({int(round(score))}/100)"
            reason += " with independent corroboration." if corroborated else "."
        return {"score": int(round(score)), "tier": tier, "reason": reason}
    except Exception:  # noqa: BLE001 — grading must never break the pipeline
        return {"score": 0, "tier": "LOW", "reason": ""}


def stamp_clusters(clusters: list, profiles: list, seeds: list[dict] | None) -> list:
    """Compute and attach match_score / match_tier / match_reason on every cluster.

    Mutates and returns the same list. Call this as the FINAL scoring step, after the LLM
    reranker/adjudicator have run, so relevance_score / ai_confidence are populated.
    """
    seed_vals = seed_value_set(seeds)
    for c in clusters:
        res = compute(c, profiles, seed_vals)
        c.match_score = res["score"]
        c.match_tier = res["tier"]
        c.match_reason = res["reason"]
    return clusters
