# Agentic Browser — Corrected Architecture (design, not yet built)

Fixes the six problems in the first draft plan: weak anti-bot, unclear pipeline
integration, wrong model keys, redundant WhatsMyName template, no determinism/caching,
missing ops (timeouts/cleanup/concurrency/failure-UX). Design only — build after chat switch.

---

## 0. Model strategy (uses your FREE keys, each where it's strongest)

| Job | Model | Why |
|---|---|---|
| Navigation / vision (agent loop) | **Gemini `gemini-3.1-flash-lite`** (Google AI Studio free tier) | Only free key that is fast AND vision-capable; browser agents need screenshots. |
| Page → structured JSON (extraction) | **Groq** (existing key, via `LLMClient`) | Fast text model, no vision needed here; keeps Gemini quota for navigation. |
| Agent loop | **NEVER NVIDIA** | ~80s/call on this network → an agent (many calls/task) never finishes. |

`config.py` holds `AGENT_MODEL` (Gemini) + reuses the existing `LLMClient` (Groq-primary)
for extraction. Add `GEMINI_API_KEY` to `.env`. Fail-safe: if Gemini key missing, the
recorded-flow layer (§2) still works with zero LLM calls.

---

## 1. Design principles (the fixes)

1. **Determinism-first, agent-as-fallback.** Curated sites run as *recorded deterministic
   flows* (zero LLM calls) → fast, reliable, cheap. The LLM agent only fires for the
   Custom-URL case or when a recorded flow drifts/breaks. (Fixes: speed, cost, flakiness.)
2. **Output flows THROUGH the reasoning layer, never beside it.** Extracted profiles are
   converted to `RawProfile` and pushed through the EXISTING dedup → exact-match flag →
   `correlate()` → `score()` → persist path, so they're linked/scored with the rest. They
   are NOT inserted as standalone island entities. (Fixes: the integration gap.)
3. **Total isolation.** Everything lives in `backend/agentic_browser/`; the only touch
   points to existing code are (a) one new orchestrator seam `ingest_external_profiles()`,
   (b) router registration in `main.py`, (c) the add-investigation form.
4. **Honest failure.** Anti-bot WILL sometimes win. Every task has a hard timeout and a
   clean terminal `blocked` state — never a hang or an infinite CAPTCHA loop.

---

## 2. Execution modes

### Mode A — Recorded flow (curated sites: SocialSearcher, Inflact, …)
A per-site *recipe* in `recipes.py`: deterministic Playwright steps
(`goto(template_url.format(query))` → `wait_for_selector` → extract via selectors) authored
& verified once. Runs with **zero LLM calls**. This is what the demo uses → fast + reliable.
If a recipe fails (selector drift), fall back to Mode B and (optionally) auto-refresh the
recipe.

