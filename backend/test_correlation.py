"""Standalone correlation + scoring test — run with: python -m backend.test_correlation"""

import logging
import sys

from backend.correlation.engine import CorrelationEngine
from backend.schemas import LinkedIdentity, RawProfile, compute_hash
from backend.scoring.engine import ScoringEngine

logging.basicConfig(level="DEBUG", format="%(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def _make_profile(
    platform: str,
    handle: str,
    **meta: object,
) -> RawProfile:
    """Helper to build a test profile."""
    return RawProfile(
        type="social_account",
        value=handle,
        platform=platform,
        source_url=f"https://{platform}.com/{handle}",
        metadata=dict(meta),
        data_mode="mock",
        collected_at="2026-06-25T00:00:00Z",
        sha256=compute_hash(platform, handle),
    )


def _find_cluster(clusters: list[LinkedIdentity], profile: RawProfile) -> LinkedIdentity:
    """Find the cluster containing a specific profile."""
    for cluster in clusters:
        if profile in cluster.profiles:
            return cluster
    raise ValueError(f"Profile {profile.platform}/@{profile.value} not found in any cluster")


def main() -> None:
    """Build 5 mock profiles, run correlation + scoring, assert expectations."""
    print("\n" + "=" * 70)
    print("VERTEX Correlation & Scoring Test")
    print("=" * 70)

    # ── Build test profiles ──────────────────────────────────────────
    p1 = _make_profile(
        "instagram", "arjun99",
        phone="+918888888888",
        photo_phash="abc123",
        bio="crypto trader and investment guru in mumbai",
    )
    p2 = _make_profile(
        "twitter", "arjun99x",
        phone="+918888888888",
        photo_phash="abc124",   # 1-char hex diff → ~3 bits hamming
        bio="investment advisor crypto mumbai",
    )
    p3 = _make_profile(
        "linkedin", "arjun.sharma",
        phone="+918888888888",
        # NO photo_phash, NO bio overlap → only phone matches
    )
    p4 = _make_profile(
        "github", "arjun99",
        bio="investment advisor",
        photo_phash="def456",
    )
    p5 = _make_profile(
        "reddit", "completelydifferent",
        bio="I collect stamps and enjoy birdwatching",
    )

    profiles = [p1, p2, p3, p4, p5]
    print(f"\nProfiles built: {len(profiles)}")
    for i, p in enumerate(profiles, 1):
        print(f"  P{i}: {p.platform}/@{p.value}")

    # ── Run correlation ──────────────────────────────────────────────
    print("\n--- Correlation ---")
    clusters = CorrelationEngine().correlate(profiles)
    print(f"Clusters formed: {len(clusters)}")

    # ── Run scoring ──────────────────────────────────────────────────
    print("\n--- Scoring ---")
    engine = ScoringEngine()
    for cluster in clusters:
        engine.score(cluster)
    engine.detect_red_herrings(clusters)

    # ── Print results ────────────────────────────────────────────────
    print("\n--- Results ---")
    for cluster in clusters:
        members = ", ".join(f"{p.platform}/@{p.value}" for p in cluster.profiles)
        print(f"\n  Cluster {cluster.cluster_id}:")
        print(f"    Members:    {members}")
        print(f"    Score:      {cluster.confidence_score:.1f}")
        print(f"    Tier:       {cluster.tier}")
        print(f"    Red herring: {cluster.is_red_herring}")
        if cluster.is_red_herring:
            print(f"    Reason:     {cluster.red_herring_reason}")
        if cluster.why_explanation:
            print(f"    Why:        {'; '.join(cluster.why_explanation)}")
        fired = [s.signal_name for s in cluster.signals if s.matched]
        print(f"    Signals:    {fired}")

    # ── Assertions ───────────────────────────────────────────────────
    print("\n--- Assertions ---")
    errors: list[str] = []

    # P1 + P2 should be in the same cluster with HIGH tier
    c12 = _find_cluster(clusters, p1)
    if p2 not in c12.profiles:
        errors.append("FAIL: P1 and P2 should be in the same cluster")
    else:
        print("  ✓ P1 + P2 are in the same cluster")

    if c12.tier != "HIGH":
        errors.append(f"FAIL: P1+P2 cluster tier should be HIGH, got {c12.tier} (score={c12.confidence_score})")
    else:
        print(f"  ✓ P1+P2 cluster tier is HIGH (score={c12.confidence_score:.1f})")

    # P3 should be alone, LOW tier, red herring
    c3 = _find_cluster(clusters, p3)
    if len(c3.profiles) != 1:
        errors.append(f"FAIL: P3 should be a singleton, got {len(c3.profiles)} profiles")
    else:
        print("  ✓ P3 is a singleton cluster")

    if c3.tier != "LOW":
        errors.append(f"FAIL: P3 tier should be LOW, got {c3.tier}")
    else:
        print(f"  ✓ P3 tier is LOW (score={c3.confidence_score:.1f})")

    if not c3.is_red_herring:
        errors.append("FAIL: P3 should be flagged as red herring")
    else:
        print(f"  ✓ P3 is flagged as red herring: {c3.red_herring_reason}")

    # P5 should be singleton, REJECT
    c5 = _find_cluster(clusters, p5)
    if len(c5.profiles) != 1:
        errors.append(f"FAIL: P5 should be a singleton, got {len(c5.profiles)} profiles")
    else:
        print("  ✓ P5 is a singleton cluster")

    if c5.tier != "REJECT":
        errors.append(f"FAIL: P5 tier should be REJECT, got {c5.tier}")
    else:
        print("  ✓ P5 tier is REJECT")

    # ── Final verdict ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        print(f"\n{len(errors)} ASSERTION(S) FAILED")
        sys.exit(1)
    else:
        print("  ALL ASSERTIONS PASSED ✅")
        print("=" * 70)


if __name__ == "__main__":
    main()
