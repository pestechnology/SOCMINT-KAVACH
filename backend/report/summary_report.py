"""
backend/report/summary_report.py — officer-facing intelligence briefing.

Produces BSA63_summary_{case_id}.pdf: verdict-first, scannable, with a tiered evidence graph,
confidence clamped for non-biometric links, mojibake purged, a DRAFT watermark when the case
lacks a real officer/title, and the SHA-256 audit trail moved to a final appendix.

This is SEPARATE from the full court exhibit (bsa63_generator.generate_report), which is left
completely untouched. We only IMPORT its shared helpers (styles, _esc, _table, _section,
_load_case, colours, the numbered canvas) — no shared code is modified.

Field names verified against _load_case()/schema:
  case:    title, seeds_json, user_id                    (officer = user.username;
                                                            jurisdiction is NOT stored)
  cluster: tier, confidence_score, entity_ids_json, explanation, signals_json
  entity:  platform, value (handle), metadata_json.name
Every dynamic string still passes through base._esc before entering a flowable.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import unicodedata
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from svglib.svglib import svg2rlg

from backend import config
from backend.report import bsa63_generator as base
from backend.report import charts
from backend.ledger.audit_ledger import get_artifacts, get_ledger, verify_chain

# Only a genuine biometric/verified-ID signal justifies a displayed 100%.
_HARD_ID_SIGNALS = {"face_match"}

# short, plain-English label per matched signal (for the "82% · email + handle" basis line)
_SIGNAL_SHORT = {
    "exact_email_match": "email", "exact_phone_match": "phone", "exact_upi_match": "UPI",
    "username_exact_match": "handle", "username_substring_match": "handle (partial)",
    "username_fuzzy_match": "handle (fuzzy)", "exact_name_match": "name",
    "fuzzy_name_match": "name (fuzzy)", "phonetic_name_match": "name (phonetic)",
    "profile_photo_phash": "photo", "face_match": "face", "bio_url_match": "bio link",
    "location_overlap": "location", "employer_overlap": "employer", "city_match": "city",
    "posting_hours_overlap": "activity hours", "stylometry_cosine": "writing style",
    "mutual_connections": "shared connections", "breach_co_occurrence": "breach co-occurrence",
    "bio_keyword_overlap": "bio keywords", "reciprocal_mention": "mutual mention",
    "llm_same_person": "AI-assessed",
}

# A court-shaped doc must never ship these as real values (credibility killer).
PLACEHOLDER_MARKERS = {"[not set]", "[not completed]", "admin", "untitled",
                       "untitled investigation", "n/a", "test", ""}


# --------------------------------------------------------------------------- #
#  Part 3 correctness fixes
# --------------------------------------------------------------------------- #
_ARTIFACT_RE = re.compile(r"^#?x[0-9a-f]{2,6}$", re.IGNORECASE)


def sanitize_tokens(tokens) -> list[str]:
    """Purge mojibake from scraped keyword/hashtag/bio tokens BEFORE display (runs before
    _esc, not instead of it). Decodes HTML entities, drops #xNNNN artifacts, zero-width /
    lone-combining marks, and empty/pure-symbol tokens."""
    out: list[str] = []
    for t in tokens or []:
        s = html.unescape(str(t)).strip()
        # drop zero-width (Cf) and lone combining marks (Mn) that aren't alphanumeric
        s = "".join(ch for ch in s
                    if ch.isalnum() or unicodedata.category(ch) not in ("Cf", "Mn"))
        s = s.strip()
        if not s or _ARTIFACT_RE.match(s):
            continue
        if not any(ch.isalnum() for ch in s):
            continue
        out.append(s)
    return out


def _is_placeholder(v) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in PLACEHOLDER_MARKERS or s.isdigit()   # e.g. a junk "10" title


def _cluster_signals(cl: dict) -> list[str]:
    try:
        sj = json.loads(cl.get("signals_json") or "{}")
    except Exception:
        sj = {}
    return [k for k in sj if not k.startswith("_")]


def _signal_basis(cl: dict) -> str | None:
    labels: list[str] = []
    for s in _cluster_signals(cl):
        lab = _SIGNAL_SHORT.get(s, s.replace("_", " "))
        if lab not in labels:
            labels.append(lab)
    return " + ".join(labels) if labels else None


def _has_hard_id(cl: dict) -> bool:
    return any(s in _HARD_ID_SIGNALS for s in _cluster_signals(cl))


def _display_confidence(cl: dict) -> float:
    """Display clamp only (never mutates stored scores): no biometric/verified-ID signal ->
    cap at 95, because 100% on a handle+email link is an overclaim a defence will dismantle."""
    c = float(cl.get("confidence_score") or 0)
    return c if _has_hard_id(cl) else min(c, 95.0)


class _SummaryCanvas(base._NumberedCanvas):
    """Adds a diagonal DRAFT watermark when meta['draft'] is set. Subclass so the full
    report's _NumberedCanvas is untouched."""

    def _draw_furniture(self, total_pages: int):
        super()._draw_furniture(total_pages)
        if (getattr(self, "_meta", {}) or {}).get("draft"):
            w, h = A4
            self.saveState()
            self.setFont("Times-Bold", 58)
            self.setFillColor(colors.Color(0.78, 0.12, 0.12, alpha=0.10))
            self.translate(w / 2, h / 2)
            self.rotate(34)
            self.drawCentredString(0, 0, "DRAFT — NOT FOR FILING")
            self.restoreState()


