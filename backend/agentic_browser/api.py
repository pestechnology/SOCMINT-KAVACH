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


class SmartLookupRequest(BaseModel):
    """Route an identifier to every source that handles its type, fetch + extract + merge."""
    query: str = Field(..., description="the identifier value")
    id_type: str = "username"           # username | email | name | instagram | phone
    include_login: bool = True
    max_public: int = 6                  # cap on Supadata scrapes per lookup (quota)


@router.post("/smart-lookup")
def smart_lookup_endpoint(req: SmartLookupRequest, user_id: str = Depends(get_current_user)):
    """Run a multi-source OSINT lookup and return the merged dossier + per-source results
    (each with its provenance/source). Public sources → Supadata, login → authed browser,
    api → IntelBase. Does not persist — it's lead-generation for the analyst to act on."""
    from .smart import smart_lookup
    return smart_lookup(req.id_type, req.query,
                        include_login=req.include_login, max_public=req.max_public)


class SmartSendRequest(BaseModel):
    """Promote a Quick-Lookup dossier into a real investigation (the bridge)."""
    query: str
    id_type: str = "username"
    dossier: Optional[dict] = None      # the merged OsintDossier from the lookup (as JSON)


@router.post("/smart-lookup/send")
def smart_lookup_send(req: SmartSendRequest, user_id: str = Depends(get_current_user)):
    """Create a case seeded with the query and ingest the dossier's accounts/identifiers
    through the correlation pipeline. Returns {case_id, added}."""
    from .extractor import OsintDossier
    from .smart import dossier_to_profiles
    from backend.pipeline.orchestrator import ingest_external_profiles
    from backend.cases.case_service import set_status

    # 'instagram' isn't a valid case seed type — route it to username.
    seed_type = req.id_type if req.id_type in ("name", "email", "phone", "username", "upi") else "username"
    try:
        case_id = create_case(user_id, f"Lookup: {req.query}", [{"type": seed_type, "value": req.query}])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    dossier = req.dossier if isinstance(req.dossier, OsintDossier) else OsintDossier(**(req.dossier or {}))
    profs = dossier_to_profiles(dossier, req.query, req.id_type)
    set_status(case_id, "running")
    stats = ingest_external_profiles(case_id, profs)
    set_status(case_id, "complete")
    return {"case_id": case_id, "added": stats.get("added", 0)}


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
