"""
backend/llm/llm_client.py — Dual-provider LLM client (NVIDIA Cloud + Groq).

Enhancement-only with hard fallbacks. The LLM NEVER decides confidence or
linking on its own. It extracts entities, explains matches, summarises cases,
and — new — reranks singleton profiles against a target persona for relevance
ordering.

Providers:
  NVIDIA  — deepseek-v4-pro (explanations), llama-3.3-70b (extraction)
  Groq    — llama-3.3-70b-versatile (reranking, failover for extraction)

Every method is wrapped in try/except + timeout and degrades to a
deterministic fallback.
"""
from __future__ import annotations

import json
import re
import time

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
    "exact_name_match": "share the exact same real name",
    "fuzzy_name_match": "have highly similar real names",
    "location_overlap": "are based in the same geographic location",
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
    """Dual-provider LLM client with automatic failover."""

    def __init__(self):
        self.nvidia_key = config.NVIDIA_API_KEY
        self.nvidia_url = config.NVIDIA_BASE_URL.rstrip("/")
        self.groq_key = config.GROQ_API_KEY
        self.groq_url = config.GROQ_BASE_URL.rstrip("/")
        self.groq_model = config.GROQ_MODEL
        self.timeout = config.LLM_TIMEOUT_SECONDS

    def _chat(self, model: str, messages: list[dict], temperature: float,
              max_tokens: int, provider: str = "nvidia", timeout: float | None = None) -> str:
        """Make a chat completion call. provider = 'nvidia' | 'groq'."""
        if provider == "groq":
            if not self.groq_key:
                raise RuntimeError("no Groq API key")
            url = f"{self.groq_url}/chat/completions"
            key = self.groq_key
        else:
            if not self.nvidia_key:
                raise RuntimeError("no NVIDIA API key")
            url = f"{self.nvidia_url}/chat/completions"
            key = self.nvidia_key

        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=timeout if timeout is not None else self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _chat_with_failover(self, model: str, messages: list[dict],
                            temperature: float, max_tokens: int) -> str:
        """Try NVIDIA first with a fast timeout (8s), fall back to Groq if NVIDIA fails."""
        try:
            return self._chat(model, messages, temperature, max_tokens, "nvidia", timeout=min(self.timeout, 8.0))
        except Exception as e:
            print(f"[llm] nvidia failover triggered ({e}), falling back to groq...")
            return self._chat(self.groq_model, messages, temperature, max_tokens, "groq")

    def extract_entities(self, text: str) -> list[dict]:
        if not text or not text.strip():
            return []
        try:
            content = self._chat_with_failover(
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
        except Exception:  # noqa: BLE001 - any LLM failure -> deterministic regex fallback
            return _regex_entities(text)

    def extract_keywords(self, text: str, entities: list[dict] = None) -> list[str]:
        """Use LLM to extract top identifying keywords and personal names from case entities."""
        if not text and not entities:
            return []
        try:
            summary_lines = []
            if entities:
                for e in entities[:30]:
                    m = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
                    if not m and isinstance(e.get("metadata_json"), str):
                        try:
                            m = json.loads(e["metadata_json"])
                        except Exception:
                            m = {}
                    name = m.get("name") or m.get("fullname") or m.get("title") or e.get("title") or ""
                    if name and "(@" in name:
                        name = name.split("(@")[0].strip()
                    name = name.split(" • ")[0].split(" | ")[0].strip()
                    bio = m.get("bio") or ""
                    title = m.get("title") or ""
                    snippet = m.get("snippet") or ""
                    if name or bio or title or snippet:
                        summary_lines.append(f"User: {e.get('value')}, Name: {name}, Bio: {bio}, Title: {title}, Snippet: {snippet}")
            prompt_data = "\n".join(summary_lines) if summary_lines else text[:4000]
            messages = [
                {"role": "system", "content":
                 "You are an NSA-grade forensic analyst. Extract the 10-15 most identifying, high-signal keywords and personal identifiers from the provided target account profiles.\n"
                 "RULES:\n"
                 "1. MUST extract actual personal names, first names, last names, and nicknames found in titles, usernames, or text (e.g. if you see 'Ashwin Harish', you MUST include 'ashwin' and 'harish').\n"
                 "2. MUST include specific locations, professions, technologies, or unique interests mentioned.\n"
                 "3. STRICTLY IGNORE generic social media boilerplate and noise words such as: photos, videos, instagram, profile, follow, app, sign, up, subscribers, posts, account, user, channel, likes, views, share, official, page, bio, link, click, join, online, free, content, media, platform, social, phone, galaxy, samsung, flight, mesa, number, tiktok, twitter, facebook, youtube, github, linkedin.\n"
                 "Output ONLY a valid JSON array of lowercase strings, e.g. [\"ashwin\", \"harish\", \"photography\", \"developer\", \"ai\"]. No prose."},
                {"role": "user", "content": prompt_data[:4000]},
            ]
            try:
                content = self._chat(self.groq_model, messages, temperature=0.1, max_tokens=300, provider="groq", timeout=8.0)
            except Exception as ge:
                print(f"[llm] groq failed in extract_keywords ({ge}), falling back to nvidia...")
                content = self._chat_with_failover(config.LLM_EXTRACT_MODEL, messages, temperature=0.1, max_tokens=300)
            content = content.strip()
            if content.startswith("```"):
                content = content.strip("`").split("\n", 1)[-1]
            data = json.loads(content[content.find("["):content.rfind("]") + 1])
            if isinstance(data, list):
                return [str(d).lower().strip() for d in data if str(d).strip() and len(str(d).strip()) >= 3][:15]
            return []
        except Exception as e:
            print(f"[llm] extract_keywords fallback: {e}")
            return []

    def explain_match(self, signals: list[str], tier: str) -> str:
        try:
            content = self._chat_with_failover(
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
            content = self._chat_with_failover(
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

    def rerank_profiles(self, seed_type: str, seed_value: str,
                        target_persona: dict,
                        candidates: list[dict]) -> list[dict]:
        """Batch-rerank singleton profiles against the target persona.

        Args:
            seed_type: 'username', 'email', 'name', etc.
            seed_value: the original search input
            target_persona: merged keywords, bios, locations from confirmed clusters
            candidates: list of {index, platform, value, bio, keywords, location, name, ...}

        Returns:
            list of {index, relevance, reason} sorted by relevance desc.
            Falls back to empty list on failure (caller keeps original ordering).
        """
        if not candidates:
            return []

        # Build concise summaries to fit in context window
        persona_str = json.dumps(target_persona, default=str)[:2000]
        cand_lines = []
        for c in candidates[:50]:  # cap at 50 to stay within context
            parts = [f"#{c['index']}: {c.get('platform','?')}/{c.get('value','?')}"]
            if c.get("bio"):
                parts.append(f"bio: {str(c['bio'])[:150]}")
            if c.get("name"):
                parts.append(f"name: {c['name']}")
            if c.get("keywords"):
                parts.append(f"keywords: {', '.join(c['keywords'][:8])}")
            if c.get("location"):
                parts.append(f"location: {c['location']}")
            cand_lines.append(" | ".join(parts))

        candidates_str = "\n".join(cand_lines)

        prompt = f"""You are an expert OSINT analyst. An investigator searched for {seed_type}: "{seed_value}".

The confirmed target persona has these characteristics:
{persona_str}

Below are unlinked candidate profiles. For each one, assess how likely it belongs to the SAME PERSON as the target persona. Consider:
- Exact Username Match on Legitimate Platforms: If a candidate on a major platform (like Instagram, LinkedIn, GitHub, Twitter, Facebook, YouTube) matches the seed username EXACTLY or very closely, score it HIGH (>= 75) even if the account is private or has an empty bio!
- Country/Location Focus: Over 99% of our investigations focus on India. If a candidate explicitly lists a foreign location outside India (e.g., USA, UK, Canada, Europe), penalize it heavily unless there is overwhelming proof of international relocation.
- Semantic similarity of bio/keywords (not just exact match — "crypto trader" and "investment advisor" are related)
- Professional/interest domain overlap
- Obscure/Random Platforms: Be very skeptical of obscure websites or gaming forums with generic short usernames and no identifying bio or name.

Candidates:
{candidates_str}

Return ONLY a valid JSON array. Each element: {{"index": <int>, "relevance": <0-100>, "reason": "<one line>"}}
Sort by relevance descending. 0 = definitely different person. 100 = almost certainly same person.
Return [] if no candidates. No prose outside the JSON."""

        # Prefer Groq for reranking (faster, saves NVIDIA quota for extraction)
        providers = [("groq", self.groq_model), ("nvidia", config.LLM_EXTRACT_MODEL)]

        for provider, model in providers:
            try:
                content = self._chat(
                    model,
                    [{"role": "system", "content": "You are an OSINT identity resolution expert. Output ONLY valid JSON."},
                     {"role": "user", "content": prompt}],
                    temperature=0.2, max_tokens=3000,
                    provider=provider,
                )
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:]
                start = content.find("[")
                end = content.rfind("]")
                if start >= 0 and end > start:
                    data = json.loads(content[start:end + 1])
                    if isinstance(data, list):
                        # Validate and clean
                        result = []
                        for item in data:
                            if isinstance(item, dict) and "index" in item and "relevance" in item:
                                result.append({
                                    "index": int(item["index"]),
                                    "relevance": max(0, min(100, int(item["relevance"]))),
                                    "reason": str(item.get("reason", "")),
                                })
                        result.sort(key=lambda x: x["relevance"], reverse=True)
                        print(f"[llm] rerank via {provider}: scored {len(result)} candidates")
                        return result
            except Exception as e:
                print(f"[llm] rerank via {provider} failed: {e}")
                continue

        print("[llm] rerank failed on all providers, returning empty")
        return []

    def semantic_similarity_check(self, profile_a: dict, profile_b: dict,
                                  context: str = "") -> dict:
        """Targeted semantic similarity between two profiles.

        Used by the reranker for promotion checks on high-relevance singletons.
        Returns {"score": 0-100, "reason": "...", "should_link": bool}.
        Falls back to {"score": 0, "reason": "LLM unavailable", "should_link": False}.
        """
        prompt = f"""Compare these two online profiles. Are they the SAME PERSON?

Context: {context}

Profile A:
{json.dumps(profile_a, default=str)[:1500]}

Profile B:
{json.dumps(profile_b, default=str)[:1500]}

Analyze: username patterns, bio themes, keywords, location, name, profession, writing style.
Return ONLY valid JSON: {{"score": <0-100>, "reason": "<explanation>", "should_link": <true/false>}}
Score: 0=definitely different, 100=definitely same person. should_link=true only if score>=65."""

        for provider, model in [("groq", self.groq_model), ("nvidia", config.LLM_EXTRACT_MODEL)]:
            try:
                content = self._chat(
                    model,
                    [{"role": "system", "content": "You are an OSINT identity resolution expert. Output ONLY valid JSON."},
                     {"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=300,
                    provider=provider,
                )
                content = content.strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:]
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(content[start:end + 1])
                    return {
                        "score": max(0, min(100, int(data.get("score", 0)))),
                        "reason": str(data.get("reason", "")),
                        "should_link": bool(data.get("should_link", False)),
                    }
            except Exception as e:
                print(f"[llm] similarity_check via {provider} failed: {e}")
                continue

        return {"score": 0, "reason": "LLM unavailable", "should_link": False}
