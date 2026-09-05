"""
backend/cases/case_routes.py — case + results + report endpoints.

    POST /cases                     create a case (and kick off the investigation)
    POST /cases/bulk/preview        parse an uploaded subject sheet (creates nothing)
    POST /cases/bulk                create + start ONE case per subject in that sheet
    GET  /cases                     list my cases
    GET  /cases/flagged             every red/orange/yellow-flagged account across
                                     ALL my cases, grouped by colour (cross-case view)
    GET  /cases/{id}                one case (access-controlled)
    GET  /cases/{id}/results        entities + clusters for the dashboard
    GET  /cases/{id}/report         generate + download the BSA-63 PDF
    POST /cases/{id}/pivot/suggest  derive candidate seeds from a SET of selected
                                     identifiers (spends nothing — no scrape, no query)
    POST /cases/{id}/pivot          run a pivot on an explicit list of seeds (existing
                                     accounts re-selected + suggestions + manual entries),
                                     re-correlate into this case, and resume polling.
                                     Repeatable: select again from the larger result set.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.auth.auth_middleware import get_current_user
from backend.cases.case_service import (
    create_case, get_case, get_results, list_cases, set_priority,
)
from backend.cases.annotations_service import (
    get_annotations, list_flagged, set_annotation, VALID_FLAGS,
)

router = APIRouter(prefix="/cases", tags=["cases"])


class Seed(BaseModel):
    type: str
    value: str


class NewCase(BaseModel):
    title: str
    seeds: list[Seed]
    country_filter: str = "ALL"
    # Optional free-text "what kind of case is this?" (e.g. "investment fraud through
    # Telegram"). Never used to filter/steer the SEARCH itself — only to sharpen the
    # LLM-generated guidance layers (next steps, briefing, case chat).
    case_context: str = ""
    # When ON, every source page the pipeline loads is captured as a court-grade evidence
    # bundle (MHTML + screenshot + DOM + provenance), hashed, ledgered and externally
    # timestamped (backend/evidence/capturer.py). Off by default — opt-in per case.
    capture_evidence: bool = False


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    question: str
    history: list[ChatTurn] = []


@router.post("")
def create(body: NewCase, background: BackgroundTasks, user_id: str = Depends(get_current_user)):
    try:
        case_id = create_case(user_id, body.title,
                              [s.model_dump() for s in body.seeds],
                              body.country_filter, body.case_context, body.capture_evidence)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Kick off the investigation in the background if the orchestrator exists.
    try:
        from backend.pipeline.orchestrator import run_investigation_sync
        background.add_task(run_investigation_sync, case_id)
    except Exception:
        pass  # orchestrator not built yet — case is created either way

    return {"case_id": case_id}


# ---- bulk intake: one .docx of subject details -> one case per subject ---------------
# Split into preview + create on purpose, the same "spend nothing until the investigator
# commits" shape /cases/{id}/pivot/suggest already uses: parsing is free, but every row is
# a full investigation, so the officer confirms the exact count before any run starts.
# That confirmation is why there is no arbitrary row cap - the FILE SIZE is the bound.

BULK_EXTENSIONS = (".xlsx", ".csv", ".docx")


def _parse_upload(file: UploadFile) -> list[dict]:
    """Read + parse the uploaded subject sheet, or raise HTTP 400 with a readable reason.

    Extension routing (not content sniffing) picks the reader — the three formats are
    unambiguous by name, and an officer who renames a file should be told so plainly
    rather than have the server guess."""
    name = (file.filename or "").lower()
    if not name.endswith(BULK_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Upload an .xlsx, .csv or .docx subject sheet. (.xls and .doc are the "
                   "older binary formats - re-save as .xlsx / .docx.)")
    from backend.ingestion.bulk_subjects import MAX_FILE_BYTES, parse_subjects
    # Read one byte past the cap so an oversized upload is refused without buffering it all.
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400,
                            detail=f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    try:
        return parse_subjects(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk/preview")
def bulk_preview(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    """Parse an uploaded subject sheet (.xlsx / .csv / .docx) and return the subjects
    VERTEX read out of it. Creates no case and spends no query — this is what the UI
    shows for confirmation before anything runs."""
    subjects = _parse_upload(file)
    return {"subjects": subjects, "total_seeds": sum(len(s["seeds"]) for s in subjects)}


@router.post("/bulk")
def bulk_create(background: BackgroundTasks, file: UploadFile = File(...),
                user_id: str = Depends(get_current_user)):
    """Create ONE case per subject in the uploaded sheet and start each investigation.

    Never one case holding every subject's identifiers: the correlation engine links
    accounts that share signals, so merging different people into a single case would
    fabricate cross-subject clusters. Each case then runs the ordinary pipeline, writes
    the ordinary ledger, and yields the ordinary BSA-63 report.

    Runs are queued SEQUENTIALLY (FastAPI BackgroundTasks): one live investigation fans
    out dozens of scrapers, so starting them all at once would exhaust the Serper/LLM
    per-minute budget and degrade every case's results. Each finishes in turn and
    notifies. A large sheet is therefore a long job - the preview reports the count
    up front so that is a deliberate choice, not a surprise."""
    subjects = _parse_upload(file)
    from backend.ingestion.bulk_subjects import MAX_SEEDS_PER_SUBJECT
    from backend.pipeline.orchestrator import run_investigation_sync

    created, warnings = [], []
    for n, subj in enumerate(subjects, start=1):
        try:
            case_id = create_case(user_id, subj["title"], subj["seeds"],
                                  subj["country_filter"], subj["case_context"])
        except ValueError as e:
            # One unusable subject must not sink the whole batch — report and continue.
            warnings.append(f"Subject {n} ({subj['title']}): skipped - {e}")
            continue
        background.add_task(run_investigation_sync, case_id)
        created.append({"case_id": case_id, "title": subj["title"], "seeds": subj["seeds"]})
        if subj.get("dropped_seeds"):
            warnings.append(f"Subject {n} ({subj['title']}): "
                            f"{subj['dropped_seeds']} identifiers dropped "
                            f"({MAX_SEEDS_PER_SUBJECT} per subject max).")
    if not created:
        raise HTTPException(status_code=400,
                            detail="No subject in that document could be turned into a case. "
                                   + (warnings[0] if warnings else ""))
    return {"created": len(created), "cases": created,
            "skipped_subjects": len(subjects) - len(created), "warnings": warnings}


@router.get("")
def list_mine(user_id: str = Depends(get_current_user)):
    return {"cases": list_cases(user_id)}


# NOTE: registered ahead of the "/{case_id}" catch-all below on purpose — Starlette
# matches routes in registration order, and "/cases/flagged" would otherwise be
# swallowed by "/cases/{case_id}" (case_id="flagged") and 404 as a bogus case lookup.
@router.get("/flagged")
def flagged(user_id: str = Depends(get_current_user)):
    """Every red/orange/yellow-flagged account across ALL of this user's cases,
    grouped by colour — powers the cross-case "Flagged" dashboard."""
    return list_flagged(user_id)


@router.get("/{case_id}")
def one(case_id: str, user_id: str = Depends(get_current_user)):
    case = get_case(case_id, user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    return case


@router.get("/{case_id}/results")
def results(case_id: str, user_id: str = Depends(get_current_user)):
    res = get_results(case_id, user_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Not found")
    return res


class AnnotationBody(BaseModel):
    # All optional: send only what changes. bookmarked toggles the saved flag; flag is
    # the red/orange/yellow severity ('' clears it); note is free text.
    bookmarked: bool | None = None
    flag: str | None = None
    note: str | None = None


@router.get("/{case_id}/annotations")
def list_annotations(case_id: str, user_id: str = Depends(get_current_user)):
    """This user's bookmarks + flags for the case, keyed by current entity_id."""
    ann = get_annotations(case_id, user_id)
    if ann is None:
        raise HTTPException(status_code=404, detail="Not found")
    return ann


