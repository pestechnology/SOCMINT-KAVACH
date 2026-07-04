"""
backend/analysis/next_actions.py — "What should the officer do next?" recommender.

This is VERTEX's investigative-copilot layer. After a case is scored, it looks at the whole
board — who's confirmed, which leads are unconfirmed, which identifiers surfaced, and where
the gaps are — and produces a short, ranked list of concrete NEXT ACTIONS an investigator
can take: fetch and corroborate a lead, pivot on a leaked email/phone, reverse-image-search
an avatar, re-run wider, pull a breach dump, or manually verify before filing.

Design (mirrors adjudicator.py / identity_agent.py):
  - An LLM proposes actions from a compact case digest (high signal, no raw dumps).
  - A deterministic rule engine ALWAYS runs first and seeds a strong baseline, so the
    feature is useful even when the LLM is rate-limited or offline (it degrades, never
    disappears). The LLM's job is to refine/re-rank and add reasoning, not to be load-bearing.
  - Cached per case (keyed by entity+cluster counts) so repeated results polls don't re-run.
  - Never raises: any failure falls back to the deterministic actions.

Each action: {"priority": "high|medium|low", "action": <machine tag>, "title": <imperative>,
              "detail": <one sentence: why + how>, "target": <identifier/handle/url or "">}.
"""
from __future__ import annotations

import json

# case_id -> (state_key, actions). get_results polls repeatedly; recompute only on change.
_CACHE: dict[str, tuple[tuple, list]] = {}

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

_ACTION_TAGS = {
    "fetch_profile", "breach_lookup", "phone_lookup", "verify_upi", "reverse_image",
    "records_search", "pivot_identifier", "rerun_wider", "expand_seeds", "manual_review",
    "agentic_lookup", "legal_request",
}

_SYSTEM = (
    "You are the lead analyst's copilot inside VERTEX, an OSINT suspect-profiling tool used by "
    "law enforcement. You are given a DIGEST of the current case: confirmed identities, "
    "unconfirmed leads, the identifiers discovered, and coverage gaps. Recommend the most "
    "valuable NEXT INVESTIGATIVE ACTIONS the officer should take to strengthen or extend the "
    "case — be specific and cite the concrete target (a handle, email, phone, name, or URL).\n"
    "Prefer actions that: corroborate an unconfirmed lead into a confirmed link; pivot on a "
    "newly-leaked identifier (email/phone/UPI) to find more accounts; recover a real identity "
    "behind a fake name; or close an obvious gap. Do NOT recommend anything unlawful, and do "
    "NOT invent identifiers that aren't in the digest.\n"
    "If the digest includes a CASE CONTEXT (the officer's note on what kind of case this is, "
    "e.g. 'investment fraud through Telegram'), TAILOR the recommendations to that crime type: "
    "name the specific registry, portal or technique that fits it (NCRP/1930 freeze chain for "
    "financial fraud, UPI/bank trail, chain explorer for crypto, channel enumeration for "
    "Telegram, preservation letters for sextortion evidence, …) and prefer leads consistent "
    "with that context. Use the `legal_request` action tag when the right next step is a "
    "preservation/data request to a platform found in the results. The context NEVER changes "
    "the facts — only which of them to act on first and how.\n"
    f"Each action's `action` field MUST be one of: {', '.join(sorted(_ACTION_TAGS))}.\n"
    'Output ONLY strict JSON: a list of at most 5 objects, each '
    '{"priority": "high|medium|low", "action": "<tag>", "title": "<short imperative>", '
    '"detail": "<one sentence: why this, and how>", "target": "<the identifier/handle/url>"}. '
    "Order by priority (high first). No prose outside the JSON."
)


def _norm_action(a: dict) -> dict | None:
    if not isinstance(a, dict):
        return None
    title = str(a.get("title") or "").strip()
    if not title:
        return None
    pri = str(a.get("priority") or "medium").lower()
    if pri not in _PRIORITY_RANK:
        pri = "medium"
    tag = str(a.get("action") or "manual_review").strip().lower()
    if tag not in _ACTION_TAGS:
        tag = "manual_review"
    return {
        "priority": pri,
        "action": tag,
        "title": title[:120],
        "detail": str(a.get("detail") or "").strip()[:300],
        "target": str(a.get("target") or "").strip()[:200],
    }


