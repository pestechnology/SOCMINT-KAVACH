"""
backend/analysis/case_chat.py — grounded Q&A assistant over a single case's data (RAG).

The investigator can ask free-text questions ("which accounts share a phone?", "what do we
know about the person's location?", "summarise the strongest link") and get an answer drawn
STRICTLY from what this case actually found — never outside knowledge, never invention. For a
lawful-investigation tool that is the whole point: the assistant must not hallucinate an
identifier or a fact that isn't in the evidence.

Retrieval: a single case is small (tens of entities/clusters), so "retrieval" here is a
compact, structured digest of the case state fed as context — grounded generation without the
overhead of a vector store. The system prompt hard-constrains the model to that context.

LLM routing: NVIDIA-first (a dedicated CHAT_NVIDIA_API_KEY can be set so chat doesn't share
the pipeline's quota), falling back to the pipeline's Groq-first failover, and finally to a
deterministic retrieval answer if no provider is reachable. Never raises.
"""
from __future__ import annotations

import httpx

_SYSTEM = (
    "You are the case assistant inside VERTEX, an OSINT investigation tool used by law "
    "enforcement. Answer the investigator's question using ONLY the CASE DATA provided below. "
    "Rules:\n"
    "- Use nothing but the case data. If the answer isn't in it, say plainly that the case "
    "does not contain that information — never guess, and never use outside/world knowledge to "
    "fill gaps.\n"
    "- Never invent accounts, names, emails, phones, or links that aren't in the data.\n"
    "- Cite the specific account/identifier/signal you're drawing from (e.g. 'github/arjun', "
    "'shared phone +91…').\n"
    "- Be concise and factual — a few sentences. Distinguish CONFIRMED links from unconfirmed "
    "leads when it matters. This may inform a legal filing, so accuracy over completeness.\n"
    "- If the case data includes a CASE TYPE / CONTEXT note from the officer, frame your "
    "guidance for that crime type — but the facts still come ONLY from the case data.\n"
)

_MAX_CONTEXT = 6000
_MAX_HISTORY = 6      # last N turns kept for follow-ups


def _mt(c: dict) -> str:
    return (c.get("match") or {}).get("tier") or c.get("tier") or "LOW"