### Mode B — Live agent (Custom URL, or recipe fallback)
`agent.py` wraps **browser-use** (Gemini Flash) — or **Playwright MCP** (accessibility-tree,
no vision) — given a natural-language task ("go to {url}, search {query}, extract the profile
card as JSON"). Slower (30–90s), used only when there's no recipe or a recipe broke.

---

## 3. Anti-bot — tiered + honest (hackathon-realistic, no paid proxies)

`stealth.py` builds the browser context. Do NOT rely on `--disable-blink-features` + UA
spoofing alone (2019-era; Cloudflare/Turnstile defeat it). Instead classify each target:

- **Tier 0 — open** (SocialSearcher, most public pages): patched stealth Playwright is enough.
- **Tier 1 — light detection**: use a real stealth engine — **patchright** / **rebrowser-
  playwright** (drop-in Playwright patches) or **nodriver** / **camoufox** (highest OSS
  stealth) — plus realistic headers + human-like delays. Usually passes.
- **Tier 2 — Cloudflare/Turnstile** (Inflact likely): without residential proxies + a solver,
  this is **best-effort**. Strategy: attempt once with the strongest stealth engine; if a
  challenge is detected, DON'T loop — either (a) return terminal `blocked`, or (b)
  **human-in-the-loop**: open headed, the investigator solves the Turnstile ONCE, the agent
  reuses the session cookies. (b) is a legitimate analyst-assisted pattern and a good demo
  safety net.

Turnstile is a background JS/browser-integrity challenge — "AI vision clicks the checkbox"
does NOT solve it. Vision is only for cookie/consent banners. Frame the feature to judges as
"interactive web-tool automation," not "Cloudflare bypass."

---

## 4. Pipeline integration (the critical fix)

An agentic lookup **augments a case** (or creates one). Flow:

```
ExtractedWebProfile (pydantic, validated)
   -> make_profile(type, value, platform, source_url, metadata, data_mode="agentic_web")
   -> add to the case's profile pool (existing entities + new)
   -> orchestrator.ingest_external_profiles(case_id, new_profiles):
        _dedup -> flag exact_seed_match (REUSE existing logic vs original_seed_values)
        -> (light enrich) -> correlate(all_profiles) -> score() -> persist entities+clusters
```

- `RawProfile.data_mode` already exists (`"live" | "mock"`) → add `"agentic_web"`; no schema
  change. `source_url` already exists.
- The queried profile is an exact match by construction → it inherits the existing
  `metadata.exact_seed_match` flag + the 🎯 pin + ★ badge automatically. Do NOT reinvent it.
- **New seam to add:** `backend/pipeline/orchestrator.py :: ingest_external_profiles(case_id,
  profiles)` — re-runs dedup/correlate/score over (existing case entities ∪ new) and
  re-persists clusters. `service.py` calls THIS (not a raw INSERT).

---

## 5. Package layout (revised)

```
backend/agentic_browser/
  __init__.py
  config.py     # Gemini(agent)+Groq(extract) selection, timeouts, concurrency cap, tier map
  stealth.py    # stealth/patched browser-context factory; headed/human-assist toggle
  schemas.py    # pydantic: WebToolTarget, AgenticLookupRequest, AgenticTaskStatus, ExtractedWebProfile
  recipes.py    # deterministic per-site flows + registry (SocialSearcher, Inflact); Mode A
  agent.py      # live LLM agent (browser-use / Playwright MCP); Mode B (custom URL + fallback)
  extract.py    # page text/DOM -> ExtractedWebProfile via Groq JSON, pydantic-validated
  service.py    # async task mgr + live logs; calls orchestrator.ingest_external_profiles()
  api.py        # GET /tools, POST /run, GET /status/{task_id}
```
Touches outside the package: `main.py` (register router), `orchestrator.py`
(`ingest_external_profiles` seam), `frontend/app/cases/page.js` (add-investigation option).

---

## 6. Async job + ops (were missing)

- **Concurrency cap:** global semaphore, max 1–2 live browsers (each is 100s of MB → OOM risk).
- **Hard timeout:** per-task wall-clock (e.g. 90s) with guaranteed `context.close()` in
  `finally`; kill orphan chromium on shutdown.
- **Status lifecycle** (polled by UI): `queued → launching → navigating → solving → extracting
  → correlating → complete | blocked | failed(reason)`. Live step logs via existing
  `log_action` so the current live-feed UI renders them.

---

## 7. Curated templates (WhatsMyName DROPPED)

- **SocialSearcher** — Tier 0, public mention search, no key. **Best flagship for a reliable
  live demo.**
- **Inflact** — Tier 2, best-effort / human-assisted (don't stake the demo on it).
- **Custom URL + NL instruction** — Mode B; the real differentiator (any no-API site).
- ~~WhatsMyName~~ — **removed**: redundant with Maigret/Sherlock, which already do
  cross-platform username enumeration deterministically and better.

---

## 8. Frontend (add-investigation)

`frontend/app/cases/page.js`: add a mode toggle **"🤖 Agentic Web"** next to the seed-type
dropdown → reveals **query** + **target** (dropdown of curated tools + "Custom URL" with an
instruction field). Live progress indicators driven by the status lifecycle (§6). On
`blocked`, show a clean "site blocked automated access" state, not a spinner.

---

## 9. Testing (`tests/test_agentic_browser.py`)

Fully mocked (no live sites, no real LLM in CI):
- `ExtractedWebProfile` validation + conversion → `RawProfile`.
- Recipe returns canned HTML → extraction → `ingest_external_profiles` → asserts the entity
  is persisted, `exact_seed_match` set, and it appears in a cluster (went THROUGH correlation).
- Task lifecycle `queued → running → complete` and the `blocked`/timeout paths.

---

## 10. Demo plan
Flagship = **SocialSearcher** (Tier 0, reliable live). Show **Inflact** as best-effort /
analyst-assisted so a CAPTCHA can't tank the demo. Show **Custom URL** on a simple public
site to prove generality.

---

## Open decision for the build chat
- **Augment an existing investigation** vs **create a new case** for an agentic lookup — the
  design supports augment as primary (more useful); confirm before building `service.py`.
