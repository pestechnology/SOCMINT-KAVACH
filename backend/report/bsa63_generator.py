"""
backend/report/bsa63_generator.py — the court-ready evidence package (the moat).

generate_report(case_id) -> path to a professional, multi-section PDF.

Sections (Master Architecture 10.2):
    Cover page  ·  1. Search Manifest  ·  2. Findings Summary  ·  Annexure A
    (artifacts + SHA-256)  ·  Certificate Part A  ·  Certificate Part B
    ·  3. Chain of Custody  ·  Document Integrity Statement

LEGAL POSTURE: every legal string is a TEMPLATE. Citations were checked in
LEGAL_VERIFICATION.md, but Part B is left for a certified expert to sign — VERTEX
never fabricates a signature. If case.minor_involved is set, identifying particulars
are redacted (POCSO Act 2012 s.23 / JJ Act 2015 s.74).
"""
from __future__ import annotations

import datetime
import json
import os
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

from backend import config
from backend.database import get_db
from backend.ledger.audit_ledger import get_artifacts, get_ledger, verify_chain

REDACTED = "[REDACTED - minor protected under POCSO s.23 / JJ Act s.74]"

# Conservative palette — near-black ink, a single navy accent, grey rules.
NAVY = colors.HexColor("#1f2d3d")
INK = colors.HexColor("#1a1a1a")
RULE = colors.HexColor("#8a939c")
LIGHT = colors.HexColor("#eef1f4")
MUTED = colors.HexColor("#5a6470")

TIER_COLOR = {
    "HIGH": colors.HexColor("#1d6b3f"),
    "MEDIUM": colors.HexColor("#9a6a12"),
    "LOW": colors.HexColor("#6b7785"),
    "REJECT": colors.HexColor("#6b7785"),
}