MAX_ACTIONS = 3   # cap shown to the officer — 3 focused steps beats a noisy wall of leads


def _dedupe(actions: list[dict], limit: int = MAX_ACTIONS) -> list[dict]:
    # Key on (action, title) — NOT target. The title already names the specific account/
    # identifier ("Corroborate instagram/hsvismay"), so the same recommendation carrying a
    # handle target in one copy and a full URL in another ("instagram/hsvismay" vs
    # "https://instagram.com/hsvismay") collapses to ONE entry instead of showing twice.
    seen, out = set(), []
    for a in actions:
        key = (a["action"], a["title"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    out.sort(key=lambda x: _PRIORITY_RANK.get(x["priority"], 1))
    return out[:limit]


# --------------------------------------------------------------------------------------
# Deterministic baseline — genuinely useful investigative logic, no LLM required.
# --------------------------------------------------------------------------------------

# Case-type playbook: keyword → the one India-practical step officers most often miss for
# that crime type. Only the FIRST match fires (one focused action, not a checklist), and
# only when the officer actually supplied a case context. Keeps the context feature useful
# even when the LLM is offline.
_CONTEXT_PLAYBOOK: list[tuple[tuple[str, ...], dict]] = [
    ((u"fraud", "scam", "invest", "ponzi", "upi", "payment", "bank", "money", "loan",
      "crypto", "trading"),
     {"priority": "high", "action": "records_search",
      "title": "Trigger the NCRP financial-fraud freeze chain",
      "detail": "Log the case on cybercrime.gov.in / dial 1930 with the transaction IDs so "
                "the bank/UPI nodal officers can freeze the money trail; for crypto, trace "
                "the addresses on a chain explorer before funds hop wallets.",
      "target": "https://cybercrime.gov.in"}),
    (("sextortion", "blackmail", "nude", "morph", "intimate", "obscene"),
     {"priority": "high", "action": "manual_review",
      "title": "Preserve the chats and media evidence NOW",
      "detail": "Hash and archive every chat/screenshot before the suspect deletes them, "
                "send platform preservation requests for the flagged accounts, and file "
                "on NCRP under the sexual-harassment category.",
      "target": ""}),
    (("stalk", "harass", "threat", "troll", "abuse", "doxx"),
     {"priority": "high", "action": "legal_request",
      "title": "Serve preservation + IP-disclosure requests on the abusive accounts",
      "detail": "Capture the abusive posts with timestamps, then hit each platform's LE "
                "channel for registration and IP-log disclosure to attribute the handle.",
      "target": ""}),
    (("drug", "narcot", "trafficking", "contraband"),
     {"priority": "high", "action": "records_search",
      "title": "Sweep messaging channels/groups tied to the handles",
      "detail": "Sales move through Telegram/Instagram handles — enumerate the channels "
                "and groups these accounts push, and preserve the posts advertising sale.",
      "target": ""}),
    (("child", "minor", "csam", "pocso", "groom"),
     {"priority": "high", "action": "manual_review",
      "title": "Escalate under POCSO handling rules immediately",
      "detail": "Preserve evidence without re-sharing it, report the accounts through each "
                "platform's CSAM channel (Telegram: stopca@telegram.org), and route the "
                "case through the I4C/NCMEC tipline flow.",
      "target": ""}),
]


def _context_action(context: str) -> dict | None:
    ctx = (context or "").lower()
    if not ctx.strip():
        return None
    for keywords, action in _CONTEXT_PLAYBOOK:
        if any(k in ctx for k in keywords):
            return dict(action)
    return None


def _legal_request_action(case: dict, entities: list[dict], clusters: list[dict],
                          ent_by_id: dict) -> dict | None:
    """One 'request data from the platform' step for the strongest matched account.

    Prefers a platform the officer's case context mentions (e.g. context says 'telegram'
    and a telegram account was found → that's the request to make first)."""
    try:
        from backend.analysis.le_directory import lookup
    except Exception:  # pragma: no cover
        return None
    ctx = str(case.get("case_context") or "").lower()

    def _mt(c):
        return (c.get("match") or {}).get("tier") or c.get("tier") or "LOW"

    ranked = [c for c in clusters if _mt(c) in ("HIGH", "MEDIUM")]
    best, best_entry, ctx_hit = None, None, False
    for c in ranked:
        for eid in (c.get("entity_ids") or []):
            e = ent_by_id.get(eid)
            if not e or e.get("type") not in (None, "social_account"):
                continue
            entry = lookup(e.get("platform"))
            if not entry:
                continue
            hit = bool(ctx) and str(e.get("platform") or "").lower() in ctx
            if best is None or (hit and not ctx_hit):
                best, best_entry, ctx_hit = e, entry, hit
            if ctx_hit:
                break
        if ctx_hit:
            break
    if not best or not best_entry:
        return None
    contact = best_entry.get("portal") or best_entry.get("email") or ""
    return {
        "priority": "high" if ctx_hit else "medium", "action": "legal_request",
        "title": f"Request subscriber data from {best_entry['label']} for "
                 f"{best.get('platform')}/{best.get('value')}",
        "detail": "Send a preservation request now, then subscriber info + IP logs via "
                  f"their law-enforcement channel ({contact}"
                  + (f", {best_entry['email']}" if best_entry.get("email") and best_entry.get("portal") else "")
                  + ") with a BNSS s.94 notice quoting the exact handle.",
        "target": contact,
    }


def _seed_values(case: dict) -> set[str]:
    out = set()
    for s in (case.get("seeds") or []):
        v = str(s.get("value") or "").strip().lower()
        if v:
            out.add(v)
    return out


def deterministic_actions(case: dict, entities: list[dict], clusters: list[dict]) -> list[dict]:
    actions: list[dict] = []
    seeds = _seed_values(case)

    def _match_tier(c):
        return (c.get("match") or {}).get("tier") or c.get("tier") or "LOW"

    multi = [c for c in clusters if len(c.get("entity_ids") or []) > 1]
    confirmed = [c for c in multi if _match_tier(c) == "HIGH" or c.get("tier") == "HIGH"]

    # 0) Officer supplied a case type/context → lead with the playbook step for that crime,
    #    and the data request for the platform the context points at.
    ctx_action = _context_action(case.get("case_context") or "")
    if ctx_action:
        actions.append(ctx_action)
    ent_by_id_early = {e["entity_id"]: e for e in entities}
    lr = _legal_request_action(case, entities, clusters, ent_by_id_early)
    if lr:
        actions.append(lr)

    # 1) Corroborate the strongest UNCONFIRMED lead (has a URL we can fetch).
    leads = [c for c in clusters
             if _match_tier(c) == "MEDIUM" and len(c.get("entity_ids") or []) >= 1]
    ent_by_id = {e["entity_id"]: e for e in entities}
    for c in leads[:2]:
        for eid in (c.get("entity_ids") or []):
            e = ent_by_id.get(eid)
            if e and e.get("source_url") and e.get("type") in (None, "social_account"):
                actions.append({
                    "priority": "high", "action": "fetch_profile",
                    "title": f"Corroborate {e.get('platform','account')}/{e.get('value','')}",
                    "detail": "Fetch this unconfirmed profile's bio, photo and links to test "
                              "whether it truly belongs to the subject before relying on it.",
                    "target": e.get("source_url") or e.get("value") or "",
                })
                break

    # 2) Pivot on discovered identifiers that were NOT the original seed.
    emails, phones, upis = [], [], []
    for e in entities:
        m = e.get("metadata") or {}
        val = str(e.get("value") or "").strip()
        et = e.get("type")
        if (et == "email" or "@" in val) and m.get("email", val) and val.lower() not in seeds:
            emails.append(m.get("email") or val)
        if et == "phone" and val.lower() not in seeds:
            phones.append(val)
        if et == "upi" and val.lower() not in seeds:
            upis.append(val)
        for extra_e in ([m.get("email")] if m.get("email") else []):
            if extra_e and str(extra_e).lower() not in seeds:
                emails.append(extra_e)
        for extra_p in ([m.get("phone")] if m.get("phone") else []):
            if extra_p and str(extra_p).lower() not in seeds:
                phones.append(extra_p)

    emails = list(dict.fromkeys(emails))[:2]
    phones = list(dict.fromkeys(phones))[:2]
    upis = list(dict.fromkeys(upis))[:1]

    for em in emails:
        actions.append({
            "priority": "high", "action": "breach_lookup",
            "title": f"Pivot on the leaked email {em}",
            "detail": "This email surfaced during the scan and wasn't the search seed — run a "
                      "breach/registration lookup on it to find accounts and passwords tied to it.",
            "target": str(em),
        })
    for ph in phones:
        actions.append({
            "priority": "medium", "action": "phone_lookup",
            "title": f"Reverse-lookup the phone {ph}",
            "detail": "Run a caller-ID/registration check (Truecaller, carrier) and re-seed the "
                      "investigation with this number to surface linked accounts.",
            "target": str(ph),
        })
    for up in upis:
        actions.append({
            "priority": "medium", "action": "verify_upi",
            "title": f"Verify UPI ID {up}",
            "detail": "Resolve the UPI/VPA against the bank name registry to attribute a real "
                      "account holder name to the subject.",
            "target": str(up),
        })

    # 3) Recover / search the confirmed real name.
    real_name = None
    for c in clusters:
        nm = (c.get("identity") or {}).get("name")
        if nm:
            real_name = nm
            break
    if real_name:
        actions.append({
            "priority": "medium", "action": "records_search",
            "title": f"Run public-records / news search on '{real_name}'",
            "detail": "A real name was recovered from a linked account — search open records, "
                      "news and court filings to corroborate identity and find associates.",
            "target": real_name,
        })

    # 4) Reverse-image search an avatar if any profile has a photo.
    for e in entities:
        m = e.get("metadata") or {}
        photo = m.get("photo_url") or m.get("avatar") or m.get("avatar_url")
        if photo:
            actions.append({
                "priority": "medium", "action": "reverse_image",
                "title": f"Reverse-image search the {e.get('platform','profile')} avatar",
                "detail": "Run the profile photo through reverse-image search to find the same "
                          "face reused on other platforms under different handles.",
                "target": str(photo),
            })
            break

    # 5) Coverage gaps → widen the net via the web-reader lookup.
    n_accounts = len([e for e in entities if e.get("type") in (None, "social_account")])
    if n_accounts < 4:
        actions.append({
            "priority": "high" if n_accounts < 2 else "medium", "action": "agentic_lookup",
            "title": "Run a Quick Lookup / agentic web scan",
            "detail": "Few accounts were found via the standard scrapers — use the web-reader "
                      "lookup to pull public profiles (GitHub, Reddit, X, …) directly.",
            "target": "",
        })

    # 6) Expand with the strongest confirmed handle as a new seed.
    if confirmed:
        for eid in (confirmed[0].get("entity_ids") or []):
            e = ent_by_id.get(eid)
            if e and e.get("value") and e.get("type") in (None, "social_account"):
                actions.append({
                    "priority": "low", "action": "expand_seeds",
                    "title": f"Expand from confirmed handle '{e.get('value')}'",
                    "detail": "Seed a fresh scan with this confirmed username to discover further "
                              "accounts the first pass missed.",
                    "target": e.get("value"),
                })
                break

    # 7) Always leave a governance reminder.
    if confirmed:
        actions.append({
            "priority": "low", "action": "manual_review",
            "title": "Manually verify the top cluster before filing",
            "detail": "Confirm the strongest identity link by eye and capture evidence into the "
                      "BSA-63 report before using it in any proceeding.",
            "target": "",
        })

    normed = [a for a in (_norm_action(a) for a in actions) if a]
    return _dedupe(normed, 6)


def _build_digest(case: dict, entities: list[dict], clusters: list[dict],
                  det: list[dict]) -> str:
    lines = []
    seeds = ", ".join(f"{s.get('type')}:{s.get('value')}" for s in (case.get("seeds") or [])[:5])
    lines.append(f"Search seed(s): {seeds or '(none)'}")
    lines.append(f"Region scope: {case.get('country_filter') or 'ALL'}")
    if (case.get("case_context") or "").strip():
        lines.append(f"CASE CONTEXT (officer's note on what kind of case this is): "
                     f"{str(case['case_context']).strip()[:300]}")

    def _mt(c):
        return (c.get("match") or {}).get("tier") or c.get("tier") or "LOW"

    ent_by_id = {e["entity_id"]: e for e in entities}
    confirmed = [c for c in clusters if len(c.get("entity_ids") or []) > 1 and _mt(c) == "HIGH"]
    leads = [c for c in clusters if _mt(c) == "MEDIUM"]
    lines.append(f"\nConfirmed identity clusters ({len(confirmed)}):")
    for c in confirmed[:5]:
        handles = [f"{ent_by_id[i].get('platform')}/{ent_by_id[i].get('value')}"
                   for i in (c.get("entity_ids") or []) if i in ent_by_id][:6]
        nm = (c.get("identity") or {}).get("name")
        lines.append(f"  - {', '.join(handles)}" + (f"  (name: {nm})" if nm else ""))
    lines.append(f"\nUnconfirmed leads ({len(leads)}):")
    for c in leads[:6]:
        handles = [f"{ent_by_id[i].get('platform')}/{ent_by_id[i].get('value')}"
                   for i in (c.get("entity_ids") or []) if i in ent_by_id][:3]
        lines.append(f"  - {', '.join(handles)}")

    # discovered identifiers
    emails, phones, upis, photos = set(), set(), set(), 0
    for e in entities:
        m = e.get("metadata") or {}
        if e.get("type") == "email" or (m.get("email")):
            emails.add(m.get("email") or e.get("value"))
        if e.get("type") == "phone" or m.get("phone"):
            phones.add(m.get("phone") or e.get("value"))
        if e.get("type") == "upi":
            upis.add(e.get("value"))
        if m.get("photo_url") or m.get("avatar"):
            photos += 1
    lines.append("\nIdentifiers discovered:")
    lines.append(f"  emails: {', '.join(list(emails)[:5]) or '(none)'}")
    lines.append(f"  phones: {', '.join(list(phones)[:5]) or '(none)'}")
    lines.append(f"  upi: {', '.join(list(upis)[:5]) or '(none)'}")
    lines.append(f"  profiles with a photo: {photos}")
    lines.append(f"  total accounts: {len([e for e in entities if e.get('type') in (None, 'social_account')])}")

    lines.append("\nDeterministic baseline actions already generated (refine/re-rank these, "
                 "add anything better, keep the best 5):")
    for a in det:
        lines.append(f"  - [{a['priority']}] {a['title']} — {a['detail']}")
    return "\n".join(lines)


def recommend(case: dict, entities: list[dict], clusters: list[dict],
              llm=None, use_cache: bool = True) -> list[dict]:
    """Return a ranked list of next-action dicts for the officer. Never raises."""
    case_id = case.get("case_id")
    state_key = (len(entities), len(clusters),
                 sum(1 for c in clusters if len(c.get("entity_ids") or []) > 1))
    if use_cache and case_id and case_id in _CACHE and _CACHE[case_id][0] == state_key:
        return _CACHE[case_id][1]

    det = deterministic_actions(case, entities, clusters)

    result = det
    try:
        if llm is None:
            from backend.llm.llm_client import LLMClient
            llm = LLMClient()
        from backend import config
        digest = _build_digest(case, entities, clusters, det)
        content = llm._chat_with_failover(
            config.LLM_EXTRACT_MODEL,
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": ("CASE DIGEST:\n" + digest)[:4000]}],
            temperature=0.2, max_tokens=700,
        )
        content = (content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content[4:] if content.startswith("json") else content
        start, end = content.find("["), content.rfind("]")
        if start >= 0 and end > start:
            data = json.loads(content[start:end + 1])
            llm_actions = [a for a in (_norm_action(x) for x in data) if a]
            if llm_actions:
                # Merge: LLM's ranking leads, but keep any deterministic action it dropped as
                # a safety net so we never lose a concrete, verified lead.
                result = _dedupe(llm_actions + det, MAX_ACTIONS)
    except Exception:  # noqa: BLE001 — LLM optional; deterministic baseline stands.
        result = _dedupe(det, MAX_ACTIONS)

    result = _dedupe(result, MAX_ACTIONS)
    if case_id:
        _CACHE[case_id] = (state_key, result)
    return result