def build_context(case: dict, entities: list[dict], clusters: list[dict],
                  forensics: dict | None = None) -> str:
    forensics = forensics or {}
    ent_by_id = {e["entity_id"]: e for e in entities}
    lines: list[str] = []

    seeds = ", ".join(f"{s.get('type')}:{s.get('value')}" for s in (case.get("seeds") or [])[:6])
    lines.append(f"SEARCH SEED(S): {seeds or '(none)'}")
    lines.append(f"REGION SCOPE: {case.get('country_filter') or 'ALL'}")
    if (case.get("case_context") or "").strip():
        lines.append(f"CASE TYPE / CONTEXT (officer's note): {str(case['case_context']).strip()[:300]}")
    lines.append(f"TOTAL ACCOUNTS FOUND: {len([e for e in entities if e.get('type') in (None, 'social_account')])}")

    confirmed = [c for c in clusters if len(c.get("entity_ids") or []) > 1 and _mt(c) == "HIGH"]
    probable = [c for c in clusters if _mt(c) == "MEDIUM"]

    lines.append(f"\nCONFIRMED IDENTITY CLUSTERS ({len(confirmed)}):")
    for c in confirmed[:8]:
        handles = [f"{ent_by_id[i].get('platform')}/{ent_by_id[i].get('value')}"
                   for i in (c.get("entity_ids") or []) if i in ent_by_id][:8]
        nm = (c.get("identity") or {}).get("name")
        sigs = ", ".join(k for k in (c.get("signals") or {}).keys() if not k.startswith("_"))
        lines.append(f"  - accounts: {', '.join(handles)}"
                     + (f"; name: {nm}" if nm else "")
                     + (f"; shared signals: {sigs}" if sigs else ""))
        if c.get("explanation"):
            lines.append(f"    reasoning: {c['explanation'][:240]}")

    lines.append(f"\nUNCONFIRMED LEADS ({len(probable)}):")
    for c in probable[:8]:
        handles = [f"{ent_by_id[i].get('platform')}/{ent_by_id[i].get('value')}"
                   for i in (c.get("entity_ids") or []) if i in ent_by_id][:4]
        lines.append(f"  - {', '.join(handles)} (match {(c.get('match') or {}).get('score', '?')}%)")

    # identifiers & attributes
    emails, phones, upis, locations, names = set(), set(), set(), set(), set()
    for e in entities:
        m = e.get("metadata") or {}
        if e.get("type") == "email" or m.get("email"):
            emails.add(m.get("email") or e.get("value"))
        if e.get("type") == "phone" or m.get("phone"):
            phones.add(m.get("phone") or e.get("value"))
        if e.get("type") == "upi":
            upis.add(e.get("value"))
        for loc in ([m.get("location")] if m.get("location") else []):
            locations.add(str(loc))
        for nm in ([m.get("name") or m.get("fullname")] if (m.get("name") or m.get("fullname")) else []):
            names.add(str(nm))
    lines.append("\nDISCOVERED IDENTIFIERS & ATTRIBUTES:")
    lines.append(f"  names seen: {', '.join(list(names)[:10]) or '(none)'}")
    lines.append(f"  emails: {', '.join(list(emails)[:8]) or '(none)'}")
    lines.append(f"  phones: {', '.join(list(phones)[:8]) or '(none)'}")
    lines.append(f"  upi: {', '.join(list(upis)[:6]) or '(none)'}")
    lines.append(f"  locations: {', '.join(list(locations)[:8]) or '(none)'}")

    ident = forensics.get("identity") or {}
    if ident:
        if ident.get("real_names"):
            lines.append(f"  classified real name(s): {', '.join(ident['real_names'][:5])}")
        if ident.get("employers"):
            lines.append(f"  employer(s)/school(s): {', '.join(ident['employers'][:5])}")
    if forensics.get("keywords"):
        lines.append(f"  interests/keywords: {', '.join(list(forensics['keywords'])[:12])}")
    tone = (forensics.get("tone") or {}).get("label")
    if tone:
        lines.append(f"  writing tone: {tone}")

    # LEAK / BREACH DATA — the "Additional Data" tab (NewLeaks OSINT bot). Previously the
    # RAG ignored this entirely, so it could not answer about leaked identity fields. Surface
    # the classified identity fields, leftover labelled facts and breach sources. Passwords
    # are flagged by count only, never echoed as raw credentials in a chat answer.
    leak_ents = [e for e in entities if (e.get("metadata") or {}).get("source") == "newleaks_bot"]
    if leak_ents:
        lines.append("\nLEAK / BREACH DATA (from the 'Additional Data' tab, via NewLeaks OSINT bot):")
        for e in leak_ents[:6]:
            m = e.get("metadata") or {}
            ident = e.get("value") or m.get("value") or "?"
            dbs = m.get("databases") or m.get("breaches") or []
            cnt = m.get("breach_count") or m.get("leaks_count")
            head = f"  for {ident}"
            if dbs:
                head += f"; breach sources: {', '.join(str(x) for x in dbs[:8])}"
            if cnt:
                head += f"; records: {cnt}"
            lines.append(head)

            classified = m.get("leak_classified") or {}
            leftover = m.get("leak_leftover") or {}
            passwords: list = []

            def _emit(key, val):
                if val is None or val == "":
                    return
                if isinstance(val, (list, tuple)):
                    val = ", ".join(str(x) for x in list(val)[:6])
                lines.append(f"    {str(key).replace('_', ' ')}: {val}")

            for k, v in list(classified.items())[:20]:
                if k in ("password", "passwords"):
                    passwords.extend(v if isinstance(v, (list, tuple)) else [v])
                    continue
                _emit(k, v)
            for k, v in list(leftover.items())[:12]:
                _emit(k, v)
            # Raw fallback fields when the LLM classification was unavailable.
            if not classified:
                for label, key in (("names", "names"), ("emails", "emails"),
                                   ("phones", "phones"), ("links", "links"), ("ips", "ips")):
                    _emit(label, m.get(key))
            passwords.extend(m.get("passwords") or [])
            passwords = [p for p in passwords if p]
            if passwords:
                lines.append(f"    passwords: {len(passwords)} leaked "
                             "(sensitive — shown in the Additional Data tab, not repeated here)")

    text = "\n".join(lines)
    return text[:_MAX_CONTEXT]