# --------------------------------------------------------------------------- #
#  Page furniture: running header band + footer with "Page X of Y"
# --------------------------------------------------------------------------- #
class _NumberedCanvas(_canvas.Canvas):
    """Two-pass canvas so every page can print 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states = []
        self._meta = kwargs.get("_meta", {})

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_furniture(total)
            super().showPage()
        super().save()

    def _draw_furniture(self, total_pages: int):
        w, h = A4
        meta = getattr(self, "_meta", {}) or {}
        # --- header band ---
        self.saveState()
        self.setFillColor(NAVY)
        self.rect(0, h - 14 * mm, w, 14 * mm, fill=1, stroke=0)
        self.setFillColor(colors.white)
        self.setFont("Times-Bold", 9)
        self.drawString(18 * mm, h - 9 * mm, "ELECTRONIC EVIDENCE REPORT")
        self.setFont("Times-Roman", 8)
        self.drawRightString(w - 18 * mm, h - 9 * mm, "CONFIDENTIAL")
        # --- footer ---
        self.setFillColor(MUTED)
        self.setFont("Times-Roman", 7.5)
        self.setStrokeColor(RULE)
        self.setLineWidth(0.4)
        self.line(18 * mm, 12 * mm, w - 18 * mm, 12 * mm)
        self.drawString(18 * mm, 8 * mm, f"Case {meta.get('case_id', '')}")
        self.drawCentredString(w / 2, 8 * mm, meta.get("generated", ""))
        self.drawRightString(w - 18 * mm, 8 * mm,
                             f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


def _canvas_factory(meta: dict):
    def maker(*args, **kwargs):
        c = _NumberedCanvas(*args, **kwargs)
        c._meta = meta
        return c
    return maker


# --------------------------------------------------------------------------- #
#  Styles
# --------------------------------------------------------------------------- #
def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontName="Times-Bold",
                          fontSize=26, leading=30, alignment=TA_CENTER, textColor=INK,
                          spaceAfter=4))
    ss.add(ParagraphStyle("CoverSub", parent=ss["Normal"], fontName="Times-Roman",
                          fontSize=12.5, alignment=TA_CENTER, textColor=MUTED, leading=16))
    ss.add(ParagraphStyle("SectionNo", parent=ss["Heading2"], fontName="Times-Bold",
                          fontSize=13.5, textColor=NAVY, spaceBefore=4, spaceAfter=2))
    ss.add(ParagraphStyle("Body2", parent=ss["Normal"], fontName="Times-Roman",
                          fontSize=10, leading=14, alignment=TA_JUSTIFY, textColor=INK))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontName="Times-Roman",
                          fontSize=8.5, leading=11, textColor=MUTED))
    ss.add(ParagraphStyle("Legal", parent=ss["Normal"], fontName="Times-Italic",
                          fontSize=8.5, leading=11.5, textColor=MUTED, alignment=TA_JUSTIFY))
    ss.add(ParagraphStyle("CellWrap", parent=ss["Normal"], fontName="Times-Roman",
                          fontSize=8.5, leading=11, textColor=INK))
    ss.add(ParagraphStyle("Mono", parent=ss["Normal"], fontName="Courier",
                          fontSize=7, leading=9, textColor=INK))
    return ss


def _section(ss, number: str, title: str):
    return [
        Spacer(1, 2 * mm),
        Paragraph(f"{number}&nbsp;&nbsp;{title}", ss["SectionNo"]),
        HRFlowable(width="100%", thickness=0.8, color=RULE, spaceBefore=2, spaceAfter=6),
    ]


def _table(data, col_widths, header=True, zebra=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.3, LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]))
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ]
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
#  Data access
# --------------------------------------------------------------------------- #
def _load_case(case_id: str) -> dict:
    conn = get_db()
    try:
        case = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        entities = conn.execute(
            "SELECT * FROM entities WHERE case_id = ? ORDER BY rowid", (case_id,)).fetchall()
        clusters = conn.execute(
            "SELECT * FROM clusters WHERE case_id = ? ORDER BY confidence_score DESC",
            (case_id,)).fetchall()
        user = None
        if case and case["user_id"]:
            user = conn.execute("SELECT * FROM users WHERE user_id = ?",
                                (case["user_id"],)).fetchone()
        return {
            "case": dict(case) if case else None,
            "entities": [dict(e) for e in entities],
            "clusters": [dict(c) for c in clusters],
            "user": dict(user) if user else None,
        }
    finally:
        conn.close()


def _esc(s) -> str:
    """Escape XML-special chars so user/scraped data can't break (or inject into)
    reportlab Paragraph markup. Without this, a value like 'Tom & Jerry' or '<b>' aborts
    PDF generation entirely."""
    if s in (None, ""):
        return "-"
    return _xml_escape(str(s))


def _redact(text, redact: bool) -> str:
    return REDACTED if redact else _esc(text)


# --------------------------------------------------------------------------- #
#  The report
# --------------------------------------------------------------------------- #
def generate_report(case_id: str, output_path: str | None = None) -> str:
    ss = _styles()
    data = _load_case(case_id)
    case = data["case"] or {"case_id": case_id, "title": "(unknown case)",
                            "minor_involved": 0, "created_at": "", "seeds_json": "[]"}
    redact = bool(case.get("minor_involved"))
    officer = (data["user"] or {}).get("username", "____________________")
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    generated = now_dt.strftime("Generated %Y-%m-%d %H:%M UTC")

    os.makedirs(config.REPORT_OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(config.REPORT_OUTPUT_DIR, f"BSA63_report_{case_id}.pdf")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=22 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Electronic Evidence Report - {case_id}",
        author="VERTEX", subject="BSA 2023 Section 63 Electronic Evidence Report",
    )
    el: list = []

    try:
        seeds = json.loads(case.get("seeds_json") or "[]")
    except Exception:
        seeds = []
    seed_str = ", ".join(f"{s.get('type','?')}: {s.get('value','')}"
                         for s in seeds if isinstance(s, dict)) or "-"

    # ===================== COVER =====================
    el += [Spacer(1, 30 * mm),
           Paragraph("ELECTRONIC EVIDENCE REPORT", ss["CoverTitle"]),
           Spacer(1, 2 * mm),
           Paragraph("Prepared under Section 63 of the Bharatiya Sakshya Adhiniyam, 2023",
                     ss["CoverSub"]),
           Paragraph("Social Media Intelligence (SOCMINT) / OSINT Suspect Profiling",
                     ss["CoverSub"]),
           Spacer(1, 6 * mm),
           HRFlowable(width="60%", thickness=1.2, color=NAVY, hAlign="CENTER"),
           Spacer(1, 12 * mm)]

    cover_rows = [
        [Paragraph("<b>Case reference</b>", ss["CellWrap"]), Paragraph(_esc(str(case.get("case_id") or case_id)), ss["Mono"])],
        [Paragraph("<b>Case title</b>", ss["CellWrap"]), Paragraph(_esc(case.get("title", "-")), ss["CellWrap"])],
        [Paragraph("<b>Seed identifier(s)</b>", ss["CellWrap"]), Paragraph(_redact(seed_str, redact), ss["CellWrap"])],
        [Paragraph("<b>Investigating officer</b>", ss["CellWrap"]), Paragraph(_esc(officer), ss["CellWrap"])],
        [Paragraph("<b>Jurisdiction</b>", ss["CellWrap"]), Paragraph("____________________ (to be completed)", ss["CellWrap"])],
        [Paragraph("<b>Report generated</b>", ss["CellWrap"]), Paragraph(now_dt.strftime("%Y-%m-%d %H:%M UTC"), ss["CellWrap"])],
        [Paragraph("<b>Produced by</b>", ss["CellWrap"]), Paragraph("VERTEX - automated OSINT collection &amp; correlation system", ss["CellWrap"])],
    ]
    el += [_table([[Paragraph("<b>Field</b>", ss["CellWrap"]), Paragraph("<b>Detail</b>", ss["CellWrap"])]] + cover_rows,
                  [55 * mm, 119 * mm])]
    el += [Spacer(1, 10 * mm),
           Paragraph("CONFIDENTIAL - FOR INVESTIGATIVE AND JUDICIAL USE ONLY", ss["CoverSub"]),
           Spacer(1, 3 * mm),
           Paragraph("This document collates publicly available information and the system's "
                     "correlation findings. Confidence ratings are decision-support indicators, "
                     "not determinations of fact. Linkage assertions are to be corroborated by "
                     "the investigating officer.", ss["Small"])]
    if redact:
        el += [Spacer(1, 4 * mm),
               Paragraph("NOTICE: This case is flagged as involving a minor. Identifying "
                         "particulars are redacted in accordance with Section 23 of the POCSO "
                         "Act, 2012 and Section 74 of the Juvenile Justice Act, 2015. [VERIFY-LEGAL]",
                         ss["Legal"])]
    el += [PageBreak()]

    # ===================== 1. SEARCH MANIFEST =====================
    ledger = get_ledger(case_id)
    el += _section(ss, "1.", "Search Manifest")
    el += [Paragraph("Each search and processing step recorded by the system, with the SHA-256 "
                     "digest of its inputs and outputs and the time of execution.", ss["Body2"]),
           Spacer(1, 3 * mm)]
    if ledger:
        rows = [["#", "Action", "Search ID", "Input SHA-256", "Output SHA-256", "Timestamp (UTC)"]]
        for n, r in enumerate(ledger, 1):
            rows.append([str(n),
                         Paragraph(_esc(r["action"]), ss["CellWrap"]),
                         Paragraph((r["search_id"] or "")[:10] + "…", ss["Mono"]),
                         Paragraph((r["input_hash"] or "")[:20] + "…", ss["Mono"]),
                         Paragraph((r["output_hash"] or "")[:20] + "…", ss["Mono"]),
                         Paragraph((r["timestamp"] or "")[:19], ss["CellWrap"])])
        el += [_table(rows, [8 * mm, 30 * mm, 22 * mm, 38 * mm, 38 * mm, 28 * mm])]
    else:
        el += [Paragraph("No ledger entries recorded.", ss["Body2"])]
    el += [PageBreak()]

    # ===================== 2. FINDINGS SUMMARY =====================
    el += _section(ss, "2.", "Findings Summary")
    el += [Paragraph("Identified account clusters with confidence tier and the plain-English "
                     "reasoning supporting each linkage decision. A cluster is rated only on "
                     "corroborating evidence; a single-signal match is never treated as a link.",
                     ss["Body2"]), Spacer(1, 4 * mm)]
    ent_by_id = {e["entity_id"]: e for e in data["entities"]}
    if data["clusters"]:
        for n, cl in enumerate(data["clusters"], 1):
            try:
                ids = json.loads(cl.get("entity_ids_json") or "[]")
            except Exception:
                ids = []
            members = []
            for eid in ids:
                e = ent_by_id.get(eid)
                if e:
                    members.append(f"{_esc(e.get('platform','?'))}: {_redact(e.get('value',''), redact)}")
            tier = cl.get("tier", "-")
            conf = cl.get("confidence_score", 0)
            tc = TIER_COLOR.get(tier, MUTED)
            block = [
                Paragraph(f'<b>Cluster {n}</b> &nbsp;'
                          f'<font color="#{tc.hexval()[2:]}"><b>[{_esc(tier)}]</b></font> &nbsp;'
                          f'{_esc(conf)}% confidence', ss["Body2"]),
                Paragraph(f"<b>Accounts:</b> " + ("; ".join(members) or "-"), ss["Small"]),
                Paragraph(f"<b>Reasoning:</b> " + _esc(cl.get("explanation") or "-"), ss["Body2"]),
                HRFlowable(width="100%", thickness=0.3, color=LIGHT, spaceBefore=4, spaceAfter=4),
            ]
            el += [KeepTogether(block)]
    else:
        el += [Paragraph("No clusters recorded for this case.", ss["Body2"])]
    el += [PageBreak()]

    # ===================== 2A. DIGITAL FOOTPRINT & EXPOSURE =====================
    def _m(e):
        try:
            return json.loads(e.get("metadata_json") or "{}")
        except Exception:
            return {}

    ents = data["entities"]
    accounts      = [e for e in ents if e.get("type") == "social_account"]
    registrations = [e for e in ents if e.get("type") == "email_registration"]
    breach_ents   = [e for e in ents if e.get("type") == "breach"]
    phone_intel   = [e for e in ents if e.get("type") == "phone_intel"]

    el += _section(ss, "2A.", "Digital Footprint & Exposure")
    el += [Paragraph("Publicly observable accounts, service registrations, data-breach "
                     "exposure, phone intelligence and activity patterns collected for the "
                     "seed identifier(s). These are investigative leads; the confidence tiers "
                     "in Section 2 indicate which are assessed as the same individual.",
                     ss["Body2"]), Spacer(1, 3 * mm)]

    # --- false-positive filter note ---
    fp_actions = [r for r in ledger if r.get("action") == "false_positive_filter"]
    if fp_actions:
        el += [Paragraph(
            "<i>Validation note:</i> Username enumeration results from Maigret and "
            "Sherlock were validated against a random control probe before inclusion. "
            "Sites that returned a hit for the control string (broken detector) were "
            "excluded from the real results.  See Section 1 (Search Manifest) for "
            f"the {len(fp_actions)} recorded filter step(s) and their audit hashes.",
            ss["Small"]), Spacer(1, 2 * mm)]

    # --- discovered accounts (capped) ---
    if accounts:
        # Build a map from entity_id -> cluster tier for "Confirmed" vs "Possible lead" labelling
        eid_tier: dict[str, str] = {}
        for cl in data["clusters"]:
            try:
                ids = json.loads(cl.get("entity_ids_json") or "[]")
            except Exception:
                ids = []
            t = cl.get("tier", "REJECT")
            for eid in ids:
                eid_tier[eid] = t

        CAP = 40
        el += [Paragraph(f"<b>Discovered accounts</b> ({len(accounts)} total"
                         + (f"; first {CAP} shown" if len(accounts) > CAP else "") + ")",
                         ss["Body2"]), Spacer(1, 1.5 * mm)]
        rows = [["#", "Platform", "Account", "Name", "Status", "Activity (UTC)"]]
        for n, e in enumerate(accounts[:CAP], 1):
            m = _m(e)
            name = m.get("name") or m.get("fullname") or ""
            act = m.get("most_active_time_utc") or ""
            if m.get("posting_frequency_per_day"):
                act = (act + f" · {m.get('posting_frequency_per_day')}/day").strip(" ·")
            tier = eid_tier.get(e.get("entity_id", ""), "REJECT")
            if tier in ("HIGH", "MEDIUM"):
                status_txt = "Confirmed"
            elif tier == "LOW":
                status_txt = "Possible lead"
            else:
                status_txt = "Unconfirmed"
            rows.append([str(n),
                         Paragraph(_esc(e.get("platform")), ss["CellWrap"]),
                         Paragraph(_redact(e.get("value", ""), redact), ss["CellWrap"]),
                         Paragraph(_redact(name, redact) if name else "-", ss["CellWrap"]),
                         Paragraph(_esc(status_txt), ss["CellWrap"]),
                         Paragraph(_esc(act) if act else "-", ss["CellWrap"])])
        el += [_table(rows, [8 * mm, 24 * mm, 44 * mm, 40 * mm, 22 * mm, 36 * mm]),
               Spacer(1, 2 * mm)]
        el += [Paragraph(
            "<i>Status key:</i> <b>Confirmed</b> = HIGH/MEDIUM cluster with ≥2 corroborating "
            "signals.  <b>Possible lead</b> = LOW tier (single or weak signal).  "
            "<b>Unconfirmed</b> = REJECT — no corroborating evidence links this account "
            "to others in the case; treat as an investigative lead only.",
            ss["Small"]), Spacer(1, 3 * mm)]

    # --- email -> registered services (holehe) ---
    if registrations:
        by_email: dict = {}
        for e in registrations:
            by_email.setdefault(e.get("value", ""), []).append(_m(e).get("service") or e.get("platform"))
        el += [Paragraph("<b>Service registrations</b> — services where an email address is "
                         "registered (detected via password-reset / sign-up responses; no login):",
                         ss["Body2"]), Spacer(1, 1.5 * mm)]
        rows = [["Email", "Registered on"]]
        for email, svcs in by_email.items():
            svc_list = ", ".join(sorted({str(s) for s in svcs if s}))
            rows.append([Paragraph(_redact(email, redact), ss["CellWrap"]),
                         Paragraph(_esc(svc_list), ss["CellWrap"])])
        el += [_table(rows, [50 * mm, 124 * mm]), Spacer(1, 4 * mm)]

    # --- breach exposure ---
    if breach_ents:
        el += [Paragraph("<b>Data-breach exposure</b> — public breach corpora in which the "
                         "identifier appears (breach NAMES only; no credentials are collected "
                         "or stored):", ss["Body2"]), Spacer(1, 1.5 * mm)]
        rows = [["Identifier", "Count", "Breaches (sample)"]]
        for e in breach_ents:
            m = _m(e)
            names = m.get("breaches") or []
            sample = ", ".join(str(x) for x in names[:12]) + ("…" if len(names) > 12 else "")
            rows.append([Paragraph(_redact(e.get("value", ""), redact), ss["CellWrap"]),
                         Paragraph(_esc(m.get("breach_count") or len(names)), ss["CellWrap"]),
                         Paragraph(_esc(sample) if sample else "-", ss["CellWrap"])])
        el += [_table(rows, [44 * mm, 18 * mm, 112 * mm]), Spacer(1, 4 * mm)]

    # --- phone intelligence ---
    if phone_intel:
        el += [Paragraph("<b>Phone intelligence</b> (carrier / line-type lookup):", ss["Body2"]),
               Spacer(1, 1.5 * mm)]
        rows = [["Number", "Carrier", "Country", "Line type"]]
        for e in phone_intel:
            m = _m(e)
            rows.append([Paragraph(_redact(e.get("value", ""), redact), ss["CellWrap"]),
                         Paragraph(_esc(m.get("carrier") or "-"), ss["CellWrap"]),
                         Paragraph(_esc(m.get("country") or "-"), ss["CellWrap"]),
                         Paragraph(_esc(m.get("line_type") or "-"), ss["CellWrap"])])
        el += [_table(rows, [44 * mm, 50 * mm, 40 * mm, 40 * mm]), Spacer(1, 4 * mm)]

    if not (accounts or registrations or breach_ents or phone_intel):
        el += [Paragraph("No public footprint data was collected for this case.", ss["Body2"])]
    el += [PageBreak()]

    # ===================== 2B. FORENSIC ANALYSIS =====================
    try:
        from backend.analysis.forensics import summarize as _forensics_summary
        fx = _forensics_summary(data["entities"])
    except Exception:
        fx = {}
    if fx:
        tone = fx.get("tone", {})
        act = fx.get("activity", {})
        eng = fx.get("engagement", {})
        el += _section(ss, "2B.", "Linguistic & Behavioural Forensics")
        el += [Paragraph("Automated analysis of the collected public text and activity "
                         "metadata. These are investigative indicators, not determinations of fact.",
                         ss["Body2"]), Spacer(1, 3 * mm)]
        tone_txt = (f"{tone.get('label', 'neutral')} "
                    f"(compound {tone.get('compound', 0)}; {tone.get('samples_analyzed', 0)} text samples)")
        if tone.get("flag_negative"):
            tone_txt += "  [FLAGGED: predominantly negative / hostile tone]"
        active = ", ".join(f"{int(h):02d}:00" for h in (act.get("active_hours_utc") or []))
        active = (active + f"  ·  {act.get('posts_analyzed', 0)} posts analysed") if act.get("available") \
            else "insufficient temporal data"
        eng_txt = (f"{eng.get('followers_total', 0)} total followers across "
                   f"{len(eng.get('top_accounts') or [])} measured account(s)") if eng.get("available") \
            else "no public engagement metrics available"
        rows = [
            [Paragraph("<b>Indicator</b>", ss["CellWrap"]), Paragraph("<b>Finding</b>", ss["CellWrap"])],
            [Paragraph("Overall tone (sentiment)", ss["CellWrap"]), Paragraph(_esc(tone_txt), ss["CellWrap"])],
            [Paragraph("Top keywords", ss["CellWrap"]),
             Paragraph(_esc(", ".join(fx.get("keywords") or []) or "-"), ss["CellWrap"])],
            [Paragraph("Hashtags", ss["CellWrap"]),
             Paragraph(_esc(", ".join("#" + h for h in (fx.get("hashtags") or [])) or "-"), ss["CellWrap"])],
            [Paragraph("Most active hours (UTC)", ss["CellWrap"]), Paragraph(_esc(active), ss["CellWrap"])],
            [Paragraph("Engagement", ss["CellWrap"]), Paragraph(_esc(eng_txt), ss["CellWrap"])],
        ]
        el += [_table(rows, [55 * mm, 119 * mm], header=False), PageBreak()]

    # ===================== ANNEXURE A =====================
    artifacts = get_artifacts(case_id)
    el += _section(ss, "Annexure A.", "Captured Artifacts")
    el += [Paragraph("Each captured artifact with its SHA-256 digest. Any party may recompute "
                     "these digests independently to confirm the artifacts are unaltered.", ss["Body2"]),
           Spacer(1, 3 * mm)]
    if artifacts:
        rows = [["#", "Type", "File", "SHA-256 digest", "Captured (UTC)"]]
        for n, a in enumerate(artifacts, 1):
            rows.append([str(n),
                         Paragraph(_esc(a["artifact_type"] or ""), ss["CellWrap"]),
                         Paragraph(_esc(os.path.basename(a["file_path"] or "")), ss["Mono"]),
                         Paragraph((a["sha256"] or ""), ss["Mono"]),
                         Paragraph((a["captured_at"] or "")[:19], ss["CellWrap"])])
        el += [_table(rows, [8 * mm, 24 * mm, 38 * mm, 66 * mm, 28 * mm])]
    else:
        el += [Paragraph("No artifacts captured for this case.", ss["Body2"])]
    el += [PageBreak()]

    # ===================== CERTIFICATE PART A =====================
    el += _section(ss, "Certificate.", "Section 63(4) - PART A")
    el += [Paragraph("[VERIFY-LEGAL] To be completed and signed by the person in charge of the "
                     "computer / communication device or the management of the relevant "
                     "activities, identifying the electronic record and the manner of its "
                     "production.", ss["Legal"]), Spacer(1, 3 * mm)]
    part_a = [
        [Paragraph("<b>Particulars</b>", ss["CellWrap"]), Paragraph("<b>Detail</b>", ss["CellWrap"])],
        [Paragraph("Electronic record identified as", ss["CellWrap"]),
         Paragraph(f"VERTEX evidence package for case {case_id}", ss["CellWrap"])],
        [Paragraph("Manner of production", ss["CellWrap"]),
         Paragraph("Automated collection of publicly available OSINT data via the VERTEX system; "
                   "each item hashed (SHA-256) and recorded at the time of capture.", ss["CellWrap"])],
        [Paragraph("Device(s) / system involved", ss["CellWrap"]),
         Paragraph("VERTEX SOCMINT/OSINT pipeline (FastAPI + SQLite). Host particulars: "
                   "____________________", ss["CellWrap"])],
        [Paragraph("Period of operation", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
        [Paragraph("Person in charge (name)", ss["CellWrap"]), Paragraph(_esc(officer), ss["CellWrap"])],
        [Paragraph("Designation", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
        [Paragraph("Signature &amp; date", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
    ]
    el += [_table(part_a, [55 * mm, 119 * mm], header=False), PageBreak()]

    # ===================== CERTIFICATE PART B =====================
    el += _section(ss, "Certificate.", "Section 63(4) - PART B")
    el += [Paragraph("[VERIFY-LEGAL] To be completed and signed by an expert. The hash values "
                     "below were computed by VERTEX using the SHA-256 algorithm. VERTEX does NOT "
                     "fabricate the expert signature - it is left for a certified examiner.",
                     ss["Legal"]), Spacer(1, 3 * mm)]
    hash_rows = [["#", "Record / artifact", "Hash value (SHA-256)"]]
    if artifacts:
        for n, a in enumerate(artifacts, 1):
            hash_rows.append([str(n),
                              Paragraph(_esc(os.path.basename(a["file_path"] or "")), ss["Mono"]),
                              Paragraph((a["sha256"] or ""), ss["Mono"])])
    else:
        hash_rows.append(["-", "(no artifacts)", "-"])
    el += [_table(hash_rows, [8 * mm, 56 * mm, 110 * mm]), Spacer(1, 4 * mm)]
    part_b = [
        [Paragraph("<b>Particulars</b>", ss["CellWrap"]), Paragraph("<b>Detail</b>", ss["CellWrap"])],
        [Paragraph("Hashing algorithm used", ss["CellWrap"]), Paragraph("SHA-256", ss["CellWrap"])],
        [Paragraph("Expert name", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
        [Paragraph("Expert credentials", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
        [Paragraph("Signature &amp; date", ss["CellWrap"]), Paragraph("____________________", ss["CellWrap"])],
    ]
    el += [_table(part_b, [55 * mm, 119 * mm], header=False), PageBreak()]

    # ===================== 3. CHAIN OF CUSTODY =====================
    ok, detail = verify_chain(case_id)
    el += _section(ss, "3.", "Chain of Custody")
    status_color = "#1d6b3f" if ok else "#a11111"
    el += [Paragraph(f'Integrity verification: '
                     f'<font color="{status_color}"><b>{"INTACT" if ok else "FAILED"}</b></font> - {detail}',
                     ss["Body2"]), Spacer(1, 3 * mm)]
    if ledger:
        rows = [["#", "Action", "Actor", "Timestamp (UTC)", "Chain link (prev. hash)"]]
        for n, r in enumerate(ledger, 1):
            rows.append([str(n),
                         Paragraph(_esc(r["action"]), ss["CellWrap"]),
                         Paragraph(_esc(r["actor"] or ""), ss["CellWrap"]),
                         Paragraph((r["timestamp"] or "")[:19], ss["CellWrap"]),
                         Paragraph((r["previous_hash"] or "")[:22] + "…", ss["Mono"])])
        el += [_table(rows, [8 * mm, 34 * mm, 22 * mm, 34 * mm, 50 * mm])]

    # ===================== DOCUMENT INTEGRITY =====================
    el += [Spacer(1, 8 * mm)]
    el += _section(ss, "", "Document Integrity Statement")
    el += [Paragraph("Each artifact annexed to this report carries a SHA-256 digest recorded at "
                     "the time of capture. The audit ledger above is a tamper-evident hash chain: "
                     "altering any recorded step breaks the chain and is detectable on "
                     "re-verification. To independently confirm an artifact, recompute its SHA-256 "
                     "and compare it to the value listed in Annexure A and Certificate Part B.",
                     ss["Body2"]),
           Spacer(1, 4 * mm),
           Paragraph("Legal basis (see LEGAL_VERIFICATION.md): admissibility of electronic records "
                     "under Section 63, Bharatiya Sakshya Adhiniyam, 2023; mandatory certificate per "
                     "<i>Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal</i> (Supreme Court, "
                     "2020); production under Section 94, BNSS 2023. All legal text herein is "
                     "template content pending certified review. [VERIFY-LEGAL]", ss["Legal"])]

    doc.build(el, canvasmaker=_canvas_factory({"case_id": case_id, "generated": generated}))
    return output_path
