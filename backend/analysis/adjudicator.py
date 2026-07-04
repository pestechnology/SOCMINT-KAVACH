"""
backend/analysis/adjudicator.py — LLM same-person adjudication agent.

The deterministic engine links accounts only on hard signals (shared photo/email/phone/
face, or username + a corroborating signal). That is precise but misses real accounts a
human investigator would confidently link from context alone — same real name + same city
+ same niche interests across platforms, even with different handles and no shared photo.

This agent is the "human-in-the-loop, but automated" layer the user asked for: it reviews
a candidate account against the KNOWN target holistically (names, handles, bios, locations,
interests, and whatever signals already fired) and returns a same-person verdict with a
confidence and a plain-English reason.

Policy (chosen by the user): a confident adjudication CAN confirm a link on its own — but
the result is always tagged `ai_confirmed` so the UI and the court report present it
distinctly from a hard-evidence match ("AI-assessed", not "forensically anchored"). It is
used both to PROMOTE missed matches and to REJECT weak soft-signal-only clusters.

Fail-safe: any LLM/parse error returns a no-op verdict (same_person=False, confidence=0),
so the pipeline degrades to exactly the deterministic behaviour when the LLM is down.
"""
from __future__ import annotations

import json

_NOOP = {"same_person": False, "confidence": 0, "reason": "adjudicator unavailable"}

_SYSTEM = (
    "You are a forensic identity-resolution examiner. You are given a KNOWN TARGET "
    "(the person under investigation, described by their confirmed accounts) and ONE "
    "CANDIDATE account. Decide whether the candidate is the SAME REAL PERSON as the "
    "target.\n"
    "Weigh: real-name match, username/handle similarity and stylistic variants, "
    "self-described bio/interests/profession overlap, location agreement, and any shared "
    "signals provided. A different display photo or a different handle does NOT rule out a "
    "match — people vary these across platforms. But a common first name alone, or a "
    "generic shared interest alone, is NOT enough.\n"
    "Return `confidence` as the probability they are the SAME person on a 0-100 scale: "
    "100 = certainly the same person (an analyst would testify to it), 50 = genuinely "
    "unsure, 0 = certainly two different people (e.g. a coincidental handle collision "
    "with a conflicting real name or location). Be decisive but calibrated.\n"
    'Output ONLY strict JSON: {"same_person": true/false, "confidence": 0-100, '
    '"reason": "<one or two sentences citing the specific evidence>"}. No prose outside it.'
)


def _fmt_target(anchor: dict) -> str:
    parts = []
    if anchor.get("names"):
        parts.append(f"Real name(s): {', '.join(anchor['names'][:5])}")
    if anchor.get("usernames"):
        parts.append(f"Known handles: {', '.join(anchor['usernames'][:8])}")
    if anchor.get("locations"):
        parts.append(f"Location(s): {', '.join(anchor['locations'][:4])}")
    if anchor.get("employers"):
        parts.append(f"Employer/School: {', '.join(anchor['employers'][:4])}")
    if anchor.get("interests"):
        parts.append(f"Interests: {', '.join(anchor['interests'][:10])}")
    if anchor.get("bios"):
        parts.append("Bio excerpts: " + "  |  ".join(anchor["bios"][:3])[:600])
    if anchor.get("platforms"):
        parts.append(f"Seen on: {', '.join(sorted(set(anchor['platforms']))[:12])}")
    return "\n".join(parts) or "(sparse target profile)"


def _fmt_candidate(c: dict, shared_signals: list[str] | None) -> str:
    parts = [f"Platform: {c.get('platform', '?')}", f"Handle: {c.get('username') or c.get('value') or '?'}"]
    if c.get("name"):
        parts.append(f"Name on profile: {c['name']}")
    if c.get("location"):
        parts.append(f"Location: {c['location']}")
    if c.get("bio"):
        parts.append(f"Bio: {str(c['bio'])[:400]}")
    if shared_signals:
        parts.append(f"Signals already shared with target: {', '.join(shared_signals)}")
    return "\n".join(parts)


def adjudicate(anchor: dict, candidate: dict, shared_signals: list[str] | None = None,
               llm=None) -> dict:
    """Return {"same_person": bool, "confidence": 0-100, "reason": str}. Never raises."""
    try:
        if llm is None:
            from backend.llm.llm_client import LLMClient
            llm = LLMClient()
        from backend import config
        user = (
            "KNOWN TARGET:\n" + _fmt_target(anchor) +
            "\n\nCANDIDATE ACCOUNT:\n" + _fmt_candidate(candidate, shared_signals) +
            "\n\nIs the candidate the same real person as the target?"
        )
        content = llm._chat_with_failover(
            config.LLM_EXTRACT_MODEL,
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": user[:3500]}],
            temperature=0.0, max_tokens=250,
        )
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content[4:] if content.startswith("json") else content
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            return dict(_NOOP)
        data = json.loads(content[start:end + 1])
        if not isinstance(data, dict):
            return dict(_NOOP)
        conf = int(data.get("confidence") or 0)
        conf = max(0, min(100, conf))
        return {
            "same_person": bool(data.get("same_person")) and conf >= 50,
            "confidence": conf,
            "reason": str(data.get("reason") or "").strip()[:400],
        }
    except Exception:  # noqa: BLE001 — any failure = no-op, pipeline stays deterministic
        return dict(_NOOP)