def suggested_queries(case: dict, entities: list[dict], clusters: list[dict]) -> list[str]:
    """A few relevant questions the investigator is likely to want — clickable prompts.
    Deterministic and grounded in what the case actually contains."""
    qs: list[str] = ["Summarise the strongest finding in this case."]
    ent_by_id = {e["entity_id"]: e for e in entities}

    confirmed = [c for c in clusters if len(c.get("entity_ids") or []) > 1 and _mt(c) == "HIGH"]
    if confirmed:
        handles = [ent_by_id[i].get("value") for i in (confirmed[0].get("entity_ids") or [])
                   if i in ent_by_id]
        if handles:
            qs.append(f"Why are {handles[0]} and {handles[-1]} linked to the same person?")

    has_phone = any(e.get("type") == "phone" or (e.get("metadata") or {}).get("phone") for e in entities)
    has_email = any(e.get("type") == "email" or (e.get("metadata") or {}).get("email") for e in entities)
    if has_phone or has_email:
        qs.append("Which accounts share the same phone number or email?")
    if any((e.get("metadata") or {}).get("location") for e in entities):
        qs.append("What locations are associated with the subject?")
    if any((e.get("metadata") or {}).get("source") == "newleaks_bot" for e in entities):
        qs.append("What personal details surfaced in the leak/breach data?")
    qs.append("What are the unconfirmed leads I should verify next?")
    qs.append("Is there a real name behind the accounts?")

    # de-dupe, keep order, cap
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:6]


def _deterministic_answer(question: str, context: str) -> str:
    """No-LLM fallback: surface the case digest so the investigator still gets grounded facts."""
    return ("The chat model is temporarily unavailable, so I can't compose a written answer "
            "right now. Here is the case data relevant to your question — please read it "
            "directly:\n\n" + context)


def _chat_nvidia(messages: list[dict], timeout: float = 30.0) -> str:
    from backend import config
    if not config.CHAT_NVIDIA_API_KEY:
        raise RuntimeError("no chat NVIDIA key")
    url = f"{config.CHAT_NVIDIA_BASE_URL.rstrip('/')}/chat/completions"
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {config.CHAT_NVIDIA_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": config.CHAT_LLM_MODEL, "messages": messages,
              "temperature": 0.2, "max_tokens": 600},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def answer(case_id: str, user_id: str, question: str,
           history: list[dict] | None = None) -> dict:
    """Answer `question` grounded in the case. Returns {"answer": str, "grounded": bool}.

    history: prior turns as [{"role": "user"|"assistant", "content": str}, ...]. Never raises.
    """
    question = (question or "").strip()
    if not question:
        return {"answer": "Please enter a question about this case.", "grounded": False}

    from backend.cases.case_service import get_results
    data = get_results(case_id, user_id)
    if not data:
        return {"answer": "This case could not be found.", "grounded": False}

    context = build_context(data["case"], data.get("entities", []),
                            data.get("clusters", []), data.get("forensics", {}))

    msgs = [{"role": "system", "content": _SYSTEM + "\n\nCASE DATA:\n" + context}]
    for turn in (history or [])[-_MAX_HISTORY:]:
        role = turn.get("role")
        content = str(turn.get("content") or "")[:1500]
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": question[:1000]})

    # 1) NVIDIA-first (dedicated key, per request).
    try:
        return {"answer": _chat_nvidia(msgs).strip(), "grounded": True}
    except Exception:
        pass
    # 2) Fall back to the pipeline's Groq-first failover.
    try:
        from backend.llm.llm_client import LLMClient
        from backend import config
        out = LLMClient()._chat_with_failover(config.CHAT_LLM_MODEL, msgs,
                                              temperature=0.2, max_tokens=600)
        if out and out.strip():
            return {"answer": out.strip(), "grounded": True}
    except Exception:
        pass
    # 3) No LLM reachable — return the grounded facts directly.
    return {"answer": _deterministic_answer(question, context), "grounded": False}
