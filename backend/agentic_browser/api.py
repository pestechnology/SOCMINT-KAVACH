"""FastAPI router for the Agentic Web Browser.

Auth + ownership: every endpoint that touches a case verifies the caller owns it (same
`get_current_user` dependency the case routes use), so one user can't drive an agent
against — or read tasks for — another user's investigation.
"""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.auth_middleware import get_current_user
from backend.cases.case_service import get_case, create_case
from .schemas import WebToolTarget, AgenticLookupRequest, AgenticTaskStatus
from .agent import get_curated_tools
from .service import (
    create_task, get_task, list_tasks_for_case, run_agentic_task_background,
)

router = APIRouter(prefix="/api/agentic-browser", tags=["agentic-browser"])


def _require_case(case_id: str, user_id: str):
    case = get_case(case_id, user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or access denied.")
    return case


@router.get("/tools", response_model=List[WebToolTarget])
def list_tools(user_id: str = Depends(get_current_user)):
    """Curated OSINT web-tool templates available for autonomous exploration."""
    return get_curated_tools()


@router.post("/run", response_model=AgenticTaskStatus)
def start_lookup(request: AgenticLookupRequest, background_tasks: BackgroundTasks,
                 user_id: str = Depends(get_current_user)):
    """Run an agentic lookup that AUGMENTS an existing investigation (must own the case)."""
    _require_case(request.case_id, user_id)
    task = create_task(request)
    background_tasks.add_task(run_agentic_task_background, task.task_id, request, False)
    return task


class AgenticInvestigateRequest(BaseModel):
    """Create a NEW investigation whose data source is the agentic browser, then run it."""
    query: str = Field(..., description="Target identifier (handle / name)")
    tool_id: str = "socialsearcher"
    title: Optional[str] = None
    seed_type: str = "username"
    custom_url: Optional[str] = None
    custom_instruction: Optional[str] = None


@router.post("/investigate", response_model=AgenticTaskStatus)
def investigate(request: AgenticInvestigateRequest, background_tasks: BackgroundTasks,
                user_id: str = Depends(get_current_user)):
    """Create a fresh case for this user and run the agentic browser as its source. The
    full enumeration pipeline is NOT started — this case is populated by the agent, then
    correlated. Returns the task (whose case_id is the new case)."""
    title = request.title or f"Agentic: {request.query}"
    try:
        case_id = create_case(user_id, title, [{"type": request.seed_type, "value": request.query}])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    lookup = AgenticLookupRequest(
        case_id=case_id, tool_id=request.tool_id, query=request.query,
        custom_url=request.custom_url, custom_instruction=request.custom_instruction,
    )
    task = create_task(lookup)
    background_tasks.add_task(run_agentic_task_background, task.task_id, lookup, True)
    return task


@router.get("/status/{task_id}", response_model=AgenticTaskStatus)
def get_task_status(task_id: str, user_id: str = Depends(get_current_user)):
    """Live execution logs + extracted profiles for a task (must own the task's case)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Agentic lookup task not found.")
    _require_case(task.case_id, user_id)
    return task


@router.get("/case/{case_id}", response_model=List[AgenticTaskStatus])
def get_case_tasks(case_id: str, user_id: str = Depends(get_current_user)):
    """All agentic lookup tasks for an investigation (must own the case)."""
    _require_case(case_id, user_id)
    return list_tasks_for_case(case_id)
