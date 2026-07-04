"""
Core browser-automation engine + curated OSINT tool templates.

This drives a REAL browser (browser-use + Playwright, navigation on Gemini Flash) and
returns only data literally extracted from the page. There is deliberately NO simulated /
fabricated mode: an OSINT tool that invents follower counts or names is worse than useless.
When the live browser is unavailable, or the site blocks us, or nothing is found, we return
an empty result (and an honest `blocked` flag) — never fake profiles.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, List, Optional

from .config import (
    AGENTIC_BROWSER_MODE, GEMINI_API_KEY, GEMINI_MODEL, MAX_STEPS_PER_TASK,
    TASK_TIMEOUT_S, STEP_TIMEOUT_S, HEADLESS_BROWSER,
)
from .schemas import (
    WebToolTarget, AgenticStepLog, ExtractedWebProfile, ExtractedProfilesResult,
)

# Anti-fabrication guardrail appended to every agent task (browser-use extend_system_message).
_GUARDRAIL = (
    "You are a meticulous OSINT web-extraction agent. Absolute rule: NEVER fabricate, guess, "
    "or hallucinate any value. Report ONLY information literally visible on the page. If a "
    "field is not shown, leave it null. If the profile does not exist, the page errors, or a "
    "CAPTCHA / login wall blocks you, return an EMPTY profiles list (set blocked=true if you "
    "were blocked). An empty list is the correct, honest answer when nothing real is found."
)

# Curated OSINT web tools. WhatsMyName / Google-dork templates were intentionally dropped:
# WhatsMyName duplicates the deterministic Maigret/Sherlock enumeration we already run, and
# Google aggressively bot-blocks. Keep the list honest: a reliable Tier-0 site, a best-effort
# Tier-2 site, and a fully general custom target.
CURATED_OSINT_TOOLS: List[WebToolTarget] = [
    WebToolTarget(
        id="socialsearcher",
        name="Social Searcher (real-time mentions)",
        description="Free real-time social search — cross-platform public mentions & profiles. Reliable (no hard bot-wall).",
        target_url="https://www.social-searcher.com/",
        query_placeholder="e.g. ash29_03",
        icon="🔍",
        category="Mention Lookup",
    ),
    WebToolTarget(
        id="inflact",
        name="Inflact Instagram Viewer (best-effort)",
        description="Public Instagram profile viewer / analytics. Cloudflare-protected — best-effort, may be blocked.",
        target_url="https://inflact.com/profiles/instagram-viewer/",
        query_placeholder="e.g. ash29_03",
        icon="📸",
        category="Social Analytics",
    ),
    WebToolTarget(
        id="custom",
        name="Custom web tool (any URL)",
        description="Point the agent at any URL and give a natural-language extraction instruction.",
        target_url="",
        query_placeholder="target identifier / query",
        icon="🛠️",
        category="Custom",
    ),
]


def get_curated_tools() -> List[WebToolTarget]:
    return CURATED_OSINT_TOOLS


def _build_task(tool: WebToolTarget, target_url: str, query: str,
                custom_instruction: Optional[str]) -> str:
    """Construct the natural-language task for the agent, per tool."""
    if tool.id == "inflact":
        return (
            f"Go to {target_url}. Accept any cookie/consent banner. Find the Instagram "
            f"username search box, type '{query}', and submit. Wait for the profile card to "
            f"render. Extract ONLY what is shown for that profile: platform (instagram), "
            f"username, full display name, bio, follower count, following count, post count, "
            f"and the profile photo image URL. Return one profile. If the profile is not found "
            f"or you are blocked, return an empty list."
        )
    if tool.id == "socialsearcher":
        return (
            f"Go to {target_url}. Accept any cookie banner. Search for '{query}'. From the "
            f"results, extract each distinct social-media profile/account visible (platform, "
            f"username/handle, profile URL, and any display name or bio shown). Return them as "
            f"profiles. If nothing is found or you are blocked, return an empty list."
        )
    # custom
    instr = (custom_instruction or
             f"Search for '{query}' and extract any social-media profile/account information you find.")
    return (
        f"Go to {target_url}. {instr} For each result, capture platform, username/handle, "
        f"profile URL, display name, and bio when visible. If nothing is found or you are "
        f"blocked, return an empty list."
    )


class AgenticBrowserEngine:
    """Runs autonomous browser tasks and returns structured, non-fabricated OSINT data."""

    def __init__(self, mode: str = AGENTIC_BROWSER_MODE):
        self.mode = mode

    def live_available(self) -> tuple[bool, str]:
        """(available, reason). Live needs browser-use importable AND a Gemini key."""
        if self.mode == "off":
            return False, "agentic browser disabled (AGENTIC_BROWSER_MODE=off)"
        if not GEMINI_API_KEY:
            return False, "GEMINI_API_KEY not set — cannot drive the browser agent"
        try:
            import browser_use  # noqa: F401
        except Exception as e:  # noqa: BLE001
            return False, f"browser-use not installed ({e})"
        return True, "ok"

    async def run_task(
        self,
        tool_id: str,
        query: str,
        custom_url: Optional[str] = None,
        custom_instruction: Optional[str] = None,
        log_callback: Optional[Callable[[AgenticStepLog, str], Any]] = None,
    ) -> ExtractedProfilesResult:
        """Execute the browsing task and return a structured result. Raises RuntimeError if
        the live browser is unavailable — it NEVER falls back to fabricated data."""
        tool = next((t for t in CURATED_OSINT_TOOLS if t.id == tool_id), CURATED_OSINT_TOOLS[-1])
        target_url = (custom_url or tool.target_url) if tool.id == "custom" else tool.target_url
        if not target_url:
            raise RuntimeError("no target URL provided for the agentic lookup")

        ok, reason = self.live_available()
        if not ok:
            raise RuntimeError(reason)
        return await self._run_live_agent(tool, target_url, query, custom_instruction, log_callback)

    async def _run_live_agent(
        self,
        tool: WebToolTarget,
        target_url: str,
        query: str,
        custom_instruction: Optional[str],
        log_callback: Optional[Callable[[AgenticStepLog, str], Any]],
    ) -> ExtractedProfilesResult:
        from browser_use import Agent, ChatGoogle
        try:
            from browser_use import BrowserProfile
        except Exception:  # noqa: BLE001
            BrowserProfile = None  # type: ignore

        task = _build_task(tool, target_url, query, custom_instruction)
        llm = ChatGoogle(model=GEMINI_MODEL, api_key=GEMINI_API_KEY, temperature=0.0)

        step = {"i": 0}

        async def _emit(details: str, status: str):
            if not log_callback:
                return
            step["i"] += 1
            log = AgenticStepLog(step_index=step["i"], action=status, details=details, status="info")
            res = log_callback(log, status)
            if asyncio.iscoroutine(res):
                await res

        async def on_step_end(agent_obj, *_a, **_kw):
            url = ""
            try:
                url = str(getattr(getattr(agent_obj, "browser_session", None), "current_url", "") or "")
            except Exception:  # noqa: BLE001
                url = ""
            await _emit(f"Agent step {step['i'] + 1}: analyzing page{(' — ' + url) if url else ''}…",
                        "navigating")

        await _emit(f"Launching stealth browser → {target_url}", "navigating")

        agent_kwargs = dict(
            task=task,
            llm=llm,
            use_vision=True,
            output_model_schema=ExtractedProfilesResult,
            extend_system_message=_GUARDRAIL,
            flash_mode=True,
            max_actions_per_step=3,
            step_timeout=STEP_TIMEOUT_S,
        )
        if BrowserProfile is not None:
            try:
                agent_kwargs["browser_profile"] = BrowserProfile(headless=HEADLESS_BROWSER)
            except Exception:  # noqa: BLE001
                pass

        agent = Agent(**agent_kwargs)
        try:
            history = await asyncio.wait_for(
                agent.run(max_steps=MAX_STEPS_PER_TASK, on_step_end=on_step_end),
                timeout=TASK_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            await _emit("Task exceeded time budget — stopping.", "warning")
            return ExtractedProfilesResult(profiles=[], blocked=False, notes="timeout")
        finally:
            await self._safe_close(agent)

        return self._parse_history(history)

    @staticmethod
    async def _safe_close(agent) -> None:
        for attr in ("close", "stop"):
            fn = getattr(agent, attr, None)
            if callable(fn):
                try:
                    r = fn()
                    if asyncio.iscoroutine(r):
                        await r
                    return
                except Exception:  # noqa: BLE001
                    pass
        # last resort: close the browser session directly
        try:
            sess = getattr(agent, "browser_session", None)
            if sess is not None and hasattr(sess, "close"):
                r = sess.close()
                if asyncio.iscoroutine(r):
                    await r
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _parse_history(history) -> ExtractedProfilesResult:
        """Pull the structured ExtractedProfilesResult out of the agent history, defensively."""
        # 1) browser-use structured output (set because output_model_schema was provided)
        for attr in ("structured_output",):
            val = getattr(history, attr, None)
            if isinstance(val, ExtractedProfilesResult):
                return val
        try:
            gso = getattr(history, "get_structured_output", None)
            if callable(gso):
                val = gso()
                if isinstance(val, ExtractedProfilesResult):
                    return val
        except Exception:  # noqa: BLE001
            pass
        # 2) fall back to parsing the final result text as JSON
        try:
            final = history.final_result() if hasattr(history, "final_result") else None
        except Exception:  # noqa: BLE001
            final = None
        if final:
            if isinstance(final, ExtractedProfilesResult):
                return final
            text = final if isinstance(final, str) else json.dumps(final, default=str)
            try:
                return ExtractedProfilesResult.model_validate_json(text)
            except Exception:  # noqa: BLE001
                try:
                    start, end = text.find("{"), text.rfind("}")
                    if start >= 0 and end > start:
                        return ExtractedProfilesResult(**json.loads(text[start:end + 1]))
                except Exception:  # noqa: BLE001
                    pass
        # 3) nothing usable → honest empty (NOT fabricated)
        return ExtractedProfilesResult(profiles=[], blocked=False, notes="no structured result")