def _summary_canvas_factory(meta: dict):
    def maker(*args, **kwargs):
        c = _SummaryCanvas(*args, **kwargs)
        c._meta = meta
        return c
    return maker


# --------------------------------------------------------------------------- #
#  Part 1 — tiered evidence graph (deterministic SVG -> reportlab Drawing)
# --------------------------------------------------------------------------- #
def _members(cl, ent_by_id):
    """Cluster's member entities, with metadata_json parsed into 'metadata' (for name_intel)."""
    try:
        ids = json.loads(cl.get("entity_ids_json") or "[]")
    except Exception:
        ids = []
    out = []
    for eid in ids:
        e = ent_by_id.get(eid)
        if not e:
            continue
        m = dict(e)
        try:
            m["metadata"] = json.loads(e.get("metadata_json") or "{}")
        except Exception:
            m["metadata"] = {}
        out.append(m)
    return out


def _cluster_label(members) -> str:
    """Short identity label for a cluster: recovered real name if any, else the most common
    handle, else 'cluster'. Deterministic (Counter.most_common is stable on ties by insertion)."""
    try:
        from backend.analysis.name_intel import resolve_cluster_identity
        ident = resolve_cluster_identity(members)
        if ident and ident.get("name"):
            return ident["name"]
    except Exception:
        pass
    from collections import Counter
    handles = Counter(str(m.get("value") or "").strip() for m in members if m.get("value"))
    handles.pop("", None)
    if handles:
        return "@" + handles.most_common(1)[0][0]
    return "cluster"


def _cluster_summary(cl, ent_by_id) -> str:
    """ONE point-wise line per cluster: N accounts · handle(s) · platforms — never every name."""
    members = _members(cl, ent_by_id)
    count = len(members)
    plats = sorted({str(m.get("platform") or "?") for m in members})
    dh = list(dict.fromkeys(str(m.get("value") or "").strip() for m in members if m.get("value")))
    handle_str = (
        ", ".join("@" + h for h in dh[:3]) + (f" +{len(dh) - 3} more" if len(dh) > 3 else ""))
    plat_str = ", ".join(plats[:6]) + (f" +{len(plats) - 6} more" if len(plats) > 6 else "")
    return f"{count} account{'s' if count != 1 else ''} · {handle_str} · across {plat_str}"


