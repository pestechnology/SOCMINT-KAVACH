"""
backend/llm/llm_client.py — NVIDIA Cloud LLM, enhancement-only with hard fallbacks.

The LLM NEVER decides confidence or linking and NEVER sits on the critical path.
Every method is wrapped in try/except + timeout and degrades to a deterministic
fallback. If NVIDIA is slow/unreachable/garbage, the pipeline continues unchanged.

    extract_entities(text) -> list[dict]   # LLM, fallback = regex
    explain_match(signals, tier) -> str     # LLM, fallback = deterministic template
    summarize_case(findings) -> str         # LLM, fallback = ""
"""
from __future__ import annotations

import json
import re

import httpx

from backend import config

_PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\d[\s-]?){10}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_UPI_RE = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b")

# Deterministic explanation phrases (shared with scoring fallback intent).
_SIGNAL_PHRASES = {
    "exact_phone_match": "share the same registered phone number",
    "exact_email_match": "share the same email address",
    "exact_upi_match": "share the same UPI ID",
    "username_exact_match": "use an identical username",
    "username_substring_match": "use closely related usernames",
    "username_fuzzy_match": "use similar usernames",
    "profile_photo_phash": "have visually identical profile photos",
    "posting_hours_overlap": "post during the same hours",
    "stylometry_cosine": "write in a very similar style",
    "breach_co_occurrence": "appear together in the same data breaches",
    "bio_keyword_overlap": "use the same distinctive phrases",
    "reciprocal_mention": "mention each other",
}


def _regex_entities(text: str) -> list[dict]:
    out: list[dict] = []
    for m in set(_EMAIL_RE.findall(text or "")):
        out.append({"type": "email", "value": m, "confidence": 0.9})
    emails = {e["value"] for e in out}
    for m in set(_PHONE_RE.findall(text or "")):
        digits = "".join(ch for ch in m if ch.isdigit())
        if len(digits) >= 10:
            out.append({"type": "phone", "value": m.strip(), "confidence": 0.7})
    for m in set(_UPI_RE.findall(text or "")):
        # skip if this match is actually the local@domain prefix of a real email
        # (e.g. 'arjun@gmail' inside 'arjun@gmail.com') or an email itself
        if m in emails or any(e.startswith(m + ".") or e == m for e in emails):
            continue
        if not m.endswith((".com", ".in", ".org", ".net")):
            out.append({"type": "upi", "value": m, "confidence": 0.6})
    return out


def _template_explanation(signals: list[str], tier: str) -> str:
    phrases = [_SIGNAL_PHRASES.get(s, s) for s in signals]
    if not phrases:
        return "No corroborating signals were found between these accounts."
    joined = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " and " + phrases[-1]
    lead = "strongly indicates" if tier == "HIGH" else "possibly indicates" if tier == "MEDIUM" else "weakly suggests"
    return f"The system {lead} the same person: these accounts {joined}."


class LLMClient:
    def __init__(self):
        self.api_key = config.NVIDIA_API_KEY
        self.base_url = config.NVIDIA_BASE_URL.rstrip("/")
        self.timeout = config.LLM_TIMEOUT_SECONDS

    def _chat(self, model: str, messages: list[dict], temperature: float,
              max_tokens: int) -> str:
        """Raise on any failure; callers handle the fallback."""
        if not self.api_key:
            raise RuntimeError("no NVIDIA API key")
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def extract_entities(self, text: str) -> list[dict]:
        if not text or not text.strip():
            return []
        try:
            content = self._chat(
                config.LLM_EXTRACT_MODEL,
                [
                    {"role": "system", "content":
                     "Extract identifiers from the text. Output ONLY a valid JSON array of "
                     '{"type","value","confidence"} where type is one of '
                     "email|phone|username|upi|name. Return [] if nothing found. No prose."},
                    {"role": "user", "content": text[:4000]},
                ],
                temperature=0.1, max_tokens=1024,
            )
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`").split("\n", 1)[-1]
            data = json.loads(content[content.find("["):content.rfind("]") + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict) and d.get("value")]
            raise ValueError("not a list")
        except Exception as e:  # noqa: BLE001
            print(f"[llm] extract_entities fallback (regex): {e}")
            return _regex_entities(text)

    def explain_match(self, signals: list[str], tier: str) -> str:
        try:
            content = self._chat(
                config.LLM_EXPLAIN_MODEL,
                [
                    {"role": "system", "content":
                     "You explain, in 2-3 plain-English sentences, why social accounts likely "
                     "belong to the same person. Use 'strongly indicates', never 'proves'. "
                     "No markdown."},
                    {"role": "user", "content":
                     f"Tier: {tier}. Signals that matched: {', '.join(signals) or 'none'}. "
                     "Explain the linkage for a non-technical investigator."},
                ],
                temperature=0.7, max_tokens=200,
            )
            return content.strip() or _template_explanation(signals, tier)
        except Exception as e:  # noqa: BLE001
            print(f"[llm] explain_match fallback (template): {e}")
            return _template_explanation(signals, tier)

    def summarize_case(self, findings: dict) -> str:
        try:
            content = self._chat(
                config.LLM_EXPLAIN_MODEL,
                [
                    {"role": "system", "content":
                     "Write a 3-4 sentence neutral case summary for an investigator. No markdown."},
                    {"role": "user", "content": json.dumps(findings, default=str)[:4000]},
                ],
                temperature=0.5, max_tokens=300,
            )
            return content.strip()
        except Exception as e:  # noqa: BLE001
            print(f"[llm] summarize_case fallback (empty): {e}")
            return ""
