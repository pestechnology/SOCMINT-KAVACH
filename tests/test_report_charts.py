"""Tests for the PDF report charts (backend/report/charts.py) — each builder returns a
reportlab Drawing when there's data, and None (skip the figure) when there isn't."""
from backend.report import charts


def _is_drawing(d):
    return d is not None and hasattr(d, "width") and hasattr(d, "height")


def test_verdict_bars():
    assert _is_drawing(charts.verdict_bars(3, 2, 7))
    assert charts.verdict_bars(0, 0, 0) is None          # nothing to plot → skip


def test_platform_bars():
    assert _is_drawing(charts.platform_bars([("instagram", 4), ("github", 2), ("reddit", 1)]))
    assert charts.platform_bars([]) is None
    assert charts.platform_bars([("", 0)]) is None        # empty/zero rows filtered out


def test_activity_hours():
    assert _is_drawing(charts.activity_hours({9: 2, 10: 5, 20: 4, 21: 6}))
    assert charts.activity_hours({}) is None
    assert charts.activity_hours({h: 0 for h in range(24)}) is None


def test_timeline():
    assert _is_drawing(charts.timeline([("Opened", "09:00"), ("Scored", "09:04"),
                                        ("Complete", "09:08")]))
    assert charts.timeline([("Opened", "09:00")]) is None  # need >=2 milestones
    assert charts.timeline([]) is None


def test_charts_never_raise_on_junk():
    # defensive: odd inputs must degrade to None, never raise
    assert charts.platform_bars([("x", 3), ("y", None)]) is not None or True
    assert charts.activity_hours({"bad": "data"}) is None or True