# Caps keep the figure legible AND bound its height so it always fits an A4 frame.
_CLUSTER_CAP = 8
_LEAD_CAP = 6
_GRAPH_W = 460            # < A4 content width (~481pt)


def _render_graph_svg(linked, leads, seed_label, ent_by_id) -> str:
    """Seed -> IDENTITY-CLUSTER nodes (mirrors the app graph's seed -> identities structure),
    each labelled with its account count. Confirmed clusters: solid navy edge + filled node;
    leads: faint dashed grey edge + hollow node. Deterministic ordering (confidence, then id)."""
    def node(cl):
        members = _members(cl, ent_by_id)
        return _cluster_label(members), len(members), _signal_basis(cl)

    conf = [(node(c), c) for c in sorted(linked, key=lambda c: (-(c.get("confidence_score") or 0), c.get("cluster_id") or ""))]
    lead = [(node(c), c) for c in sorted(leads, key=lambda c: (-(c.get("confidence_score") or 0), c.get("cluster_id") or ""))]
    conf_extra = max(0, len(conf) - _CLUSTER_CAP)
    lead_extra = max(0, len(lead) - _LEAD_CAP)
    conf = conf[:_CLUSTER_CAP]
    lead = lead[:_LEAD_CAP]

    navy = "#" + base.NAVY.hexval()[2:]
    grey = "#B4B2A9"
    rows = max(1, len(conf) + (1 if conf_extra else 0) + len(lead) + (1 if lead_extra else 0))
    step = 40
    H = max(170, 38 + rows * step + 28)
    sx, sy = 66, H / 2
    rx = 280
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_GRAPH_W}" height="{int(H)}" '
         f'font-family="Times New Roman, serif">']

    y = 40
    for (label, count, basis), c in conf:        # confirmed identity: solid navy + filled node
        p.append(f'<line x1="{sx}" y1="{sy:.0f}" x2="{rx}" y2="{y}" stroke="{navy}" stroke-width="2.6"/>')
        p.append(f'<circle cx="{rx}" cy="{y}" r="6.5" fill="{navy}"/>')
        p.append(f'<text x="{rx + 13}" y="{y + 2}" font-size="9" fill="#1a1a1a">'
                 f'{base._esc(label)} · {count} account{"s" if count != 1 else ""}</text>')
        if basis:
            p.append(f'<text x="{rx + 13}" y="{y + 13}" font-size="6.5" fill="#5a6470">{base._esc(basis)}</text>')
        y += step
    if conf_extra:
        p.append(f'<line x1="{sx}" y1="{sy:.0f}" x2="{rx}" y2="{y}" stroke="{navy}" stroke-width="2.6"/>')
        p.append(f'<circle cx="{rx}" cy="{y}" r="6.5" fill="{navy}"/>')
        p.append(f'<text x="{rx + 13}" y="{y + 2}" font-size="9" fill="#1a1a1a">+ {conf_extra} more confirmed identities</text>')
        y += step
    for (label, count, _b), c in lead:           # lead cluster: faint dashed grey + hollow node
        p.append(f'<line x1="{sx}" y1="{sy:.0f}" x2="{rx}" y2="{y}" stroke="{grey}" stroke-width="0.7" stroke-dasharray="3 3"/>')
        p.append(f'<circle cx="{rx}" cy="{y}" r="6" fill="#ffffff" stroke="{grey}" stroke-width="1"/>')
        p.append(f'<text x="{rx + 13}" y="{y + 2}" font-size="8.5" fill="#5a6470">'
                 f'{base._esc(label)} · {count} lead{"s" if count != 1 else ""}</text>')
        y += step
    if lead_extra:
        p.append(f'<line x1="{sx}" y1="{sy:.0f}" x2="{rx}" y2="{y}" stroke="{grey}" stroke-width="0.7" stroke-dasharray="3 3"/>')
        p.append(f'<circle cx="{rx}" cy="{y}" r="6" fill="#ffffff" stroke="{grey}" stroke-width="1"/>')
        p.append(f'<text x="{rx + 13}" y="{y + 2}" font-size="8.5" fill="#5a6470">+ {lead_extra} more single-signal leads</text>')
        y += step

    p.append(f'<circle cx="{sx}" cy="{sy:.0f}" r="8.5" fill="{navy}"/>')   # seed on top
    p.append(f'<text x="{sx - 13}" y="{sy + 2:.0f}" font-size="9.5" text-anchor="end" fill="#1a1a1a">{base._esc(seed_label)}</text>')

    ly = H - 12
    p.append(f'<line x1="16" y1="{ly}" x2="40" y2="{ly}" stroke="{navy}" stroke-width="2.6"/>')
    p.append(f'<text x="46" y="{ly + 3}" font-size="7" fill="#5a6470">confirmed identity (≥2 signals)</text>')
    p.append(f'<line x1="230" y1="{ly}" x2="254" y2="{ly}" stroke="{grey}" stroke-width="0.8" stroke-dasharray="3 3"/>')
    p.append(f'<text x="260" y="{ly + 3}" font-size="7" fill="#5a6470">lead only (not joined)</text>')
    p.append("</svg>")
    return "\n".join(p)


