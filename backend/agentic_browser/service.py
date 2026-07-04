"""Service layer: async web-agent tasks + integration into the VERTEX pipeline.

Key fix vs the scaffold: extracted profiles are NOT inserted as standalone island
entities. They flow through `orchestrator.ingest_external_profiles`, which re-correlates
and re-scores them against the rest of the case — so an agentic-scraped account gets
linked/tiered exactly like everything else.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import MAX_CONCURRENT_TASKS
from .schemas import AgenticLookupRequest, AgenticTaskStatus, AgenticStepLog
from .agent import AgenticBrowserEngine

_tasks: Dict[str, AgenticTaskStatus] = {}
_sema = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# lifecycle statuses the agent's step callback is allowed to set on the task
_AGENT_STATUSES = {"navigating", "extracting"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_task(request: AgenticLookupRequest) -> AgenticTaskStatus:
    """Register a new queued web-agent lookup task."""
    import uuid
    task = AgenticTaskStatus(
        task_id=uuid.uuid4().hex,
        case_id=request.case_id,
        tool_id=request.tool_id,
        query=request.query,
        status="queued",
    )
    _tasks[task.task_id] = task
    return task


def get_task(task_id: str) -> Optional[AgenticTaskStatus]:
    return _tasks.get(task_id)


def list_tasks_for_case(case_id: str) -> List[AgenticTaskStatus]:
    return [t for t in _tasks.values() if t.case_id == case_id]


async def run_agentic_task_background(
    task_id: str, request: AgenticLookupRequest, manage_case_status: bool = False
) -> None:
    """Run the browsing task, then ingest results THROUGH the correlation pipeline.

    manage_case_status=True is used by the create-case-and-run flow (`/investigate`): the
    case was freshly created for this lookup, so this task owns its final status. When
    augmenting an existing case (`/run`) it is False and the case's status is left alone.
    """
    task = _tasks.get(task_id)
    if not task:
        return

    def _add_log(action: str, details: str, status: str = "info") -> None:
        task.step_logs.append(
            AgenticStepLog(step_index=len(task.step_logs) + 1, action=action,
                           details=details, status=status))
        task.updated_at = _now_iso()

    def _finish_case(status: str) -> None:
        if not manage_case_status:
            return
        try:
            from backend.cases.case_service import set_status
            set_status(request.case_id, status)
        except Exception:  # noqa: BLE001
            pass

    _finish_case("running")   # mark the freshly-created case as in-progress (own-case flow)
    engine = AgenticBrowserEngine()
    ok, reason = engine.live_available()
    if not ok:
        task.status = "error"
        task.error_message = reason
        _add_log("error", reason, "error")
        _finish_case("error")
        return

    async def _log_cb(log: AgenticStepLog, new_status: str) -> None:
        task.step_logs.append(log)
        if new_status in _AGENT_STATUSES:
            task.status = new_status
        task.updated_at = _now_iso()

    try:
        async with _sema:
            task.status = "navigating"
            task.updated_at = _now_iso()
            result = await engine.run_task(
                tool_id=request.tool_id,
                query=request.query,
                custom_url=request.custom_url,
                custom_instruction=request.custom_instruction,
                log_callback=_log_cb,
            )

        task.extracted_profiles = result.profiles

        # honest outcomes: blocked / nothing-found are NOT errors and NOT fabricated
        if result.blocked and not result.profiles:
            task.status = "blocked"
            _add_log("blocked",
                     result.notes or "Site blocked automated access (CAPTCHA / login wall).",
                     "warning")
            task.updated_at = _now_iso()
            _finish_case("complete")
            return
        if not result.profiles:
            task.status = "complete"
            _add_log("complete", "No profiles were visible on the page.", "info")
            task.updated_at = _now_iso()
            _finish_case("complete")
            return

        # integrate THROUGH the pipeline (re-correlate) — never as island entities
        task.status = "correlating"
        _add_log("correlating",
                 f"Extracted {len(result.profiles)} profile(s); ingesting and re-correlating…",
                 "info")
        from backend.pipeline.orchestrator import ingest_external_profiles
        raws = [ep.to_raw_profile() for ep in result.profiles]
        stats = await asyncio.to_thread(ingest_external_profiles, request.case_id, raws)

        task.entities_added = int(stats.get("added", 0))
        task.status = "complete"
        _add_log("complete",
                 f"Linked {task.entities_added} new account(s); case now has "
                 f"{stats.get('clusters', 0)} clusters.",
                 "success")
        task.updated_at = _now_iso()
        _finish_case("complete")
    except Exception as e:  # noqa: BLE001
        task.status = "error"
        task.error_message = str(e)
        _add_log("error", f"Task failed: {e}", "error")
        task.updated_at = _now_iso()
        _finish_case("error")
