"""
backend/cases/case_routes.py — case + results + report endpoints.

    POST /cases                     create a case (and kick off the investigation)
    GET  /cases                     list my cases
    GET  /cases/{id}                one case (access-controlled)
    GET  /cases/{id}/results        entities + clusters for the dashboard
    GET  /cases/{id}/report         generate + download the BSA-63 PDF
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
                              body.country_filter)
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
