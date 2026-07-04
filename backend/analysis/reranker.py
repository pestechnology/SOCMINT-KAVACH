"""
backend/analysis/reranker.py — Post-correlation semantic reranking.

After the deterministic correlation engine clusters profiles by hard signals
(shared phone, email, photo hash, username match), many valid profiles remain
as LOW/REJECT singletons because the only evidence is semantic (same domain of
interest, username variant, bio theme overlap) which the rule engine can't see.

The reranker:
  1. Builds a "target persona" from confirmed clusters — merging ALL keywords,
     bios, locations, active hours, and names from every confirmed member.
  2. Sends ALL singletons to the LLM in ONE batch call for relevance scoring.
  3. For high-relevance singletons (score ≥ 65), runs a targeted semantic
     similarity check against the strongest confirmed cluster member.
  4. Promotes singletons that pass the similarity check into the confirmed cluster.
  5. Assigns a relevance_rank to every cluster for UI ordering.

LLM budget: 1 batch rerank call + 0-5 targeted similarity checks = ≤6 calls total.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from backend.analysis.forensics import _WORD_RE, _STOP
from backend.ingestion.base_module import RawProfile
from backend.llm.llm_client import LLMClient
from backend.scoring.scoring_engine import Cluster


def _extract_keywords(text: str, max_n: int = 15) -> list[str]:
    """Extract top keywords from text, excluding stopwords."""
    if not text:
        return []
    from collections import Counter
    words = [w.lower() for w in _WORD_RE.findall(text)]
    return [w for w, _ in Counter(w for w in words if w not in _STOP).most_common(max_n)]


def _build_target_persona(profiles: list[RawProfile],
                          confirmed_indices: set[int]) -> dict:
    """Merge all information from confirmed cluster members into a single persona."""
    all_bios: list[str] = []
    all_keywords: list[str] = []
    all_names: list[str] = []
    all_locations: list[str] = []
    all_usernames: list[str] = []
    all_platforms: list[str] = []
    all_hours: list[int] = []

    for idx in confirmed_indices:
        p = profiles[idx]
        m = p.metadata or {}

        all_platforms.append(p.platform)
        if p.value:
            all_usernames.append(p.value)

        bio = str(m.get("bio") or "")
        snippet = str(m.get("snippet") or "")
        text_sample = str(m.get("text_sample") or "")
        combined_text = " ".join(filter(None, [bio, snippet, text_sample]))

        if combined_text.strip():
            all_bios.append(combined_text[:200])
            all_keywords.extend(_extract_keywords(combined_text))

        name = m.get("name") or m.get("fullname")
        if name and isinstance(name, str) and name.strip():
            all_names.append(name.strip())

        loc = m.get("location")
        if loc and isinstance(loc, str) and loc.strip():
            all_locations.append(loc.strip())

        hours = m.get("posting_hours")
        if isinstance(hours, list):
            all_hours.extend(hours)

    # Deduplicate keywords by frequency
    from collections import Counter
    kw_counts = Counter(all_keywords)
    top_keywords = [w for w, _ in kw_counts.most_common(20)]

    return {
        "usernames": list(set(all_usernames)),
        "platforms": list(set(all_platforms)),
        "names": list(set(all_names)),
        "locations": list(set(all_locations)),
        "keywords": top_keywords,
        "bio_samples": all_bios[:5],  # keep concise for LLM context
        "active_hours": sorted(set(all_hours)) if all_hours else [],
    }


def _build_candidate_info(profiles: list[RawProfile], idx: int) -> dict:
    """Build a concise info dict for a singleton candidate."""
    p = profiles[idx]
    m = p.metadata or {}

    bio = str(m.get("bio") or m.get("snippet") or "")
    keywords = _extract_keywords(bio) if bio else []

    return {
        "index": idx,
        "platform": p.platform,
        "value": p.value,
        "type": p.type,
        "bio": bio[:200] if bio else "",
        "name": m.get("name") or m.get("fullname") or "",
        "location": m.get("location") or "",
        "keywords": keywords,
        "source_url": p.source_url or "",
    }


def _profile_to_dict(p: RawProfile) -> dict:
    """Convert a RawProfile to a dict for LLM consumption."""
    m = p.metadata or {}
    return {
        "platform": p.platform,
        "username": p.value,
        "bio": str(m.get("bio") or "")[:300],
        "name": m.get("name") or m.get("fullname") or "",
        "location": m.get("location") or "",
        "keywords": _extract_keywords(str(m.get("bio") or "")),
        "source_url": p.source_url or "",
    }


# Minimum rarity-weighted anchor-keyword score for a candidate to be surfaced to the
# adjudicator. Tuned so a lone common-first-name match (~0.1-0.6) never qualifies but a
# rare full-handle/employer/city match (a few points of IDF x specificity) does.
_KW_SURFACE_MIN = 2.0


def _profile_text_for_kw(p: RawProfile) -> str:
    m = p.metadata or {}
    parts = [str(p.value or "")]
    for k in ("name", "fullname", "bio", "snippet", "title"):
        parts.append(str(m.get(k) or ""))
    return " ".join(parts)


def rerank_and_promote(
    seed_type: str,
    seed_value: str,
    profiles: list[RawProfile],
    clusters: list[Cluster],
) -> tuple[list[Cluster], list[int]]:
    """Rerank singletons against confirmed clusters and promote high-relevance ones.

    Args:
        seed_type: the original search type
        seed_value: the original search value
        profiles: all discovered profiles
        clusters: clusters from the scoring engine

    Returns:
        (updated_clusters, promoted_indices)
    """
    llm = LLMClient()

    # Identify confirmed clusters (multi-member, HIGH or MEDIUM)
    confirmed_clusters = [
        c for c in clusters
        if len(c.member_indices) >= 2 and c.tier in ("HIGH", "MEDIUM")
    ]

    # Collect confirmed member indices
    confirmed_indices: set[int] = set()
    for c in confirmed_clusters:
        confirmed_indices.update(c.member_indices)

    # Identify singletons
    singleton_clusters = [c for c in clusters if len(c.member_indices) == 1]
    singleton_indices = [
        c.member_indices[0] for c in singleton_clusters
        if c.member_indices[0] not in confirmed_indices
    ]

    if not singleton_indices:
        # Nothing to rerank — just assign relevance ranks
        for i, c in enumerate(clusters):
            c.relevance_rank = i + 1
        return clusters, []

    # Step 1: Build target persona from confirmed clusters
    if confirmed_indices:
        target_persona = _build_target_persona(profiles, confirmed_indices)
    else:
        # No confirmed clusters yet — build persona from the seed itself
        target_persona = {
            "usernames": [seed_value] if seed_type in ("username",) else [],
            "names": [seed_value] if seed_type == "name" else [],
            "platforms": [],
            "locations": [],
            "keywords": _extract_keywords(seed_value),
            "bio_samples": [],
            "active_hours": [],
            "seed_type": seed_type,
            "seed_value": seed_value,
        }

    # Step 2: Build candidate info for all singletons
    candidates = [_build_candidate_info(profiles, idx) for idx in singleton_indices]

    # Step 3: Batch LLM rerank (1 call)
    rerank_results = llm.rerank_profiles(seed_type, seed_value, target_persona, candidates)

    # Build index -> relevance map
    relevance_map: dict[int, dict] = {}
    for r in rerank_results:
        relevance_map[r["index"]] = r

    # Step 4: LLM ADJUDICATION of high-relevance singletons against the target.
    # Policy (user-chosen): a confident adjudication (confidence >= CONFIRM) can CONFIRM a
    # same-person link on its own — the resulting cluster is tagged ai_confirmed so the UI/
    # report present it distinctly from a hard-evidence match. A softer positive
    # (PROMOTE..CONFIRM) still adds the member for recall but does NOT elevate the tier.
    PROMOTION_THRESHOLD = 60     # relevance floor to even consider a candidate
    PROMOTE = 65                 # adjudicator P(same) to link as a recall lead
    CONFIRM = 80                 # adjudicator P(same) to CONFIRM (ai_confirmed) a link
    promoted: list[int] = []
    promoted_reasons: dict[int, str] = {}
    ai_confirmed_idx: dict[int, dict] = {}   # singleton idx -> {"confidence", "reason"}

    high_relevance = [r for r in rerank_results if r["relevance"] >= PROMOTION_THRESHOLD]
    # Bounded to keep the sequential Groq burst under the per-minute limit.
    high_relevance = high_relevance[:6]

    # ADDITIVE anchor-keyword booster: surface up to 2 EXTRA candidates that the LLM
    # relevance pass may have under-rated but which mention the anchor's DISTINCTIVE
    # keywords (rare full-handle / employer / city — never a common first name; see
    # anchor_keywords.py's rarity weighting). This ONLY routes more candidates to the
    # adjudicator (which still gates every link) — it never touches deterministic scores.
    # max()-style union: it can only ADD to `high_relevance`, never drop an LLM pick.
    kw_matched_by_idx: dict[int, list[str]] = {}
    try:
        from backend.analysis.anchor_keywords import build_anchor_keywords, score_candidate
        anchor_kws = build_anchor_keywords(profiles)
        if anchor_kws:
            already = {r["index"] for r in high_relevance}
            scored = []
            for idx in singleton_indices:
                if idx in already:
                    continue
                s, matched = score_candidate(_profile_text_for_kw(profiles[idx]), anchor_kws)
                if s >= _KW_SURFACE_MIN and matched:
                    scored.append((s, idx, matched))
            scored.sort(reverse=True)
            for s, idx, matched in scored[:2]:
                kw_matched_by_idx[idx] = matched
                high_relevance.append({"index": idx, "relevance": PROMOTION_THRESHOLD,
                                       "reason": f"distinctive keyword match: {', '.join(matched[:4])}"})
                print(f"[anchor-kw] surfaced {profiles[idx].platform}/{profiles[idx].value} "
                      f"(score={s}, matched={matched[:4]})")
    except Exception as e:  # noqa: BLE001 — booster must never break the pipeline
        print(f"[anchor-kw] skipped ({e})")

    # Anchor description handed to the adjudicator (from the confirmed persona / seed).
    anchor = {
        "names": target_persona.get("names", []),
        "usernames": target_persona.get("usernames", []) or ([seed_value] if seed_value else []),
        "locations": target_persona.get("locations", []),
        "employers": target_persona.get("employers", []),
        "interests": target_persona.get("keywords", []),
        "bios": target_persona.get("bio_samples", []),
        "platforms": target_persona.get("platforms", []),
    }

    if high_relevance:
        from backend.analysis.adjudicator import adjudicate
        for r in high_relevance:
            singleton_idx = r["index"]
            singleton = profiles[singleton_idx]
            shared = None
            if singleton_idx in kw_matched_by_idx:
                shared = ["shared distinctive keyword: " + k for k in kw_matched_by_idx[singleton_idx][:4]]
            verdict = adjudicate(anchor, _profile_to_dict(singleton), shared_signals=shared, llm=llm)
            conf = verdict["confidence"]
            if verdict["same_person"] and conf >= CONFIRM:
                promoted.append(singleton_idx)
                promoted_reasons[singleton_idx] = verdict["reason"]
                ai_confirmed_idx[singleton_idx] = {"confidence": conf, "reason": verdict["reason"]}
                print(f"[adjudicator] CONFIRMED {singleton.platform}/{singleton.value} "
                      f"(P(same)={conf}) — {verdict['reason'][:80]}")
            elif verdict["same_person"] and conf >= PROMOTE:
                promoted.append(singleton_idx)
                promoted_reasons[singleton_idx] = verdict["reason"]
                print(f"[adjudicator] promoted (lead) {singleton.platform}/{singleton.value} "
                      f"(P(same)={conf})")
            else:
                print(f"[adjudicator] not linked {singleton.platform}/{singleton.value} "
                      f"(P(same)={conf})")

    # Step 5: Rebuild clusters with promotions
    new_clusters: list[Cluster] = []
    promoted_set = set(promoted)

    # Remove promoted singletons from cluster list
    for cl in clusters:
        if len(cl.member_indices) == 1 and cl.member_indices[0] in promoted_set:
            continue
        new_clusters.append(cl)

    # Choose the cluster the promoted candidates attach to: the strongest confirmed
    # cluster if one exists, otherwise the exact-match anchor singleton (the common case —
    # the target's own account is often unlinked). If neither exists, the promoted
    # candidates themselves form the target cluster (they all matched the seed persona).
    def _base_cluster() -> Cluster | None:
        if confirmed_clusters:
            return max(confirmed_clusters, key=lambda c: c.confidence_score)
        exact = [c for c in new_clusters if len(c.member_indices) == 1
                 and profiles[c.member_indices[0]].metadata.get("exact_seed_match")]
        return exact[0] if exact else None

    if promoted:
        base = _base_cluster()
        any_ai = any(idx in ai_confirmed_idx for idx in promoted)
        best_ai = max((ai_confirmed_idx[i]["confidence"] for i in promoted if i in ai_confirmed_idx), default=0)
        ai_reason = "  ".join(ai_confirmed_idx[i]["reason"] for i in promoted if i in ai_confirmed_idx)[:600]

        if base is not None:
            # remove the base (if it was a promoted exact singleton, it's already filtered) and
            # any promoted singletons, then rebuild the merged cluster.
            new_clusters = [c for c in new_clusters if c.cluster_id != base.cluster_id]
            merged_members = sorted(set(base.member_indices) | set(promoted))
            merged_signals = dict(base.signals)
            merged_signals["semantic_rerank_match"] = 30

            if any_ai:
                # AI-CONFIRMED link (user policy: the adjudicator may confirm on its own).
                # Elevate to a HIGH match but TAG it ai_confirmed so the UI/report show it as
                # "AI-assessed", distinct from a forensically-anchored (hard-signal) match.
                merged_signals["llm_same_person"] = best_ai
                confidence = max(base.confidence_score, float(best_ai))
                tier = "HIGH"
            else:
                # Soft promotion: recall only, tier/confidence stay pinned to hard evidence.
                confidence = base.confidence_score
                tier = base.tier

            promoted_names = [f"{profiles[p].platform}/{profiles[p].value}" for p in promoted]
            note = (" [AI-assessed same person: " + ai_reason + "]") if any_ai else (
                f" [{len(promoted)} profile(s) promoted via semantic reranking: {', '.join(promoted_names)}]")
            new_clusters.append(Cluster(
                cluster_id=base.cluster_id,
                member_indices=merged_members,
                confidence_score=round(confidence, 1),
                tier=tier,
                signals=merged_signals,
                explanation=(base.explanation + note),
                ai_confirmed=any_ai,
                ai_confidence=best_ai if any_ai else 0,
                ai_reason=ai_reason if any_ai else "",
            ))
        elif any_ai and len(promoted) >= 2:
            # No anchor cluster/singleton, but the adjudicator confirmed several accounts as
            # the same target person — form a new AI-assessed cluster from them.
            new_clusters = [c for c in new_clusters
                            if not (len(c.member_indices) == 1 and c.member_indices[0] in promoted_set)]
            new_clusters.append(Cluster(
                cluster_id=uuid.uuid4().hex,
                member_indices=sorted(promoted),
                confidence_score=float(best_ai),
                tier="HIGH",
                signals={"llm_same_person": best_ai},
                explanation="[AI-assessed same person: " + ai_reason + "]",
                ai_confirmed=True,
                ai_confidence=best_ai,
                ai_reason=ai_reason,
            ))

    # Step 6: Assign relevance_rank to all clusters
    # Sort: literal exact query matches first (#1), then partial seed matches, then confirmed multi-member (by confidence), then singletons by LLM relevance
    def _sort_key(c: Cluster) -> tuple:
        seed_clean = seed_value.strip().lower() if seed_value else ""
        is_exact = any(
            profiles[idx].metadata.get("exact_seed_match") or
            (seed_clean and str(profiles[idx].value or "").strip().lower() == seed_clean) or
            (seed_clean and str((profiles[idx].metadata or {}).get("username") or "").strip().lower() == seed_clean)
            for idx in c.member_indices if idx < len(profiles)
        )
        is_seed_rel = getattr(c, "relevance_score", 0) >= 100
        is_multi = len(c.member_indices) > 1
        if is_exact:
            return (4, c.confidence_score, 100)
        elif is_seed_rel:
            return (3, c.confidence_score, 100)
        elif is_multi:
            return (2, c.confidence_score, 0)
        else:
            idx = c.member_indices[0]
            rel = relevance_map.get(idx, {}).get("relevance", 0)
            return (1 if rel >= 50 else 0, rel, 0)

    new_clusters.sort(key=_sort_key, reverse=True)

    for i, c in enumerate(new_clusters):
        c.relevance_rank = i + 1
        # Attach LLM relevance to singleton clusters for UI ORDERING only.
        # PRECISION GUARD: LLM relevance is a LEAD score, not a linkage confidence. An
        # unlinked account the LLM "thinks" matches is a lead to investigate, not a
        # confirmed link. The old code overwrote confidence_score/tier with the raw
        # relevance number, so relevance>75 turned a singleton with ZERO hard signals into
        # a HIGH/"confirmed" cluster on the LLM's word alone. We now keep relevance in its
        # own field (relevance_score, surfaced separately in the UI) and NEVER let it raise
        # the deterministic confidence_score or tier.
        if len(c.member_indices) == 1:
            idx = c.member_indices[0]
            rel_info = relevance_map.get(idx)
            if rel_info and not (getattr(c, "relevance_score", 0) >= 100):
                c.relevance_score = rel_info["relevance"]
                c.relevance_reason = rel_info["reason"]
                if rel_info["relevance"] >= 50:
                    lead = (f"LLM lead ({rel_info['relevance']}/100 — a lead to verify, "
                            f"not a confirmed link): {rel_info['reason']}")
                    if not c.explanation or c.explanation == "No strong correlations found. Isolated profile.":
                        c.explanation = lead
                    else:
                        c.explanation += f" | {lead}"

    return new_clusters, promoted
