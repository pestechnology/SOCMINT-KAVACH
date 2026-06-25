"""Correlation engine — groups profiles into LinkedIdentity clusters using union-find."""

import logging
import uuid
from collections import defaultdict

from backend.correlation.signals import compute_all_signals, fired_signals
from backend.schemas import LinkedIdentity, RawProfile, SignalResult

logger = logging.getLogger(__name__)


class _UnionFind:
    """Weighted union-find with path compression."""

    def __init__(self, n: int) -> None:
        self.parent: list[int] = list(range(n))
        self.rank: list[int] = [0] * n

    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        """Union by rank."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


class CorrelationEngine:
    """Groups profiles into linked identities based on signal overlap."""

    def correlate(self, profiles: list[RawProfile]) -> list[LinkedIdentity]:
        """Cluster profiles using pairwise signal analysis and union-find.

        Linking rule: two profiles are joined when >= 2 signals fire between them.
        A single signal — even a high-weight one — is NOT sufficient for linking,
        per the red-herring principle (Section 7.3).
        """
        n = len(profiles)
        if n == 0:
            return []

        uf = _UnionFind(n)

        # Store all pairwise signals for later use by the scoring engine
        pair_signals: dict[tuple[int, int], list[SignalResult]] = {}

        for i in range(n):
            for j in range(i + 1, n):
                all_sigs = compute_all_signals(profiles[i], profiles[j])
                fired = fired_signals(all_sigs)
                pair_signals[(i, j)] = fired

                # Union when 2+ signals fire
                if len(fired) >= 2:
                    uf.union(i, j)
                    logger.debug(
                        "[correlation] linked %s(%s) ↔ %s(%s) — %d signals",
                        profiles[i].platform,
                        profiles[i].value,
                        profiles[j].platform,
                        profiles[j].value,
                        len(fired),
                    )

        # Group by connected component
        components: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            components[uf.find(i)].append(i)

        # Build LinkedIdentity objects
        clusters: list[LinkedIdentity] = []
        for indices in components.values():
            cluster_profiles = [profiles[i] for i in indices]

            # Gather all fired signals for pairs within this cluster
            cluster_signals: list[SignalResult] = []
            for i_idx, i in enumerate(indices):
                for j in indices[i_idx + 1:]:
                    key = (min(i, j), max(i, j))
                    cluster_signals.extend(pair_signals.get(key, []))

            cluster = LinkedIdentity(
                cluster_id=f"CLU-{uuid.uuid4().hex[:8]}",
                profiles=cluster_profiles,
                signals=cluster_signals,
            )
            clusters.append(cluster)

        # Attach near-miss info to singletons for red-herring detection
        for cluster in clusters:
            if len(cluster.profiles) == 1:
                profile_idx = profiles.index(cluster.profiles[0])
                near_miss: list[SignalResult] = []
                for (i, j), sigs in pair_signals.items():
                    if (i == profile_idx or j == profile_idx) and sigs:
                        near_miss.extend(sigs)
                if near_miss:
                    # Store near-miss signals — scoring engine will detect red herring
                    cluster.signals = near_miss

        logger.info(
            "[correlation] %d profiles → %d clusters",
            n,
            len(clusters),
        )
        return clusters