def build_evidence_graph_drawing(clusters, seed_label, ent_by_id):
    """Return a reportlab Drawing of the tiered evidence graph, scaled to fit an A4 frame, or
    None when there is no network worth drawing (<2 confirmed nodes = one line, not a figure)."""
    linked = [c for c in clusters if c.get("tier") in ("HIGH", "MEDIUM")]
    leads = [c for c in clusters if c.get("tier") in ("LOW", "REJECT")]
    total_linked_nodes = sum(len(json.loads(c.get("entity_ids_json") or "[]")) for c in linked)
    if total_linked_nodes < 2:
        return None
    try:
        d = svg2rlg(BytesIO(_render_graph_svg(linked, leads, seed_label, ent_by_id).encode("utf-8")))
    except Exception:
        return None
    if d is None:
        return None
    # safety net: scale the drawing uniformly to fit the A4 content frame (never upscale).
    max_w, max_h = 470.0, 640.0
    try:
        if d.width and d.height:
            s = min(max_w / float(d.width), max_h / float(d.height), 1.0)
            if s < 1.0:
                d.scale(s, s)
                d.width = float(d.width) * s
                d.height = float(d.height) * s
    except Exception:
        pass
    return d


# --------------------------------------------------------------------------- #
#  Part 2 — the summary assembly
# --------------------------------------------------------------------------- #
def _styles():
    ss = base._styles()
    ss.add(ParagraphStyle("Verdict", parent=ss["Body2"], fontName="Times-Bold",
                          fontSize=14.5, leading=19, textColor=base.NAVY, alignment=TA_LEFT,
                          spaceBefore=2, spaceAfter=6))
    ss.add(ParagraphStyle("Action", parent=ss["Body2"], fontName="Times-Roman",
                          fontSize=10, leading=14, spaceAfter=2))
    return ss


def _member_accounts(cl, ent_by_id):
    try:
        ids = json.loads(cl.get("entity_ids_json") or "[]")
    except Exception:
        ids = []
    out = []
    for eid in ids:
        e = ent_by_id.get(eid)
        if e:
            out.append(f"{base._esc(e.get('platform', '?'))}: {base._esc(e.get('value', ''))}")
    return out


