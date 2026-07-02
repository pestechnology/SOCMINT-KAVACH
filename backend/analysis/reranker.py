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

    # Step 4: Targeted similarity checks for high-relevance singletons
    PROMOTION_THRESHOLD = 65
    promoted: list[int] = []
    promoted_reasons: dict[int, str] = {}

    high_relevance = [r for r in rerank_results if r["relevance"] >= PROMOTION_THRESHOLD]
    # Cap targeted checks at 15 to allow LLM to check more candidates
    high_relevance = high_relevance[:15]

    if high_relevance and confirmed_clusters:
        # Find the strongest confirmed cluster
        best_cluster = max(confirmed_clusters, key=lambda c: c.confidence_score)
        # Pick the richest member from the best cluster for comparison
        best_member_idx = max(
            best_cluster.member_indices,
            key=lambda i: len(str(profiles[i].metadata or {}))
        )
        best_member = profiles[best_member_idx]

        for r in high_relevance:
            singleton_idx = r["index"]
            singleton = profiles[singleton_idx]

            context = (
                f"Investigating {seed_type}: {seed_value}. "
                f"Target persona keywords: {', '.join(target_persona.get('keywords', [])[:10])}. "
                f"Reranker assessed relevance={r['relevance']}: {r['reason']}"
            )

            result = llm.semantic_similarity_check(
                _profile_to_dict(singleton),
                _profile_to_dict(best_member),
                context=context,
            )

            if result["should_link"] and result["score"] >= 65:
                promoted.append(singleton_idx)
                promoted_reasons[singleton_idx] = result["reason"]
                print(f"[reranker] PROMOTED {singleton.platform}/{singleton.value} "
                      f"(score={result['score']}, reason={result['reason'][:80]})")
            else:
                print(f"[reranker] not promoted {singleton.platform}/{singleton.value} "
                      f"(score={result['score']})")

    # Step 5: Rebuild clusters with promotions
    new_clusters: list[Cluster] = []
    promoted_set = set(promoted)

    # Remove promoted singletons from cluster list
    for cl in clusters:
        if len(cl.member_indices) == 1 and cl.member_indices[0] in promoted_set:
            continue
        new_clusters.append(cl)

    # Merge promoted singletons into confirmed clusters
    if promoted and confirmed_clusters:
        best_cluster = max(confirmed_clusters, key=lambda c: c.confidence_score)

        for i, nc in enumerate(new_clusters):
            if nc.cluster_id == best_cluster.cluster_id:
                merged_members = list(nc.member_indices) + promoted
                merged_signals = dict(nc.signals)
                # Record the semantic signal for transparency in the explanation, but it is
                # NOT summed into the score below.
                merged_signals["semantic_rerank_match"] = 30

                # PRECISION GUARD: an LLM promotion ADDS MEMBERS for recall but must NOT
                # upgrade the cluster's tier/confidence. Those stay pinned to what the
                # deterministic hard signals already earned. Summing semantic_rerank_match
                # into the score (the old behaviour) let two LLM calls push a MEDIUM cluster
                # to HIGH with no hard anchor — making the LLM the sole justification for a
                # "confirmed" link, which is exactly the failure mode this tool must avoid.
                confidence = nc.confidence_score
                tier = nc.tier

                promoted_names = [
                    f"{profiles[p].platform}/{profiles[p].value}" for p in promoted
                ]
                new_clusters[i] = Cluster(
                    cluster_id=nc.cluster_id,
                    member_indices=sorted(merged_members),
                    confidence_score=round(confidence, 1),
                    tier=tier,
                    signals=merged_signals,
                    explanation=(
                        nc.explanation +
                        f" [{len(promoted)} profile(s) promoted via semantic reranking: "
                        f"{', '.join(promoted_names)}]"
                    ),
                )
                break

    # Step 6: Assign relevance_rank to all clusters
    # Sort: confirmed multi-member first (by confidence), then singletons by LLM relevance
    def _sort_key(c: Cluster) -> tuple:
        is_multi = len(c.member_indices) > 1
        if is_multi:
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
            if rel_info:
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
