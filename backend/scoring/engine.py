"""Scoring engine — assigns confidence scores and tiers to linked identities.

Deterministic math only. No LLM. Same input always produces same score.
"""

import logging

from backend.correlation.signals import (
    SIGNAL_TEMPLATES,
    compute_all_signals,
    fired_signals,
)
from backend.schemas import LinkedIdentity, SignalResult

logger = logging.getLogger(__name__)

# ── Tier thresholds (from architecture doc Section 7.2) ──────────────
_TIER_HIGH = 75
_TIER_MEDIUM = 50
_TIER_LOW = 25


def _tier_from_score(score: float) -> str:
    """Map normalized score (0-100) to tier label."""
    if score > _TIER_HIGH:
        return "HIGH"
    if score >= _TIER_MEDIUM:
        return "MEDIUM"
    if score >= _TIER_LOW:
        return "LOW"
    return "REJECT"


def _build_explanation(signals: list[SignalResult]) -> list[str]:
    """Turn fired signals into plain-English sentences."""
    seen: set[str] = set()
    sentences: list[str] = []
    for sig in signals:
        if sig.matched and sig.signal_name not in seen:
            if sig.signal_name == "fullname_match" and sig.weight == 14:
                sentences.append(sig.detail)
            else:
                template = SIGNAL_TEMPLATES.get(sig.signal_name, sig.detail)
                if template:
                    sentences.append(template)
            seen.add(sig.signal_name)
    return sentences


class ScoringEngine:
    """Assigns confidence score, tier, and explanation to each cluster."""

    def score(self, cluster: LinkedIdentity) -> LinkedIdentity:
        """Score a single cluster based on internal pairwise signals. Mutates and returns."""
        profiles = cluster.profiles
        n = len(profiles)

        if n <= 1:
            # Singletons — handled by detect_red_herrings later
            cluster.confidence_score = 0.0
            cluster.tier = "REJECT"
            cluster.why_explanation = []
            return cluster

        # Compute signals for all internal pairs and find max pairwise score
        all_fired: list[SignalResult] = []
        max_pair_score: float = 0.0

        for i in range(n):
            for j in range(i + 1, n):
                pair_sigs = compute_all_signals(profiles[i], profiles[j])
                pair_fired = fired_signals(pair_sigs)
                all_fired.extend(pair_fired)

                pair_score = sum(s.weight for s in pair_fired)
                max_pair_score = max(max_pair_score, pair_score)

        # Score = max pairwise sum, capped at 100
        cluster.confidence_score = min(max_pair_score, 100.0)
        cluster.tier = _tier_from_score(cluster.confidence_score)
        cluster.signals = all_fired
        cluster.why_explanation = _build_explanation(all_fired)

        """Red-herring rejection rule for 2-profile clusters.

        Why this rule exists:
            Prevents false positives in automated correlation. A single matching attribute
            frequently collides between unrelated strangers across 500+ OSINT platforms.
        What it does:
            When a cluster contains exactly 2 profiles and only 1 unique signal type fired
            between them, the cluster is demoted to LOW tier and marked is_red_herring=True.
        What it doesn't do:
            It is NOT a hard rejection. Investigators still see the candidate card in the UI,
            badged as an uncorroborated lead requiring manual human verification.
        """
        if n == 2:
            unique_signal_names = {s.signal_name for s in all_fired}
            if len(unique_signal_names) == 1:
                cluster.tier = "LOW"
                cluster.is_red_herring = True
                cluster.red_herring_reason = (
                    "Only a single signal matched — insufficient to link. "
                    f"Signal: {next(iter(unique_signal_names))}"
                )

        logger.info(
            "[scoring] cluster %s: %d profiles, score=%.1f, tier=%s%s",
            cluster.cluster_id,
            n,
            cluster.confidence_score,
            cluster.tier,
            " (RED HERRING)" if cluster.is_red_herring else "",
        )
        return cluster

    def detect_red_herrings(
        self,
        clusters: list[LinkedIdentity],
    ) -> list[LinkedIdentity]:
        """Flag singleton clusters that had near-miss signals as red herrings.

        A singleton with cross-cluster signal matches (stored by the correlation
        engine in cluster.signals) is flagged as a red herring with tier=LOW.
        """
        for cluster in clusters:
            if len(cluster.profiles) != 1:
                continue

            # Check if correlation engine attached near-miss signals
            if not cluster.signals:
                # True singleton — no signals at all
                cluster.confidence_score = 0.0
                cluster.tier = "REJECT"
                continue

            # Has near-miss signals — this is a red herring
            near_miss_score = max(s.weight for s in cluster.signals)
            cluster.confidence_score = float(near_miss_score)
            cluster.tier = "LOW"
            cluster.is_red_herring = True

            signal_names = {s.signal_name for s in cluster.signals}
            cluster.red_herring_reason = (
                f"Only {len(signal_names)} signal type(s) matched against other "
                f"profiles — insufficient to link. "
                f"Signals: {', '.join(signal_names)}"
            )
            cluster.why_explanation = _build_explanation(cluster.signals)

            logger.info(
                "[scoring] red herring: %s on %s (near-miss score=%.0f)",
                cluster.profiles[0].value,
                cluster.profiles[0].platform,
                near_miss_score,
            )

        return clusters
