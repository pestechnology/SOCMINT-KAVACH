"""
backend/report/charts.py — lightweight SVG charts for the PDF reports.

Each builder returns a reportlab Drawing (via svglib, the SAME path the evidence graph
already uses in summary_report.py) or None when there isn't enough data to be worth a figure.
Kept to primitive SVG (rect / line / text) so svg2rlg parses it reliably. Palette matches the
report house style. Never raises — a chart that can't render just returns None and the section
is skipped.
"""
from __future__ import annotations

from io import BytesIO

from svglib.svglib import svg2rlg

# Professional data-viz palette — desaturated Tableau-style tones. A single muted steel-blue
# carries the "data" charts (platform / activity / timeline); the confidence tiers use soft
# semantic colours (teal-green / ochre / cool-grey) rather than saturated traffic-light hues.
NAVY = "#2b3a4d"     # slate ink — numbers / emphasis
INK = "#3f4b5b"      # primary labels
MUTED = "#7c858f"    # axis ticks / secondary labels
LIGHT = "#d6dce3"    # baseline rules
GRID = "#edf0f4"     # empty / zero bars
HIGH = "#4c9a78"     # muted teal-green
MED = "#dca63f"      # muted ochre
LOW = "#9aa4ad"      # cool grey (leads)
ACCENT = "#4e79a7"   # muted steel blue — primary data hue


def _draw(svg: str):
    try:
        return svg2rlg(BytesIO(svg.encode("utf-8")))
    except Exception:  # noqa: BLE001
        return None


def _svg(w: int, h: int, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{body}</svg>')


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _text(x, y, s, size=9, fill=INK, anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Helvetica" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{_esc(s)}</text>')


def _rect(x, y, w, h, fill, rx=1.5):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{max(0,h):.1f}" rx="{rx}" fill="{fill}"/>'


# --------------------------------------------------------------------------------------
def verdict_bars(high: int, med: int, low: int):
    """Vertical bars: accounts by confidence tier (HIGH / MEDIUM / LEAD)."""
    vals = [("HIGH", high, HIGH), ("MEDIUM", med, MED), ("LEADS", low, LOW)]
    if sum(v for _, v, _ in vals) <= 0:
        return None
    W, H = 460, 172
    pad_b, pad_t = 34, 16
    chart_h = H - pad_b - pad_t
    maxv = max(1, high, med, low)
    bw, gap = 96, 60
    total = len(vals) * bw + (len(vals) - 1) * gap
    x0 = (W - total) / 2
    body = [f'<line x1="{x0-14:.1f}" y1="{H-pad_b:.1f}" x2="{W-x0+14:.1f}" y2="{H-pad_b:.1f}" stroke="{LIGHT}" stroke-width="1"/>']
    for i, (lab, val, col) in enumerate(vals):
        x = x0 + i * (bw + gap)
        bh = (val / maxv) * chart_h
        y = H - pad_b - bh
        body.append(_rect(x, y, bw, bh, col, rx=3))
        body.append(_text(x + bw / 2, y - 6, str(val), size=15, fill=NAVY, anchor="middle", weight="bold"))
        body.append(_text(x + bw / 2, H - pad_b + 16, lab, size=9.5, fill=MUTED, anchor="middle"))
    return _draw(_svg(W, H, "".join(body)))


def platform_bars(items: list[tuple[str, int]], top: int = 8):
    """Horizontal bars: number of accounts discovered per platform."""
    items = [(p, c) for p, c in items if p and c][:top]
    if not items:
        return None
    W = 460
    rowh, gap = 20, 8
    pad_t = 6
    H = pad_t + len(items) * (rowh + gap)
    maxv = max(c for _, c in items)
    label_w, num_w = 120, 26
    bar_x = label_w + 6
    bar_max = W - bar_x - num_w - 6
    body = []
    for i, (plat, cnt) in enumerate(items):
        y = pad_t + i * (rowh + gap)
        body.append(_text(label_w, y + rowh * 0.72, plat[:18], size=9.5, fill=INK, anchor="end"))
        bw = (cnt / maxv) * bar_max
        body.append(_rect(bar_x, y, max(2, bw), rowh, ACCENT, rx=3))
        body.append(_text(bar_x + max(2, bw) + 5, y + rowh * 0.72, str(cnt), size=9.5, fill=NAVY, anchor="start", weight="bold"))
    return _draw(_svg(W, H, "".join(body)))


def activity_hours(hour_counts: dict[int, int]):
    """24 vertical bars: the subject's active hours (UTC) from posting-time metadata."""
    counts = [int(hour_counts.get(h, 0) or 0) for h in range(24)]
    if sum(counts) <= 0:
        return None
    W, H = 460, 132
    pad_b, pad_t, pad_l = 22, 10, 6
    chart_h = H - pad_b - pad_t
    maxv = max(counts)
    span = W - pad_l - 6
    bw = span / 24
    body = [f'<line x1="{pad_l:.1f}" y1="{H-pad_b:.1f}" x2="{W-6:.1f}" y2="{H-pad_b:.1f}" stroke="{LIGHT}" stroke-width="1"/>']
    for h in range(24):
        x = pad_l + h * bw
        bh = (counts[h] / maxv) * chart_h
        col = ACCENT if counts[h] else GRID
        body.append(_rect(x + 1, H - pad_b - bh, bw - 2, bh if counts[h] else 2, col, rx=1))
    for h in (0, 6, 12, 18, 23):
        body.append(_text(pad_l + h * bw + bw / 2, H - pad_b + 13, f"{h:02d}", size=8, fill=MUTED, anchor="middle"))
    return _draw(_svg(W, H, "".join(body)))


def timeline(events: list[tuple[str, str]]):
    """Horizontal milestone timeline: [(label, time_str), ...] left→right."""
    events = [(l, t) for l, t in events if l][:7]
    if len(events) < 2:
        return None
    W, H = 460, 118
    y = H / 2
    x0, x1 = 20, W - 20
    step = (x1 - x0) / (len(events) - 1)
    body = [f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{LIGHT}" stroke-width="2"/>']
    for i, (lab, tm) in enumerate(events):
        x = x0 + i * step
        above = (i % 2 == 0)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{ACCENT}"/>')
        ly = y - 12 if above else y + 22
        body.append(_text(x, ly, lab[:22], size=8.5, fill=NAVY, anchor="middle", weight="bold"))
        body.append(_text(x, ly - 11 if above else ly + 11, tm, size=7.5, fill=MUTED, anchor="middle"))
    return _draw(_svg(W, H, "".join(body)))