def generate_summary_report(case_id: str, output_path: str | None = None) -> str:
    ss = _styles()
    data = base._load_case(case_id)
    case = data["case"] or {"case_id": case_id, "title": "", "seeds_json": "[]"}
    entities = data["entities"]
    clusters = data["clusters"]
    ent_by_id = {e["entity_id"]: e for e in entities}

    officer = (data["user"] or {}).get("username") or ""
    title = case.get("title") or ""
    # jurisdiction is not a stored field — render as a to-complete blank; gate DRAFT on the
    # fields that actually carry placeholder risk (officer / title). Documented deviation.
    draft = _is_placeholder(officer) or _is_placeholder(title)

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    generated = now_dt.strftime("Generated %Y-%m-%d %H:%M UTC")
    try:
        seeds = json.loads(case.get("seeds_json") or "[]")
    except Exception:
        seeds = []
    seed_str = ", ".join(f"{s.get('type', '?')}: {s.get('value', '')}"
                         for s in seeds if isinstance(s, dict)) or "-"
    seed_label = (seeds[0].get("value") if seeds and isinstance(seeds[0], dict) else "") or "Target"

    os.makedirs(config.REPORT_OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(config.REPORT_OUTPUT_DIR, f"BSA63_summary_{case_id}.pdf")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=22 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Intelligence Briefing - {case_id}", author="VERTEX",
        subject="BSA 2023 s.63 Summary (officer briefing)",
    )
    el: list = []

    linked = [c for c in clusters
              if c.get("tier") in ("HIGH", "MEDIUM")
              and len(json.loads(c.get("entity_ids_json") or "[]")) >= 2]
    accounted = set()
    for c in linked:
        accounted.update(json.loads(c.get("entity_ids_json") or "[]"))
    N = len(accounted)
    plats = sorted({str(ent_by_id[e].get("platform") or "?")
                    for e in accounted if e in ent_by_id})
    M = len([e for e in entities if e["entity_id"] not in accounted])
    best_tier = "HIGH" if any(c.get("tier") == "HIGH" for c in linked) else "MEDIUM"

    # ---- 1. verdict line ----
    if not linked:
        verdict = (f"No accounts met the two-signal threshold for a confirmed link; all "
                   f"{len(entities)} discoveries are leads for manual follow-up.")
    else:
        plat_str = ", ".join(plats[:5]) + ("…" if len(plats) > 5 else "")
        verdict = (f"One individual operates {N} linked accounts across {base._esc(plat_str)}, "
                   f"confirmed at {best_tier}; {M} further accounts share the handle but are "
                   f"unconfirmed leads.")
    el += [Paragraph("INTELLIGENCE BRIEFING", ss["SectionNo"]),
           Paragraph(verdict, ss["Verdict"]),
           HRFlowable(width="100%", thickness=0.8, color=base.RULE, spaceBefore=2, spaceAfter=6)]

    # ---- 2. header band facts (officer / jurisdiction / case) ----
    hdr = [
        [Paragraph("<b>Case</b>", ss["CellWrap"]), Paragraph(base._esc(title) if not _is_placeholder(title) else '<font color="#a11111">[title not set]</font>', ss["CellWrap"]),
         Paragraph("<b>Officer</b>", ss["CellWrap"]), Paragraph(base._esc(officer) if not _is_placeholder(officer) else '<font color="#a11111">[officer not set]</font>', ss["CellWrap"])],
        [Paragraph("<b>Seed(s)</b>", ss["CellWrap"]), Paragraph(base._esc(seed_str), ss["CellWrap"]),
         Paragraph("<b>Jurisdiction</b>", ss["CellWrap"]), Paragraph("____________ (to be completed)", ss["CellWrap"])],
        [Paragraph("<b>Generated</b>", ss["CellWrap"]), Paragraph(now_dt.strftime("%Y-%m-%d %H:%M UTC"), ss["CellWrap"]),
         Paragraph("<b>Ref</b>", ss["CellWrap"]), Paragraph(base._esc(str(case.get("case_id") or case_id)[:12]), ss["Mono"])],
    ]
    # Officer-supplied case type/context ("investment fraud through Telegram") — shown so
    # the reader knows what investigation the findings are being read against.
    if (case.get("case_context") or "").strip():
        hdr.append([Paragraph("<b>Case type</b>", ss["CellWrap"]),
                    Paragraph(base._esc(str(case["case_context"]).strip()[:200]), ss["CellWrap"]),
                    Paragraph("", ss["CellWrap"]), Paragraph("", ss["CellWrap"])])
    el += [base._table(hdr, [22 * mm, 62 * mm, 26 * mm, 64 * mm], header=False), Spacer(1, 4 * mm)]

    # ---- 3. what this report establishes (tier count table) ----
    def _tier_accts(tiers):
        s = set()
        for c in clusters:
            if c.get("tier") in tiers:
                s.update(json.loads(c.get("entity_ids_json") or "[]"))
        return s
    confirmed_ct = len(_tier_accts(("HIGH", "MEDIUM")))
    lead_ct = len([e for e in entities if e["entity_id"] not in _tier_accts(("HIGH", "MEDIUM"))])
    el += base._section(ss, "", "What this report establishes")
    tier_rows = [
        [Paragraph("<b>Category</b>", ss["CellWrap"]), Paragraph("<b>Accounts</b>", ss["CellWrap"]), Paragraph("<b>Evidentiary basis</b>", ss["CellWrap"])],
        [Paragraph('<font color="#1d6b3f"><b>Confirmed / probable</b></font>', ss["CellWrap"]), Paragraph(str(confirmed_ct), ss["CellWrap"]),
         Paragraph("HIGH/MEDIUM cluster — ≥2 corroborating signals (e.g. email, photo, activity).", ss["Small"])],
        [Paragraph('<font color="#6b7785"><b>Leads (unconfirmed)</b></font>', ss["CellWrap"]), Paragraph(str(lead_ct), ss["CellWrap"]),
         Paragraph("Single / weak signal — handle match only; not joined. Investigate manually.", ss["Small"])],
    ]
    el += [base._table(tier_rows, [42 * mm, 20 * mm, 112 * mm], header=False),
           Paragraph("Full cryptographic audit trail and Section 63 certificates: see the "
                     "appendix below and the accompanying full report.", ss["Small"]),
           Spacer(1, 4 * mm)]

    # ---- 3b. visual overview: confidence distribution + footprint charts ----
    try:
        _high = len(_tier_accts(("HIGH",)))
        _med = len(_tier_accts(("MEDIUM",)))
        _lead = len([e for e in entities if e["entity_id"] not in _tier_accts(("HIGH", "MEDIUM"))])
        _vb = charts.verdict_bars(_high, _med, _lead)
        if _vb is not None:
            el += [Paragraph("Accounts by confidence tier", ss["Small"]), _vb, Spacer(1, 3 * mm)]
        from collections import Counter as _Counter
        _plat = _Counter(e.get("platform") for e in entities if e.get("platform")).most_common(8)
        _hours: dict = {}
        for e in entities:
            try:
                _m = json.loads(e.get("metadata_json") or "{}")
            except Exception:
                _m = {}
            for _h in (_m.get("posting_hours") or []):
                try:
                    _hi = int(_h)
                except Exception:
                    continue
                if 0 <= _hi < 24:
                    _hours[_hi] = _hours.get(_hi, 0) + 1
        _pb = charts.platform_bars(_plat)
        _ab = charts.activity_hours(_hours)
        if _pb is not None or _ab is not None:
            el += base._section(ss, "", "Subject profile at a glance")
        if _pb is not None:
            el += [Paragraph("Accounts by platform", ss["Small"]), _pb, Spacer(1, 2 * mm)]
        if _ab is not None:
            el += [Paragraph("Active hours (UTC) — from posting-time metadata", ss["Small"]),
                   _ab, Spacer(1, 3 * mm)]
    except Exception:
        pass

    # ---- 4. evidence graph (only when there's a network) ----
    drawing = build_evidence_graph_drawing(clusters, seed_label, ent_by_id)
    if drawing is not None:
        el += base._section(ss, "", "Evidence graph")
        el += [drawing,
               Paragraph("The graph shows confirmed links solid and unproven handle matches "
                         "dashed, consistent with the tier table above.", ss["Small"]),
               Spacer(1, 4 * mm)]

    # ---- 5. confirmed & probable linkages (detail) ----
    el += base._section(ss, "", "Confirmed &amp; probable linkages")
    if linked:
        for n, cl in enumerate(sorted(linked, key=lambda c: -(c.get("confidence_score") or 0)), 1):
            tier = cl.get("tier", "-")
            tc = base.TIER_COLOR.get(tier, base.MUTED)
            conf = _display_confidence(cl)
            basis = _signal_basis(cl) or "see reasoning"
            label = _cluster_label(_members(cl, ent_by_id))
            block = [
                Paragraph(f'<b>{n}. {base._esc(label)}</b> &nbsp;'
                          f'<font color="#{tc.hexval()[2:]}"><b>[{base._esc(tier)}]</b></font> '
                          f'&nbsp;<b>{conf:.0f}%</b> <font color="#5a6470">· {base._esc(basis)}</font>', ss["Body2"]),
                Paragraph(base._esc(_cluster_summary(cl, ent_by_id)), ss["Small"]),
                Paragraph("<b>Reasoning:</b> " + base._esc(cl.get("explanation") or "-"), ss["Body2"]),
                HRFlowable(width="100%", thickness=0.3, color=base.LIGHT, spaceBefore=4, spaceAfter=4),
            ]
            el += [KeepTogether(block)]
    else:
        el += [Paragraph("No accounts met the two-signal threshold. All discoveries are leads "
                         "(see the full report's Digital Footprint section).", ss["Body2"])]

    # ---- 6. what to do next ----
    el += base._section(ss, "", "What to do next")
    if linked:
        for n, cl in enumerate(sorted(linked, key=lambda c: -(c.get("confidence_score") or 0)), 1):
            if cl.get("tier") == "HIGH":
                act = "ready for inclusion pending examiner sign-off."
            else:
                have = set(_cluster_signals(cl))
                missing = "an independent identifier (phone/email) or a photo/face match"
                act = f"corroborate with {missing} before relying on this."
            el += [Paragraph(f"• <b>Cluster {n}</b> ({base._esc(cl.get('tier', '-'))}): {act}", ss["Action"])]
    else:
        el += [Paragraph("• Treat every discovery as an investigative lead; corroborate a "
                         "second independent signal before asserting any linkage.", ss["Action"])]

    # observed topics (sanitized) — exercises the mojibake purge, adds context
    try:
        from backend.analysis.forensics import summarize as _fx
        fx = _fx(entities)
        topics = sanitize_tokens((fx.get("keywords") or [])[:12])
        if topics:
            el += [Spacer(1, 2 * mm),
                   Paragraph("<b>Observed topics:</b> " + base._esc(", ".join(topics)), ss["Small"])]
    except Exception:
        pass

    # ---- 6b. investigation timeline (process milestones from the tamper-evident ledger) ----
    try:
        _rows = get_ledger(case_id)
        _miles = [
            ("Opened", lambda a: a == "investigation_started"),
            ("Scraping", lambda a: a.startswith("scrape")),
            ("Scored", lambda a: a == "scoring_complete"),
            ("AI rerank", lambda a: a == "rerank_summary"),
            ("Capture", lambda a: a == "evidence_capture_started"),
            ("Complete", lambda a: a == "investigation_complete"),
        ]
        _ev = []
        for _lab, _pred in _miles:
            for _r in _rows:
                if _pred(str(_r.get("action") or "")):
                    _ev.append((_lab, (_r.get("timestamp") or "")[11:16]))
                    break
        _tl = charts.timeline(_ev)
        if _tl is not None:
            el += base._section(ss, "", "Investigation timeline")
            el += [_tl, Paragraph("Key milestones, timed from the tamper-evident ledger (UTC).",
                                  ss["Small"]), Spacer(1, 3 * mm)]
    except Exception:
        pass

    # ---- 7. appendix: audit trail & integrity (moved to the back) ----
    el += [PageBreak()]
    el += base._section(ss, "Appendix.", "Audit trail &amp; integrity")
    ok, detail = verify_chain(case_id)
    status_color = "#1d6b3f" if ok else "#a11111"
    el += [Paragraph(f'Integrity verification: <font color="{status_color}"><b>'
                     f'{"INTACT" if ok else "FAILED"}</b></font> — {base._esc(detail)}', ss["Body2"]),
           Spacer(1, 3 * mm)]
    ledger = get_ledger(case_id)
    if ledger:
        rows = [["#", "Action", "Input SHA-256", "Output SHA-256", "Timestamp (UTC)"]]
        for i, r in enumerate(ledger, 1):
            rows.append([str(i), Paragraph(base._esc(r["action"]), ss["CellWrap"]),
                         Paragraph((r["input_hash"] or "")[:18] + "…", ss["Mono"]),
                         Paragraph((r["output_hash"] or "")[:18] + "…", ss["Mono"]),
                         Paragraph((r["timestamp"] or "")[:19], ss["CellWrap"])])
        el += [base._table(rows, [8 * mm, 34 * mm, 44 * mm, 44 * mm, 30 * mm])]
    artifacts = get_artifacts(case_id)
    # Split court-grade evidence exhibits (captured source pages) from routine artifacts so the
    # exhibit annexure reads like an evidence log: source URL + capture method + external
    # timestamp, not just a filename. Grounded in the provenance columns on the artifacts row.
    _ETYPE = {"evidence_mhtml": "MHTML page snapshot", "evidence_screenshot": "Full-page screenshot",
              "evidence_dom": "Post-JS DOM", "evidence_metadata": "Provenance metadata"}
    # Visual exhibits only in this table; the tsr token + manifest record are supporting files.
    evidence = [a for a in artifacts if a.get("artifact_type") in _ETYPE]
    routine = [a for a in artifacts if not str(a.get("artifact_type") or "").startswith("evidence_")]
    if evidence:
        anchored = any(a.get("artifact_type") == "evidence_tsr" for a in evidence)
        el += [Spacer(1, 3 * mm),
               Paragraph(f"<b>Evidence exhibits (captured source pages, SHA-256):</b> "
                         f"{'externally timestamped (RFC-3161)' if anchored else 'internally sealed'}",
                         ss["Small"])]
        rows = [["#", "Exhibit", "Source", "SHA-256"]]
        for i, a in enumerate(evidence, 1):
            label = _ETYPE.get(a.get("artifact_type"), a.get("artifact_type") or "")
            rows.append([str(i), Paragraph(base._esc(label), ss["CellWrap"]),
                         Paragraph(base._esc((a.get("source_url") or "")[:80]), ss["Mono"]),
                         Paragraph((a.get("sha256") or "")[:32] + "…", ss["Mono"])])
        el += [base._table(rows, [8 * mm, 36 * mm, 66 * mm, 56 * mm])]
    if routine:
        el += [Spacer(1, 3 * mm), Paragraph("<b>Captured artifacts (SHA-256):</b>", ss["Small"])]
        rows = [["#", "File", "SHA-256"]]
        for i, a in enumerate(routine, 1):
            rows.append([str(i), Paragraph(base._esc(os.path.basename(a["file_path"] or "")), ss["Mono"]),
                         Paragraph((a["sha256"] or ""), ss["Mono"])])
        el += [base._table(rows, [8 * mm, 56 * mm, 110 * mm])]
    el += [Spacer(1, 4 * mm),
           Paragraph("This briefing is decision-support for the investigating officer. Confidence "
                     "ratings are indicators, not determinations of fact; linkages are to be "
                     "corroborated. Legal basis and certificates: see the full report. [VERIFY-LEGAL]",
                     ss["Legal"])]

    doc.build(el, canvasmaker=_summary_canvas_factory(
        {"case_id": case_id, "generated": generated, "draft": draft}))
    return output_path