@router.put("/{case_id}/annotations/{entity_id}")
def upsert_annotation(case_id: str, entity_id: str, body: AnnotationBody,
                      user_id: str = Depends(get_current_user)):
    """Set/clear an account's bookmark, severity flag, and/or note."""
    try:
        result = set_annotation(
            case_id, user_id, entity_id,
            bookmarked=body.bookmarked, flag=body.flag, note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Case or account not found")
    return result


class PriorityBody(BaseModel):
    # '' clears the flag. Anything else must be one of VALID_PRIORITY_FLAGS.
    flag: str = ""


@router.put("/{case_id}/flag")
def set_case_priority(case_id: str, body: PriorityBody, user_id: str = Depends(get_current_user)):
    """Set/clear this case's red/orange/green triage priority (case-level, distinct
    from the per-account annotation flags above)."""
    try:
        result = set_priority(case_id, user_id, body.flag)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.get("/{case_id}/report")
def report(case_id: str, user_id: str = Depends(get_current_user)):
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.report.bsa63_generator import generate_report
    path = generate_report(case_id)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"BSA63_report_{case_id}.pdf")


@router.get("/{case_id}/summary_report")
def summary_report(case_id: str, user_id: str = Depends(get_current_user)):
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.report.bsa63_executive_generator import generate_report
    path = generate_report(case_id)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"BSA63_summary_{case_id}.pdf")


