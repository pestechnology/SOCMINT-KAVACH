"""
backend/pipeline/lead_reverification.py — promote unconfirmed leads to confirmed.

After initial scoring, some LOW/REJECT singleton entities from a username seed may
have a source_url that contains a bio or photo not captured during the fast scrape
pass.  This module:

  1. Identifies singleton (unlinked) entities that have a source_url but no bio/photo.
  2. Fetches those profile pages (same lightweight og:image + og:description fetcher
     used by the main enrichment pass) to populate bio and photo_url.
  3. Runs correlation between the newly-enriched singletons and the CONFIRMED cluster
     members only (not against every other unlinked entity — to keep pairwise cost O(N)
     rather than O(N²)).
  4. If a real corroborating signal fires (profile_photo_phash, bio_keyword_overlap,
     stylometry_cosine, exact_name_match, exact_email_match, exact_phone_match),
     the singleton is merged into the confirmed cluster via the same union-find /
     red-herring logic that the main scoring pass uses.  Single-signal-only matches
     are still capped at LOW — the red-herring rule is NOT weakened.
  5. Returns (updated_profiles, updated_clusters, promoted_indices) so the
     orchestrator can persist the changes and write a "lead_reverification" ledger
     entry per promoted entity.

Design constraints:
  • Never weakens the red-herring rule (LINK_MIN_SIGNALS=2 still required to merge).
  • Only checks singletons against already-confirmed clusters (HIGH/MEDIUM-tier
    multi-member clusters), not against other singletons.
  • Fail-safe: any fetch/parse error leaves the entity unchanged.
"""
from __future__ import annotations

import asyncio

from backend.correlation.correlation_engine import correlate, _pair_signals
from backend.ingestion.base_module import RawProfile
from backend.ingestion.profile_page_fetcher import enrich_profiles_from_page
from backend.scoring.scoring_engine import (
    LINK_MIN_POINTS, LINK_MIN_SIGNALS, Cluster, _tier, _cap_tier, _UnionFind,
)

# Signals that count as genuine corroboration (not just shared search context)
_STRONG_SIGNALS = {
    "profile_photo_phash", "bio_keyword_overlap", "stylometry_cosine",
    "exact_name_match", "exact_email_match", "exact_phone_match",
    "exact_upi_match", "exact_phone_match", "fuzzy_name_match",
    "posting_hours_overlap", "location_overlap",
}


