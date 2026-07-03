"""
backend/scoring/scoring_engine.py — the brain's decision layer.

score(profiles, pairs) -> list[Cluster]

Confidence model (deterministic, no LLM):
  confidence = min(100, sum of the points of all DISTINCT signals fired within
  the cluster). Weights are realistic points; capping at 100 keeps the tier
  thresholds from Section 7.2 meaningful (summing all 12 raw weights would make
  HIGH unreachable — see note below).

Tiers (Section 7.2):    HIGH > 75 | MEDIUM 50-75 | LOW 25-50 | REJECT < 25

THE RED-HERRING RULE (Section 7.3): if only ONE signal fired, cap the tier at
LOW no matter how heavy that signal is. A lone phone/username match is not a link.

Clustering: profiles are linked into the same cluster when a pair between them
reaches MEDIUM (>=50 points AND >=2 signals). Unlinked profiles become singleton
clusters carrying their best attempted pair score (so the red herring shows up as
"LOW — not linked" rather than vanishing).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from backend.correlation.correlation_engine import CandidatePair
from backend.ingestion.base_module import RawProfile

LINK_MIN_POINTS = 50          # MEDIUM threshold
LINK_MIN_SIGNALS = 2          # never link on a single signal


@dataclass
class Cluster:
    cluster_id: str
    member_indices: list[int]
    confidence_score: float
    tier: str
    signals: dict = field(default_factory=dict)   # signal -> points (union across cluster)
    explanation: str = ""
    relevance_rank: int = 0        # assigned by reranker (1 = most relevant)
    relevance_score: int = 0       # LLM relevance score for singletons (0-100)
    relevance_reason: str = ""     # LLM explanation for relevance


def _tier(score: float) -> str:
    if score > 75:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    if score >= 25:
        return "LOW"
    return "REJECT"


_TIER_ORDER = {"REJECT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _cap_tier(tier: str, ceiling: str) -> str:
    return tier if _TIER_ORDER[tier] <= _TIER_ORDER[ceiling] else ceiling


_SIGNAL_PHRASES = {
    "exact_phone_match": "share the same registered phone number",
    "exact_email_match": "share the same email address",
    "exact_upi_match": "share the same UPI ID",
    "username_exact_match": "use an identical username",
    "username_substring_match": "use closely related usernames",
    "username_fuzzy_match": "use similar usernames",
    "exact_name_match": "share the exact same real name",
    "fuzzy_name_match": "have highly similar real names",
    "location_overlap": "are based in the same geographic location",
    "profile_photo_phash": "have visually identical profile photos",
    "posting_hours_overlap": "post during the same hours",
    "stylometry_cosine": "write in a very similar style",
    "breach_co_occurrence": "appear together in the same data breaches",
    "bio_keyword_overlap": "use the same distinctive phrases in their bios",
    "reciprocal_mention": "mention each other",
    "semantic_rerank_match": "were identified as the same person through semantic analysis of their profiles",
    "face_match": "show the same face in their profile photos",
    "bio_url_match": "link directly to each other in their bio",
    "employer_overlap": "list the same employer or school",
    "city_match": "mention the same city in their bios",
    "mutual_connections": "share several of the same followers",
}


def _explain(signals: dict, tier: str, single_signal: bool) -> str:
    phrases = [_SIGNAL_PHRASES.get(s, s) for s in signals]
    if not phrases:
        return "No corroborating signals were found between these accounts."
    if len(phrases) == 1:
        joined = phrases[0]
    else:
        joined = ", ".join(phrases[:-1]) + " and " + phrases[-1]
    lead = {
        "HIGH": "These accounts strongly indicate the same person: they ",
        "MEDIUM": "These accounts possibly belong to the same person: they ",
        "LOW": "These accounts ",
        "REJECT": "These accounts ",
    }[tier]
    msg = f"{lead}{joined}."
    if single_signal:
        msg += " Only a single signal matched - insufficient to link, so this is flagged but not joined."
    return msg


HARD_ANCHOR_SIGNALS = {
    "exact_email_match",
    "exact_phone_match",
    "exact_upi_match",
    "profile_photo_phash",
    "breach_co_occurrence",
    # face_match: biometric identity match (photo_enrich.py's SFace embedding,
    # cosine >= the model's own calibrated same-person threshold) — standalone strong
    # evidence, same tier as an exact image-hash match.
    "face_match",
    # bio_url_match: a profile's OWN bio links to the other discovered account's own
    # URL — self-disclosure, comparably strong to an exact identifier match.
    "bio_url_match",
}


_CONTEXT_SIGNALS = ("location_overlap", "bio_keyword_overlap",
                    "stylometry_cosine", "posting_hours_overlap",
                    # employer_overlap / city_match: NER-derived from free text (LLM
                    # path — see fact_enrich.py). More specific than generic keyword
                    # overlap but LLM extraction confidence is lower than a
                    # deterministic identifier, so these stay context-tier, never a
                    # hard anchor by themselves.
                    "employer_overlap", "city_match",
                    # mutual_connections: real social-graph evidence but probabilistic
                    # (see correlation_engine.py's _mutual_connections for the overlap-
                    # count weighting) — corroborating, not standalone-sufficient.
                    "mutual_connections")


def _has_hard_anchor(signals: dict) -> bool:
    if any(sig in signals for sig in HARD_ANCHOR_SIGNALS):
        return True
    # A name match can anchor a link only WITH corroborating context, and the strength
    # required scales with how reliable the name signal is:
    #   - exact_name_match  : distinctive enough to anchor on ONE context signal.
    #   - fuzzy_name_match  : fires at ratio>=80 and hits common names ("rahul sharma" vs
    #                         "rahul verma"), so it needs TWO independent context signals.
    # Without this split, two unrelated people who share a common first/last name and both
    # post in the evening (posting_hours_overlap is trivially shared) would be treated as
    # hard-anchored and could reach HIGH — a false-positive merge on soft signals alone.
    n_context = sum(1 for sig in _CONTEXT_SIGNALS if sig in signals)
    if "exact_name_match" in signals and n_context >= 1:
        return True
    if "fuzzy_name_match" in signals and n_context >= 2:
        return True
    return False


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def score(profiles: list[RawProfile], pairs: list[CandidatePair], seeds: list[dict] | None = None) -> list[Cluster]:
    n = len(profiles)
    uf = _UnionFind(n)

    # Link ONLY on MEDIUM+ pairs (>=2 signals, >=50 pts) — the red-herring rule is the
    # entire point of this engine, so nothing may bypass LINK_MIN_SIGNALS/LINK_MIN_POINTS.
    for p in pairs:
        if p.num_signals >= LINK_MIN_SIGNALS and p.raw_points >= LINK_MIN_POINTS:
            uf.union(p.i, p.j)

    # Identify which profiles literally match the investigator's search seed — used
    # ONLY for ranking (surface the account that IS the searched-for identifier first)
    # and an explanatory note, NEVER to merge accounts or inflate confidence/tier.
    # A shared username/name string alone is a red herring by design (see this file's
    # docstring); an earlier version of this function unioned seed-matching profiles
    # directly and forced their tier to HIGH/confidence to 100, which let two total
    # strangers who each merely contained a short fragment of the seed (e.g. seed
    # "ash2903" loosely matching unrelated handles "ash" / "290") get merged into a
    # fabricated 100%-confidence "primary target" cluster. Matching here must never
    # affect uf.union() or Cluster.confidence_score/tier — see relevance_score/
    # relevance_reason below for the (non-authoritative) lead-ranking fields, mirroring
    # the same fix already applied to the LLM reranker's relevance vs. confidence split.
    seed_usernames = set()
    if seeds:
        for s in seeds:
            if s.get("type") in ("username", "name") and s.get("value"):
                val = str(s.get("value")).strip().lower()
                seed_usernames.add(val)
                val_clean = "".join(ch for ch in val if ch.isalnum())
                if val_clean:
                    seed_usernames.add(val_clean)

    def _matches_seed_id(idx: int) -> bool:
        if not seed_usernames:
            return False
        p = profiles[idx]
        v = str(p.value or "").strip().lower()
        vc = "".join(ch for ch in v if ch.isalnum())
        mu = str((p.metadata or {}).get("username") or "").strip().lower()
        muc = "".join(ch for ch in mu if ch.isalnum())
        meta_name = str((p.metadata or {}).get("name") or (p.metadata or {}).get("fullname") or (p.metadata or {}).get("title") or "").strip().lower()
        meta_clean = "".join(ch for ch in meta_name if ch.isalnum())

        # Containment is only meaningful when BOTH the seed fragment and the candidate
        # field are >=4 chars — mirrors the same floor correlation_engine.py's
        # username_substring_match already enforces. Below that, containment is
        # coincidental noise (e.g. "ash" / "290" both sit inside "ash2903").
        def _loose(u: str, field: str) -> bool:
            return len(u) >= 4 and len(field) >= 4 and (u in field or field in u)

        for u in seed_usernames:
            if u in (v, vc, mu, muc, meta_name, meta_clean):
                return True
            if _loose(u, vc) or _loose(u, muc) or _loose(u, meta_clean):
                return True
            if _loose(u, v) or _loose(u, mu) or _loose(u, meta_name):
                return True
        return False

    seed_indices = [idx for idx in range(n) if _matches_seed_id(idx)]

    # Group member indices by union-find root.
    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(uf.find(idx), []).append(idx)

    # Best attempted pair score per single index (for honest singleton labelling).
    best_single: dict[int, CandidatePair] = {}
    for p in pairs:
        for idx in (p.i, p.j):
            cur = best_single.get(idx)
            if cur is None or p.raw_points > cur.raw_points:
                best_single[idx] = p

    clusters: list[Cluster] = []
    for members in groups.values():
        member_set = set(members)
        is_seed_cluster = any(idx in seed_indices for idx in members) if seed_indices else False

        # Union of signals among pairs fully inside this group.
        agg: dict = {}
        for p in pairs:
            if p.i in member_set and p.j in member_set:
                for sig, pts in p.signals.items():
                    agg[sig] = max(agg.get(sig, 0), pts)

        if len(members) > 1:
            confidence = min(100.0, float(sum(agg.values())))
            single_signal = len(agg) == 1
            tier = _tier(confidence)
            if single_signal:
                tier = _cap_tier(tier, "LOW")
            if not _has_hard_anchor(agg):
                confidence = min(confidence, 65.0)
                tier = _cap_tier(tier, "MEDIUM")
            explanation = _explain(agg, tier, single_signal)
            if is_seed_cluster:
                explanation += " Includes the account matching your search input."
            clusters.append(Cluster(
                cluster_id=uuid.uuid4().hex,
                member_indices=sorted(members),
                confidence_score=round(confidence, 1),
                tier=tier,
                signals=agg,
                explanation=explanation,
                relevance_score=100 if is_seed_cluster else 0,
                relevance_reason="Matches your search input directly." if is_seed_cluster else "",
            ))
        else:
            # singleton — carry its best attempted pair so the UI can say why it's NOT linked
            idx = members[0]
            bp = best_single.get(idx)
            sigs = dict(bp.signals) if bp else {}
            confidence = min(100.0, float(sum(sigs.values())))
            single_signal = len(sigs) == 1
            is_single_seed = idx in seed_indices
            tier = _tier(confidence) if sigs else "REJECT"
            if single_signal:
                tier = _cap_tier(tier, "LOW")
            if sigs and not _has_hard_anchor(sigs):
                confidence = min(confidence, 65.0)
                tier = _cap_tier(tier, "MEDIUM")
            # A literal seed match is a useful LEAD (it's what the investigator typed),
            # not evidence of a cross-platform link — surfaced via relevance_score/reason
            # only, same non-authoritative pattern as the LLM reranker uses (see
            # reranker.py). confidence_score/tier reflect corroborating signals ONLY.
            explanation = _explain(sigs, tier, single_signal) if sigs else "Standalone account — no signals link it to any other account."
            if is_single_seed:
                explanation += " This account's identifier matches your search input directly."
            clusters.append(Cluster(
                cluster_id=uuid.uuid4().hex,
                member_indices=[idx],
                confidence_score=round(confidence, 1),
                tier=tier,
                signals=sigs,
                explanation=explanation,
                relevance_score=100 if is_single_seed else 0,
                relevance_reason="Matches your search input directly." if is_single_seed else "",
            ))

    # Strongest clusters first; exact seed cluster always #1!
    def _sort_key(c: Cluster):
        is_seed = any(idx in seed_indices for idx in c.member_indices) if seed_indices else False
        return (is_seed, len(c.member_indices) > 1, c.confidence_score)

    clusters.sort(key=_sort_key, reverse=True)
    return clusters
