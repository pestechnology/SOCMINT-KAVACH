"""
backend/report/evidence_report.py — the dedicated EVIDENCE EXHIBIT REPORT (a "Hunchly report").

Separate, self-contained PDF that presents every court-grade evidence bundle captured for a
case (backend/evidence/capturer.py) as a numbered exhibit an officer can file directly:

  - the full-page SCREENSHOT embedded inline (what was seen),
  - source URL, page title, capture UTC + clock source,
  - the SHA-256 of each file in the bundle (screenshot / MHTML / DOM / metadata),
  - the external RFC-3161 timestamp status, VERIFIED offline against the bundle hash, and
  - a case chain-of-custody verdict (the tamper-evident ledger recomputed).

Reuses the shared reportlab helpers from bsa63_generator (styles, _esc, _table, _section,
_canvas_factory) so it matches the house style. The full court report and briefing are left
untouched; this is an additional download. Never invents anything — every value is read back
from the stored artifacts + ledger.
"""
from __future__ import annotations

import datetime
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer)

from backend import config
from backend.ledger.audit_ledger import get_artifacts, verify_chain
from backend.report import bsa63_generator as base

# The four visual/provenance files that make up a bundle (the tsr token + manifest are records).
_ETYPE = {
    "evidence_screenshot": "Full-page screenshot (as seen)",
    "evidence_mhtml": "MHTML page snapshot (self-contained)",
    "evidence_dom": "Post-JS DOM (searchable)",
    "evidence_metadata": "Provenance metadata",
}


def _fmt(ts: str) -> str:
    return (ts or "")[:19].replace("T", " ") + " UTC"


def _scaled_image(path: str, max_w_mm: float = 150, max_h_mm: float = 165):
    """Return a reportlab Image scaled to fit the page (aspect preserved), or None. Validates
    the file is a real image first, so a corrupt/truncated screenshot degrades gracefully
    (the exhibit shows a note) instead of crashing the whole report at build time."""
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(path) as im:
            im.verify()  # raises on a corrupt / non-image file
    except Exception:  # noqa: BLE001
        return None
    try:
        iw, ih = ImageReader(path).getSize()
        if not iw or not ih:
            return None
        scale = min((max_w_mm * mm) / iw, (max_h_mm * mm) / ih)
        return Image(path, width=iw * scale, height=ih * scale)
    except Exception:  # noqa: BLE001
        return None


def _bundles(case_id: str) -> tuple[list[dict], int]:
    """Group evidence artifacts into per-page bundles keyed by manifest_id. Returns
    (bundles, orphan_count) — orphans are evidence files with no manifest_id (legacy)."""
    arts = [a for a in get_artifacts(case_id)
            if str(a.get("artifact_type") or "").startswith("evidence_")]
    by_manifest: dict[str, dict] = {}
    orphans = 0
    for a in arts:
        mid = a.get("manifest_id")
        if not mid:
            orphans += 1
            continue
        b = by_manifest.setdefault(mid, {"manifest_id": mid, "files": {}, "source_url": None,
                                         "captured_at": None, "page_title": None})
        b["files"][a["artifact_type"]] = a
        b["source_url"] = b["source_url"] or a.get("source_url")
        b["page_title"] = b["page_title"] or a.get("page_title")
        b["captured_at"] = b["captured_at"] or a.get("captured_at")
    # order by first-capture time
    return sorted(by_manifest.values(), key=lambda b: b.get("captured_at") or ""), orphans


def _timestamp_status(bundle: dict) -> tuple[str, str]:
    """(label, color-hex) for the bundle's external RFC-3161 anchor, verified offline."""
    tsr = bundle["files"].get("evidence_tsr")
    if not tsr:
        return "Internally sealed only (no external timestamp)", "#a1671d"
    # Recover the stamped digest from the persisted manifest, then verify the token offline.
    digest = None
    man = bundle["files"].get("evidence_manifest")
    if man:
        try:
            digest = json.loads(open(man["file_path"], "rb").read().decode("utf-8", "replace")
                                ).get("bundle_sha256")
        except Exception:  # noqa: BLE001
            digest = None
    if digest:
        try:
            from backend.evidence.capturer import verify_timestamp
            ok = verify_timestamp(open(tsr["file_path"], "rb").read(), digest)
            if ok:
                return "RFC-3161 timestamp VERIFIED (FreeTSA) ✓", "#1d6b3f"
            return "RFC-3161 token present — verification FAILED", "#a11111"
        except Exception:  # noqa: BLE001
            pass
    return "RFC-3161 timestamp present (FreeTSA)", "#1d6b3f"