async def reverify_leads(
    profiles: list[RawProfile],
    clusters: list[Cluster],
) -> tuple[list[RawProfile], list[Cluster], list[int]]:
    """Attempt to promote LOW/REJECT singletons into confirmed clusters.

    Returns:
        (profiles, updated_clusters, promoted_profile_indices)
        profiles is mutated in-place (metadata enriched); clusters list is rebuilt.
    """
    # Identify confirmed clusters (multi-member, HIGH or MEDIUM)
    confirmed_clusters = [
        c for c in clusters
        if len(c.member_indices) >= 2 and c.tier in ("HIGH", "MEDIUM")
    ]
    if not confirmed_clusters:
        return profiles, clusters, []

    # Collect the set of confirmed member indices (already-linked)
    confirmed_indices: set[int] = set()
    for c in confirmed_clusters:
        confirmed_indices.update(c.member_indices)

    # Singleton entities that are unlinked and have a source_url
    singleton_clusters = [c for c in clusters if len(c.member_indices) == 1]
    singleton_indices = [
        c.member_indices[0] for c in singleton_clusters
        if c.member_indices[0] not in confirmed_indices
    ]
    candidates = [
        i for i in singleton_indices
        if isinstance(getattr(profiles[i], "source_url", None), str)
        and profiles[i].source_url.startswith("http")
    ]

    if not candidates:
        return profiles, clusters, []

    # Fetch profile pages for candidate singletons to get bio + photo
    candidate_profiles = [profiles[i] for i in candidates]
    await enrich_profiles_from_page(candidate_profiles)

    # Also enrich photos (pHash) for any newly-acquired photo_url
    try:
        from backend.ingestion.photo_enrich import enrich_photos
        await enrich_photos(candidate_profiles)
    except Exception:
        pass

    # Check each candidate against every confirmed cluster member
    promoted: list[int] = []
    promoted_into: dict[int, int] = {}  # singleton_idx -> cluster index in clusters

    for singleton_idx in candidates:
        p_singleton = profiles[singleton_idx]
        best_signals: dict = {}
        best_cluster_idx: int = -1

        for cl_idx, conf_cl in enumerate(confirmed_clusters):
            # Aggregate signals across all confirmed members
            agg: dict = {}
            for member_idx in conf_cl.member_indices:
                fired = _pair_signals(p_singleton, profiles[member_idx])
                for sig, pts in fired.items():
                    agg[sig] = max(agg.get(sig, 0), pts)

            # Only count genuinely corroborating signals (not seed-stamped trivial matches)
            strong = {k: v for k, v in agg.items() if k in _STRONG_SIGNALS}
            total = sum(strong.values())

            if (len(strong) >= LINK_MIN_SIGNALS
                    and total >= LINK_MIN_POINTS
                    and total > sum(best_signals.values())):
                best_signals = strong
                best_cluster_idx = cl_idx

        if best_cluster_idx >= 0:
            promoted.append(singleton_idx)
            promoted_into[singleton_idx] = best_cluster_idx

    if not promoted:
        return profiles, clusters, []

    # Rebuild clusters: merge promoted singletons into their target confirmed clusters
    # Build a lookup from singleton_idx -> old singleton Cluster object
    singleton_cluster_map: dict[int, Cluster] = {
        c.member_indices[0]: c for c in singleton_clusters
    }

    new_clusters: list[Cluster] = []
    promoted_set = set(promoted)

    for cl in clusters:
        if len(cl.member_indices) == 1 and cl.member_indices[0] in promoted_set:
            continue  # will be merged below
        new_clusters.append(cl)

    # Merge into confirmed clusters
    for cl in confirmed_clusters:
        merged_indices = list(cl.member_indices)
        merged_signals = dict(cl.signals)
        for singleton_idx in promoted:
            if promoted_into.get(singleton_idx) == confirmed_clusters.index(cl):
                merged_indices.append(singleton_idx)
                # Re-compute signals for the full merged group
                for member_idx in cl.member_indices:
                    new_sigs = _pair_signals(profiles[singleton_idx], profiles[member_idx])
                    strong = {k: v for k, v in new_sigs.items() if k in _STRONG_SIGNALS}
                    for sig, pts in strong.items():
                        merged_signals[sig] = max(merged_signals.get(sig, 0), pts)

        if len(merged_indices) == len(cl.member_indices):
            # Nothing was merged into this cluster
            continue

        # Rebuild this cluster with merged members
        confidence = min(100.0, float(sum(merged_signals.values())))
        single = len(merged_signals) == 1
        tier = _tier(confidence)
        if single:
            tier = _cap_tier(tier, "LOW")

        # Replace the confirmed cluster in new_clusters with the merged version
        for i, nc in enumerate(new_clusters):
            if nc.cluster_id == cl.cluster_id:
                new_clusters[i] = Cluster(
                    cluster_id=cl.cluster_id,
                    member_indices=sorted(merged_indices),
                    confidence_score=round(confidence, 1),
                    tier=tier,
                    signals=merged_signals,
                    explanation=cl.explanation + f" [+{len(merged_indices) - len(cl.member_indices)} lead(s) promoted after reverification]",
                )
                break

    new_clusters.sort(key=lambda c: ("Primary target persona" in (c.explanation or ""), len(c.member_indices) > 1, c.confidence_score), reverse=True)
    return profiles, new_clusters, promoted
