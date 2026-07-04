"""Summary report: mojibake purge, placeholder gate, confidence clamp, graph gating."""
import json

from backend.report import summary_report as sr


def test_sanitize_drops_mojibake_keeps_real():
    out = sr.sanitize_tokens(["#x2022", "#x25e5", "#x1f171", "&#x2022;", "", "photography", "chess"])
    assert "photography" in out and "chess" in out
    for bad in ("#x2022", "#x25e5", "#x1f171"):
        assert bad not in out


def test_placeholder_gate():
    assert sr._is_placeholder("admin")
    assert sr._is_placeholder("Untitled investigation")
    assert sr._is_placeholder("10")            # junk numeric title
    assert sr._is_placeholder("")
    assert sr._is_placeholder(None)
    assert not sr._is_placeholder("Phishing case #24")


def test_confidence_clamp_below_100_without_biometric():
    # email + handle (no biometric) → clamp to 95
    assert sr._display_confidence(
        {"confidence_score": 100.0, "signals_json": '{"exact_email_match":60,"username_exact_match":45}'}) == 95.0
    # face match present → allowed to stay 100
    assert sr._display_confidence(
        {"confidence_score": 100.0, "signals_json": '{"face_match":40}'}) == 100.0
    # below-100 values pass through untouched
    assert sr._display_confidence(
        {"confidence_score": 72.0, "signals_json": '{"exact_email_match":60}'}) == 72.0


def _cl(tier, ids):
    return {"tier": tier, "entity_ids_json": json.dumps(ids), "signals_json": "{}"}


def test_graph_gating():
    ent = {f"e{i}": {"platform": "instagram", "value": f"acct{i}"} for i in range(4)}
    # no confirmed (HIGH/MEDIUM) nodes → no figure
    assert sr.build_evidence_graph_drawing([_cl("LOW", ["e0", "e1"])], "seed", ent) is None
    # a confirmed cluster with ≥2 members → a Drawing
    d = sr.build_evidence_graph_drawing([_cl("HIGH", ["e0", "e1"])], "seed", ent)
    assert d is not None
    assert d.__class__.__name__ == "Drawing"


def test_graph_is_deterministic():
    # same input → byte-identical SVG (required for court)
    ent = {f"e{i}": {"platform": "x", "value": f"h{i}"} for i in range(3)}
    linked = [_cl("HIGH", ["e0", "e1", "e2"])]
    a = sr._render_graph_svg(linked, [], "seed", ent)
    b = sr._render_graph_svg(linked, [], "seed", ent)
    assert a == b
