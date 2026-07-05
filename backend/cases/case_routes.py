"""
backend/cases/case_routes.py — case + results + report endpoints.

    POST /cases                     create a case (and kick off the investigation)
    GET  /cases                     list my cases
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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.auth.auth_middleware import get_current_user
from backend.cases.case_service import (
    create_case, get_case, get_results, list_cases,
)

router = APIRouter(prefix="/cases", tags=["cases"])


class Seed(BaseModel):
    type: str
    value: str


class NewCase(BaseModel):
    title: str
    seeds: list[Seed]
    minor_involved: bool = False
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
                              [s.model_dump() for s in body.seeds], body.minor_involved,
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


@router.get("")
def list_mine(user_id: str = Depends(get_current_user)):
    return {"cases": list_cases(user_id)}


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