@router.get("/{case_id}/evidence_report")
def evidence_report(case_id: str, user_id: str = Depends(get_current_user)):
    """Dedicated Evidence Exhibit Report — every captured source page as a numbered exhibit
    (embedded screenshot + SHA-256 of each file + external RFC-3161 timestamp + chain verdict).
    A 'Hunchly report' the officer can file. Separate from the briefing and full court report."""
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.report.evidence_report import generate_evidence_report
    path = generate_evidence_report(case_id)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"Evidence_exhibits_{case_id}.pdf")


@router.get("/{case_id}/summary")
def summary(case_id: str, user_id: str = Depends(get_current_user)):
    """Officer-facing intelligence briefing (verdict-first, tiered graph). Separate from the
    full court report above."""
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.report.summary_report import generate_summary_report
    path = generate_summary_report(case_id)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"BSA63_summary_{case_id}.pdf")


@router.post("/{case_id}/chat")
def chat(case_id: str, body: ChatBody, user_id: str = Depends(get_current_user)):
    """Grounded Q&A over this case's data — answers strictly from what the case found."""
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.analysis.case_chat import answer
    history = [t.model_dump() for t in body.history]
    return answer(case_id, user_id, body.question, history)
class SuggestRequest(BaseModel):
    seeds: list[Seed]


@router.post("/{case_id}/pivot/suggest")
def pivot_suggest(case_id: str, body: SuggestRequest, user_id: str = Depends(get_current_user)):
    """Derive candidate seeds from a SET of selected identifiers at once — spends
    nothing (no scrape, no Serper query). Lets the UI show checkboxes + an estimated
    query cost before the investigator commits to running a pivot."""
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.ingestion.derive import estimate_query_count
    from backend.pipeline.orchestrator import compute_pivot_suggestions
    suggestions = compute_pivot_suggestions([s.model_dump() for s in body.seeds], case_id=case_id)
    return {"suggestions": suggestions, "estimated_queries": estimate_query_count(suggestions)}


class PivotRequest(BaseModel):
    seeds: list[dict]


@router.post("/{case_id}/pivot")
def pivot(case_id: str, body: PivotRequest, background: BackgroundTasks,
         user_id: str = Depends(get_current_user)):
    """Run a pivot on an EXPLICIT list of seeds — any mix of already-discovered account
    values re-selected, suggested candidates, and manually-typed identifiers — and
    re-correlate them into THIS case in the background. status flips running ->
    complete, same as case creation, so the existing results poller streams the growth
    live. Repeatable: once complete, select a new batch and POST here again."""
    if not get_case(case_id, user_id):
        raise HTTPException(status_code=404, detail="Not found")
    from backend.pipeline.orchestrator import run_pivot_seeds_sync
    background.add_task(run_pivot_seeds_sync, case_id, body.seeds)
    return {"status": "running"}

