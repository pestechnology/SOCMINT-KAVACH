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
    "llm_holistic_match": "semantically match based on holistic LLM evaluation",
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


def score(profiles: list[RawProfile], pairs: list[CandidatePair]) -> list[Cluster]:
    n = len(profiles)
    uf = _UnionFind(n)

    # Link only on MEDIUM+ pairs (>=2 signals, >=50 pts) OR a holistic LLM match.
    for p in pairs:
        if (p.num_signals >= LINK_MIN_SIGNALS or "llm_holistic_match" in p.signals) and p.raw_points >= LINK_MIN_POINTS:
            uf.union(p.i, p.j)

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
        # Union of signals among pairs fully inside this group.
        agg: dict = {}
        for p in pairs:
            if p.i in member_set and p.j in member_set:
                for sig, pts in p.signals.items():
                    agg[sig] = max(agg.get(sig, 0), pts)

        if len(members) > 1:
            confidence = min(100.0, float(sum(agg.values())))
            single_signal = len(agg) == 1 and "llm_holistic_match" not in agg
            tier = _tier(confidence)
            if single_signal:
                tier = _cap_tier(tier, "LOW")
            clusters.append(Cluster(
                cluster_id=uuid.uuid4().hex,
                member_indices=sorted(members),
                confidence_score=round(confidence, 1),
                tier=tier,
                signals=agg,
                explanation=_explain(agg, tier, single_signal),
            ))
        else:
            # singleton — carry its best attempted pair so the UI can say why it's NOT linked
            idx = members[0]
            bp = best_single.get(idx)
            sigs = dict(bp.signals) if bp else {}
            confidence = min(100.0, float(sum(sigs.values())))
            single_signal = len(sigs) == 1
            tier = _tier(confidence) if sigs else "REJECT"
            if single_signal:
                tier = _cap_tier(tier, "LOW")
            clusters.append(Cluster(
                cluster_id=uuid.uuid4().hex,
                member_indices=[idx],
                confidence_score=round(confidence, 1),
                tier=tier,
                signals=sigs,
                explanation=_explain(sigs, tier, single_signal) if sigs
                            else "Standalone account — no signals link it to any other account.",
            ))

    # Strongest clusters first.
    clusters.sort(key=lambda c: (len(c.member_indices) > 1, c.confidence_score), reverse=True)
    return clusters