def generate_evidence_report(case_id: str, output_path: str | None = None) -> str:
    ss = base._styles()
    data = base._load_case(case_id)
    case = data["case"] or {"case_id": case_id, "title": ""}
    officer = (data["user"] or {}).get("username") or "____________________"
    title = case.get("title") or ""

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    generated = now_dt.strftime("Generated %Y-%m-%d %H:%M UTC")
    bundles, orphans = _bundles(case_id)
    chain_ok, chain_detail = verify_chain(case_id)

    os.makedirs(config.REPORT_OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(config.REPORT_OUTPUT_DIR, f"Evidence_exhibits_{case_id}.pdf")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=20 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Evidence Exhibit Report - {case_id}", author="VERTEX",
        subject="Court-grade OSINT evidence exhibits (BSA 2023 s.63)",
    )
    el: list = []

    # ---- title + header band ----
    el += [Paragraph("EVIDENCE EXHIBIT REPORT", ss["SectionNo"]),
           Paragraph("Captured OSINT source pages, sealed and independently timestamped.",
                     ss["Body2"]),
           HRFlowable(width="100%", thickness=0.8, color=base.RULE, spaceBefore=2, spaceAfter=6)]
    hdr = [
        [Paragraph("<b>Case</b>", ss["CellWrap"]), Paragraph(base._esc(title) or "-", ss["CellWrap"]),
         Paragraph("<b>Officer</b>", ss["CellWrap"]), Paragraph(base._esc(officer), ss["CellWrap"])],
        [Paragraph("<b>Ref</b>", ss["CellWrap"]), Paragraph(base._esc(str(case_id)[:12]), ss["Mono"]),
         Paragraph("<b>Generated</b>", ss["CellWrap"]), Paragraph(now_dt.strftime("%Y-%m-%d %H:%M UTC"), ss["CellWrap"])],
        [Paragraph("<b>Exhibits</b>", ss["CellWrap"]), Paragraph(str(len(bundles)), ss["CellWrap"]),
         Paragraph("<b>Chain of custody</b>", ss["CellWrap"]),
         Paragraph(('<font color="#1d6b3f"><b>VERIFIED</b></font>' if chain_ok
                    else '<font color="#a11111"><b>BROKEN</b></font>')
                   + f" ({base._esc(chain_detail)})", ss["CellWrap"])],
    ]
    el += [base._table(hdr, [22 * mm, 62 * mm, 30 * mm, 60 * mm], header=False), Spacer(1, 3 * mm)]

    if not bundles:
        el += [Paragraph("No evidence exhibits were captured for this case. (Enable "
                         "'Capture court-grade evidence' when creating the case.)", ss["Small"])]
        doc.build(el, canvasmaker=base._canvas_factory({"case_id": case_id, "generated": generated}))
        return output_path

    el += [Paragraph("Each exhibit below is the source page as seen at capture time. The SHA-256 "
                     "of every file is recorded in the tamper-evident ledger and, where shown, "
                     "the bundle hash is timestamped by an independent RFC-3161 authority — so "
                     "the record cannot be altered or backdated after capture. Files are retained "
                     "under reports/artifacts/ for offline re-verification.", ss["Small"]),
           Spacer(1, 3 * mm)]

    # ---- one block per captured page ----
    for i, b in enumerate(bundles, 1):
        block: list = [HRFlowable(width="100%", thickness=0.6, color=base.RULE, spaceAfter=3),
                       Paragraph(f"<b>Exhibit {i}</b> &nbsp; "
                                 f"{base._esc((b.get('page_title') or '')[:90])}", ss["CellWrap"])]
        shot = b["files"].get("evidence_screenshot")
        img = _scaled_image(shot["file_path"]) if shot else None
        if img is not None:
            block += [Spacer(1, 2 * mm), img, Spacer(1, 2 * mm)]
        else:
            block += [Paragraph("<i>[screenshot unavailable — see MHTML/DOM in artifacts]</i>", ss["Small"])]

        ts_label, ts_color = _timestamp_status(b)
        meta_rows = [
            [Paragraph("<b>Source URL</b>", ss["CellWrap"]),
             Paragraph(base._esc((b.get("source_url") or "")[:110]), ss["Mono"])],
            [Paragraph("<b>Captured</b>", ss["CellWrap"]),
             Paragraph(_fmt(b.get("captured_at")), ss["CellWrap"])],
            [Paragraph("<b>External seal</b>", ss["CellWrap"]),
             Paragraph(f'<font color="{ts_color}">{base._esc(ts_label)}</font>', ss["CellWrap"])],
        ]
        el_files = [["File", "SHA-256"]]
        for et, label in _ETYPE.items():
            a = b["files"].get(et)
            if a:
                el_files.append([Paragraph(base._esc(label), ss["CellWrap"]),
                                 Paragraph(base._esc(a.get("sha256") or ""), ss["Mono"])])
        block += [base._table(meta_rows, [30 * mm, 144 * mm], header=False),
                  Spacer(1, 1.5 * mm),
                  base._table(el_files, [58 * mm, 116 * mm]),
                  Spacer(1, 4 * mm)]
        # keep an exhibit's image + metadata together where it fits; page-break between exhibits
        el += [KeepTogether(block)] if img is None else block
        el += [PageBreak()] if i < len(bundles) else []

    if orphans:
        el += [Spacer(1, 2 * mm),
               Paragraph(f"Note: {orphans} legacy evidence file(s) without a bundle id were "
                         f"omitted from the exhibit list; they remain in the ledger.", ss["Small"])]

    # ---- s.63-style certificate footer ----
    el += [Spacer(1, 4 * mm)]
    el += base._section(ss, "", "Authentication statement (BSA 2023 s.63)")  # returns a list
    el += [Paragraph("Each exhibit above was produced by VERTEX by rendering the stated source "
                     "URL in an automated browser at the captured time and preserving the output "
                     "files unchanged. The SHA-256 value shown for each file is the hash computed "
                     "at capture and recorded in the tamper-evident ledger; the ledger chain "
                     "verification result is stated in the header. Where an RFC-3161 timestamp is "
                     "marked VERIFIED, an independent authority attests the bundle existed, "
                     "unaltered, no later than the stamped time. This report is decision-support; "
                     "the s.63 certificate must be completed and signed by the responsible officer. "
                     "[VERIFY-LEGAL]", ss["Legal"])]

    doc.build(el, canvasmaker=base._canvas_factory({"case_id": case_id, "generated": generated}))
    return output_path
