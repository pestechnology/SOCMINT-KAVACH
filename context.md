# Project Context — VERTEX
> Last updated by: Claude Opus 4.8 (1M context). Read this entire file before touching any code.

---

# 1. PROJECT OVERVIEW

## What is this project?
**VERTEX** is a **SOCMINT / OSINT suspect-profiling system**. An investigator types in **one** thing they know about a suspect — a username, email, phone number, UPI ID, full name, or face-photo URL — and VERTEX:
1. Scrapes publicly available data from across the internet for that identifier,
2. Works out which of the accounts/traces it finds actually belong to the **same person** (vs. strangers who merely share a username string),
3. Draws a connection map and confidence-rated clusters,
4. Produces a **court-admissible evidence PDF** under India's **Bharatiya Sakshya Adhiniyam (BSA) 2023, Section 63**, with a tamper-evident SHA-256 hash chain.

The one-line pitch: **"One identifier in. A complete, court-admissible digital profile out."**

## The hackathon goal
Built for **CIDECODE 2026** (CCITR + CID Karnataka, PES University, July 4–5, 2026). The problem statement: *"Design and develop a Social Media Intelligence (SOCMINT) based system that enables the lawful collection, correlation, and analysis of publicly available social media and OSINT data to identify and link multiple online accounts belonging to the same individual."*

The audience is **law enforcement (CID Karnataka)**. The winning strategy is **defensibility, not volume**: the two features that win this for this audience are (a) **red-herring rejection** — refusing to link accounts on weak evidence, and (b) the **BSA-63 court PDF with independently verifiable hashes**. Both work today and neither depends on the live network.

## What has been built vs. what is left
- ✅ **Entire backend** — config, DB, auth, cases, data-source layer, mock scraper, correlation + scoring engine, LLM client with fallbacks, orchestrator, audit ledger, BSA-63 PDF generator. All gate-tested.
- ✅ **Live scrapers**: GitHub (verified live), Serper, HIBP, Maigret, UPI parser, phone (ignorant + PhoneInfoga). All fail-safe.
- ✅ **Frontend** — Next.js + Tailwind: login, case list, new-investigation form, 3-panel results dashboard (sigma.js graph + vis-timeline), streaming via polling, PDF download. `npm run build` passes.
- ✅ **Test suite** — 44 pytest tests, all passing.
- ✅ **Legal verification** — all BSA-63 claims checked (see `LEGAL_VERIFICATION.md`).
- 🔧 **Live scraper verification** — only GitHub has been exercised live; Maigret/Serper/HIBP/phone need real keys + installed CLIs on the demo machine.
- ❌ **Remaining scrapers** (optional breadth): Blackbird, socialscan, Reddit JSON, Telethon, Wayback CDX, pHash face matcher, Playwright-based Facebook/UPI-name lookups.
- ❌ **Rate limiting**, SSE/WebSocket true streaming, retry-with-backoff.

## Tech stack — every tool and WHY

### Backend (Python 3.10)
- **FastAPI 0.115.6** — async web framework. Chosen for native async (parallel scraper fan-out via `asyncio.gather`), automatic OpenAPI docs at `/docs`, and Pydantic request validation.
- **uvicorn 0.34.0** — ASGI server that runs FastAPI.
- **SQLite (stdlib `sqlite3`, NO ORM)** — single-file DB, zero setup, resettable by deleting the file. Chosen because the demo runs on one laptop; an ORM would add complexity with no benefit at this scale.
- **httpx 0.28.1** — async HTTP client for all external API calls (GitHub, Serper, HIBP, NVIDIA, PhoneInfoga). Chosen over `requests` because it supports `AsyncClient` (required so scrapers truly run in parallel).
- **python-jose[cryptography] 3.3.0** — JWT encode/decode for auth tokens (HS256).
- **bcrypt 4.2.1** — password hashing.
- **reportlab 4.2.5** — generates the BSA-63 PDF. Chosen because it gives precise control over layout (page headers/footers, certificate tables) needed to look like an official court document.
- **thefuzz + python-Levenshtein** (optional) — fuzzy username matching in correlation. Degrades to stdlib `difflib` if absent.
- **scikit-learn** (optional) — TF-IDF cosine for stylometry signal. Degrades gracefully if absent.
- **imagehash + pillow** (optional) — perceptual-hash photo matching. Degrades to URL-equality if absent.
- **maigret** (CLI, installed separately) — primary username scraper across 3000+ sites.
- **python-dotenv** — loads `.env`.

### Frontend
- **Next.js 14.2.15 (App Router) + React 18** — the spec called for Next.js; App Router with client components.
- **Tailwind CSS 3.4** — dark professional theme, utility classes.
- **sigma.js 3 + graphology + graphology-layout-forceatlas2** — the network/connection graph (the "moat visual").
- **vis-timeline 7.7 + vis-data** — cross-platform posting timeline strip.

### External services (all optional, all fail-safe)
- **Serper.dev** — Google search backbone (dorks).
- **GitHub REST API** — username/email → profile.
- **NVIDIA Cloud LLM** (`meta/llama-3.3-70b-instruct`, `deepseek-ai/deepseek-v4-pro`) — entity extraction + plain-English explanations. **Enhancement-only**, never decides linking, always has a deterministic fallback.
- **HIBP (Have I Been Pwned)** — email → breach list.
- **Telegram (Telethon)**, **NumVerify** — wired in config but scrapers not all built.

## High-level architecture (plain English)
VERTEX is a **pipeline**. A request enters through FastAPI. Auth and case-ownership are checked. When an investigation starts, the **orchestrator** looks up which scrapers apply to each seed type (the `SEED_TOOL_MAP`), runs them all in parallel, and each scraper returns a list of `RawProfile` objects through one shared interface (`BaseDataSource.resolve`). Every scraper is **fail-safe**: on any error it returns `[]` so one broken tool never stops the run. The combined profiles are de-duplicated and saved to the `entities` table. The **correlation engine** compares every profile pair and records which "signals" fired (shared phone, same photo, similar username, etc.). The **scoring engine** turns those signals into clusters with a confidence score (0–100) and a tier (HIGH/MEDIUM/LOW/REJECT), applying the **red-herring rule** (a single signal can never link accounts). Clusters are saved and given a plain-English explanation (LLM if available, deterministic template otherwise). Throughout, every step is written to an append-only **audit ledger** as a SHA-256 hash chain. Finally, the **BSA-63 PDF generator** reads the case, clusters, ledger, and artifacts and produces a court-ready evidence document whose hashes anyone can independently recompute. The **frontend** polls the results endpoint while the investigation runs, streaming accounts onto the screen and rendering the connection graph.

---

# 2. FOLDER & FILE STRUCTURE

```
/cidecode
  context.md                         → THIS FILE — single source of truth
  LEGAL_VERIFICATION.md              → [CRITICAL] all BSA-63 legal claims verified vs primary sources
  SETUP.md                           → how to install + run backend and frontend
  VERTEX_Master_Architecture (1).md  → original design spec (the blueprint)
  VERTEX_status_and_plan.md          → original progress snapshot / day-by-day plan
  requirements.txt                   → [CONFIG] Python dependencies (pinned versions)
  .env.example                       → [CONFIG] template for secrets; copy to .env (gitignored)
  .gitignore                         → ignores .env, *.db, node_modules, reports/, etc.
  cidecode.db                        → [GENERATED] SQLite database (gitignored)

  /backend                           → all Python backend code
    __init__.py
    config.py                        → [CONFIG][CRITICAL] loads all env vars; validate_keys() warns, never crashes
    main.py                          → [ENTRY POINT] FastAPI app; lifespan init_db; CORS; /health; wires routers
    /database
      __init__.py                    → [CRITICAL] init_db() (6 tables + WAL), get_db() (connection w/ busy_timeout)
    /auth                            → JWT + bcrypt authentication
      auth_service.py                → register_user, authenticate, create_token, decode_token
      auth_middleware.py             → get_current_user FastAPI dependency (Bearer → user_id, else 401)
      auth_routes.py                 → [ENTRY POINT] POST /auth/register, POST /auth/login, GET /auth/me
    /cases                           → case CRUD + access control
      case_service.py                → create_case, get_case, list_cases, set_status, get_results, VALID_SEED_TYPES
      case_routes.py                 → [ENTRY POINT] /cases routes; triggers orchestrator as background task
    /ingestion                       → the data-source layer (scrapers)
      base_module.py                 → [CRITICAL] RawProfile dataclass, BaseDataSource (fail-safe resolve), make_profile, _hash
      mock_scraper.py                → MockScraper — fixed dev data (same-person trio + 1 red herring)
      github_scraper.py              → GitHubScraper — GitHub REST API (live-verified)
      serper_scraper.py              → SerperScraper — Google search via Serper.dev (template per seed type)
      hibp_scraper.py                → HIBPScraper — Have I Been Pwned breach lookup
      maigret_scraper.py             → MaigretScraper — runs the maigret CLI (primary username scraper)
      upi_module.py                  → UPIScraper + parse_upi + UPI_BANK_MAP (India-specific differentiator)
      phone_scrapers.py              → IgnorantScraper, PhoneInfogaScraper (fail-safe if tools absent)
    /correlation
      correlation_engine.py          → [CRITICAL] correlate(), CandidatePair, SIGNAL_WEIGHTS, signal computation
    /scoring
      scoring_engine.py              → [CRITICAL] score(), Cluster, tier thresholds, RED-HERRING rule, union-find clustering
    /llm
      llm_client.py                  → LLMClient (NVIDIA); extract_entities/explain_match/summarize_case; all with fallbacks
    /pipeline
      orchestrator.py                → [CRITICAL][ENTRY POINT] run_investigation / run_investigation_sync; SEED_TOOL_MAP
    /ledger
      audit_ledger.py                → [CRITICAL] log_action, save_artifact, verify_chain (hash chain), get_ledger, get_artifacts
    /report
      bsa63_generator.py             → [CRITICAL] generate_report() → court PDF; _esc() XML-escaping; _NumberedCanvas

  /scripts
    create_admin.py                  → create/reset an admin user (default admin / vertex2026)
    seed_demo_case.py                → build a full demo case from mock data (for testing PDF + frontend)

  /tests                             → pytest suite (44 tests, all passing)
    conftest.py                      → [CRITICAL] sets temp DB + DATA_MODE=mock BEFORE importing backend; fixtures
    test_scoring.py                  → unit: scoring, tiers, red-herring, union-find, edge cases
    test_ledger.py                   → unit/integration: hash chain, tamper detection, artifact hashing
    test_api.py                      → integration/E2E/security: auth, access control, SQL-injection
    test_report_and_pipeline.py      → integration: orchestrator, idempotency, PDF, XML-special-char regression, UPI cascade
    test_units_resilience.py         → unit: UPI parser, LLM fallbacks, scraper fail-safe, config

  /frontend                          → Next.js app
    package.json                     → [CONFIG] deps + scripts (dev/build/start)
    next.config.mjs                  → Next config (reactStrictMode)
    tailwind.config.js               → [CONFIG] Tailwind theme (custom dark colors: ink/panel/accent/good/warn/bad)
    postcss.config.js                → Tailwind/autoprefixer
    jsconfig.json                    → @/* path alias → project root
    .env.local.example               → [CONFIG] NEXT_PUBLIC_API_URL template
    /lib
      api.js                         → [CRITICAL] API client; token in localStorage; all backend calls
    /components
      Graph.js                       → sigma.js network graph (client-only, dynamic import)
      Timeline.js                    → vis-timeline strip (client-only, dynamic import)
    /app
      layout.js                      → root layout + globals.css
      globals.css                    → Tailwind directives + component classes (.card/.btn/.input/.badge)
      page.js                        → [ENTRY POINT] redirects to /login or /cases based on token
      /login/page.js                 → login + register screen
      /cases/page.js                 → case list (home) + "New investigation" modal
      /cases/[id]/page.js            → [CRITICAL] results dashboard (3-panel, polling, report download)
```

---

# 3. EVERY DATA FLOW — END TO END

## Flow A — Registration
- **Starts:** user submits the register form on `/login` (frontend), or `POST /auth/register`.
- **First receiver:** `register()` in `backend/auth/auth_routes.py`, body validated by Pydantic model `Credentials {username: str, password: str}`.
- **Steps:** calls `register_user(username, password)` in `auth_service.py` → strips username, enforces **username ≥3 chars and password ≥6 chars** (raises `ValueError` otherwise) → checks `users` table for existing username (raises `ValueError("username already exists")`) → bcrypt-hashes the password → inserts a row into `users` with a `uuid4().hex` `user_id` and role `'investigator'` → returns `user_id`. Route then calls `create_token(user_id)`.
- **Output:** `{"user_id": "...", "token": "<jwt>"}` (HTTP 200).
- **Side effects:** new `users` row; JWT minted (8h expiry).
- **Errors:** duplicate or too-short → `ValueError` → HTTP **409** (handler in route maps `ValueError` to 409).

## Flow B — Login
- **Starts:** `POST /auth/login`, body `Credentials`.
- **First receiver:** `login()` in `auth_routes.py`.
- **Steps:** `authenticate(username, password)` → fetches user row → `bcrypt.checkpw`. If valid returns `{user_id, username, role}`, else `None`.
- **Output (success):** `{"token": "<jwt>", "user": {user_id, username, role}}`.
- **Errors:** bad credentials → `authenticate` returns `None` → HTTP **401** "Invalid credentials".

## Flow C — Authenticated request (every protected route)
- **Starts:** any `/cases/*` or `/auth/me` call with header `Authorization: Bearer <jwt>`.
- **First receiver:** `get_current_user()` in `auth_middleware.py` (FastAPI `Depends`).
- **Steps:** checks header starts with `"bearer "` (case-insensitive) → extracts token → `decode_token()` (jose verifies signature + expiry) → returns `user_id`.
- **Errors:** missing/malformed header → **401** "Missing or malformed Authorization header"; invalid/expired token → **401** "Invalid or expired token".
> **GOTCHA:** A plain browser `<a href>` navigation cannot send the `Authorization` header. This is why report download uses `api.downloadReport()` (fetch + blob), NOT a link. See Flow G.

## Flow D — Create case + start investigation
- **Starts:** `POST /cases` (frontend "Start investigation" button), body `NewCase {title: str, seeds: [{type, value}], minor_involved: bool}`.
- **First receiver:** `create()` in `case_routes.py`, requires `get_current_user`.
- **Steps:** `create_case(user_id, title, seeds, minor_involved)` in `case_service.py` → validates each seed `type` against `VALID_SEED_TYPES = {name, email, phone, username, upi, face}` and non-empty value (raises `ValueError` → HTTP 400) → inserts a `cases` row with `uuid4().hex` `case_id`, `seeds_json` (JSON string), status `'pending'`. Then the route adds a **FastAPI BackgroundTask** calling `run_investigation_sync(case_id)` (imported lazily; if the orchestrator import fails the case is still created).
- **Output:** `{"case_id": "..."}` immediately (HTTP 200). The investigation runs in the background.
- **Side effects:** new `cases` row; background investigation kicked off.

## Flow E — The investigation pipeline (the core)
- **Starts:** `run_investigation_sync(case_id)` (background thread) → wraps `asyncio.run(run_investigation(case_id))`. On any exception it sets status `'error'` and logs `investigation_error`.
- **Steps (in `orchestrator.run_investigation`):**
  1. Loads the case; reads `seeds_json`. Sets status `'running'`.
  2. **Idempotency:** `DELETE FROM entities` and `DELETE FROM clusters` for this case (re-runs don't duplicate). The `audit_ledger` is intentionally NOT cleared (append-only).
  3. Logs `investigation_started`.
  4. Builds `tool_map = _seed_tool_map()`. In `DATA_MODE="mock"` every seed type maps to `[MockScraper()]` (+ `UPIScraper` for upi). In `"live"` each type maps to its real scrapers.
  5. For each seed: `_scrape_seed(type, value, tool_map)` → builds one coroutine per applicable scraper → `asyncio.gather(..., return_exceptions=True)` → flattens only successful list results. Logs `scrape:{type}` with the count.
  6. **UPI cascade:** any returned `RawProfile` with `platform=="derived"` and `metadata["cascade"]` (e.g. the username portion of a UPI) is itself scraped. Logs `cascade:{type}`.
  7. **LLM entity extraction:** collects bio/snippet text blobs (cap 10), runs `LLMClient.extract_entities` on each (regex fallback if no key), collects new username/email seeds.
  8. **Bio-link expansion:** runs scrapers on those new seeds, skipping ones already searched, **capped at 5**. Logs `expand:{type}`.
  9. **Dedup:** `_dedup()` removes profiles with the same `(platform, value, source_url)`.
  10. **Persist entities:** inserts each `RawProfile` into `entities` (streaming write so the frontend can poll progress). Remembers `index → entity_id`.
  11. **Artifact:** dumps all profiles as JSON, `save_artifact()` writes it to disk + hashes it.
  12. **Correlate + score:** `correlate(profiles)` → list of `CandidatePair`; `score(profiles, pairs)` → list of `Cluster`. Logs `scoring_complete`.
  13. **Persist clusters:** inserts each cluster into `clusters`; for multi-member clusters generates a plain-English explanation via `LLMClient.explain_match` (template fallback); writes each member's `confidence_score` back onto its `entities` row.
  14. Sets status `'complete'`; logs `investigation_complete`.
- **Output:** `{"status": "complete", "accounts": N, "clusters": M}`.
- **Side effects:** rows in `entities`, `clusters`, `audit_ledger`, `artifacts`; a JSON artifact file on disk.
- **What can go wrong / handling:** any single scraper error → caught by `BaseDataSource.resolve` → `[]`. LLM down → fallback. Whole-run exception → status `'error'` + ledger entry. DB locked → WAL + 10s busy_timeout.

## Flow F — Polling results (streaming UX)
- **Starts:** the results page `/cases/[id]` mounts and calls `api.getResults(id)` → `GET /cases/{id}/results`.
- **First receiver:** `results()` in `case_routes.py` → `get_results(case_id, user_id)` (access-controlled).
- **Steps:** `get_case` confirms ownership (else `None` → 404) → reads `entities` + `clusters`, parses `metadata_json`/`entity_ids_json`/`signals_json` into objects.
- **Output:** `{case, entities[], clusters[], status}`.
- **Frontend behavior:** while `status` is `running`/`pending`, a `setInterval` re-fetches every **1.5s**, streaming accounts into the left panel and growing the graph; stops when `complete`/`error`.

## Flow G — Generate evidence report (PDF)
- **Starts:** "Generate evidence report" button → `api.downloadReport(id)` does `fetch(/cases/{id}/report, {Authorization: Bearer})` and downloads the response as a Blob.
- **First receiver:** `report()` in `case_routes.py` → ownership check (404 if not owner) → `generate_report(case_id)` → returns `FileResponse(pdf, media_type="application/pdf")`.
- **Steps (in `bsa63_generator.generate_report`):** loads case/entities/clusters/user → builds the PDF with sections: Cover → 1. Search Manifest (from ledger) → 2. Findings Summary (clusters) → Annexure A (artifacts + SHA-256) → Certificate Part A → Certificate Part B (hashes) → 3. Chain of Custody (`verify_chain` result) → Document Integrity Statement. Every dynamic string passes through `_esc()` (XML-escape). If `case.minor_involved`, identifying values are replaced with `REDACTED`. A `_NumberedCanvas` draws the header band + "Page X of Y" footer.
- **Output:** a multi-page PDF downloaded as `BSA63_report_{case_id}.pdf`.
- **Side effects:** writes the PDF to `REPORT_OUTPUT_DIR`.
> **GOTCHA (fixed):** Before the fix, a title/seed containing `&` or `<` crashed PDF generation (reportlab parses Paragraph text as XML). `_esc()` now escapes all dynamic content. Do not insert raw user/scraped strings into a `Paragraph` without `_esc()`.

## Flow H — Audit ledger hash chain
- **Starts:** `log_action(case_id, action, input_data, output_data, actor)` called at each pipeline step.
- **Steps:** computes `input_hash = SHA256(json(input_data))`, `output_hash = SHA256(json(output_data))`, `previous_hash =` the recomputed chain value of the most recent row for this case (`"GENESIS"` for the first). Inserts the row. The chain value of a row is `SHA256(previous_hash | input_hash | output_hash | action | actor | timestamp)`.
- **Verification:** `verify_chain(case_id)` walks rows in insertion order, recomputes each link, and confirms each row's stored `previous_hash` equals the prior row's recomputed chain value. Returns `(bool, detail)`.
- **Tamper detection:** editing any recorded field changes that row's chain value, so the next row's `previous_hash` no longer matches → returns `(False, "Chain broken at row N ...")`.

---

# 4. ALL API ENDPOINTS / INTERFACES

> Base URL in dev: `http://localhost:8000`. All bodies are JSON. Auth is `Authorization: Bearer <jwt>`.

### GET /health
- **Does:** liveness probe.
- **Request:** none. **Auth:** no.
- **Response:** `{"status": "ok", "data_mode": "live" | "mock"}`.

### POST /auth/register
- **Does:** create a new user and return a token.
- **Request:** `{"username": str (required, ≥3 chars), "password": str (required, ≥6 chars)}`.
- **Response (200):** `{"user_id": str, "token": str}`.
- **Errors:** **409** if username exists or username/password too short (`ValueError`). **422** if fields missing (Pydantic).
- **Auth:** no.

### POST /auth/login
- **Does:** authenticate and return a token.
- **Request:** `{"username": str, "password": str}`.
- **Response (200):** `{"token": str, "user": {"user_id": str, "username": str, "role": str}}`.
- **Errors:** **401** "Invalid credentials".
- **Auth:** no.

### GET /auth/me
- **Does:** return the caller's user_id (token check).
- **Response (200):** `{"user_id": str}`.
- **Errors:** **401** invalid/missing token.
- **Auth:** yes.

### POST /cases
- **Does:** create a case and start the investigation in the background.
- **Request:** `{"title": str, "seeds": [{"type": str, "value": str}], "minor_involved": bool (default false)}`. `type` ∈ {name, email, phone, username, upi, face}.
- **Response (200):** `{"case_id": str}`.
- **Errors:** **400** invalid seed type / empty value; **401** no auth.
- **Auth:** yes. **Side effect:** background `run_investigation_sync`.

### GET /cases
- **Does:** list the caller's cases (newest first), each with an `account_count`.
- **Response (200):** `{"cases": [{case_id, user_id, title, seeds_json, seeds[], minor_involved, status, created_at, updated_at, account_count}]}`.
- **Auth:** yes.

### GET /cases/{case_id}
- **Does:** fetch one case (owner only).
- **Response (200):** the case dict (incl. parsed `seeds`).
- **Errors:** **404** if not found or not owned by caller (ownership and existence are deliberately indistinguishable).
- **Auth:** yes.

### GET /cases/{case_id}/results
- **Does:** return entities + clusters for the dashboard.
- **Response (200):** `{"case": {...}, "entities": [...], "clusters": [...], "status": str}`. Each entity has `metadata` (parsed); each cluster has `entity_ids[]` and `signals{}` (parsed).
- **Errors:** **404** if not owned.
- **Auth:** yes.

### GET /cases/{case_id}/report
- **Does:** generate + return the BSA-63 PDF.
- **Response (200):** `application/pdf` file stream (`BSA63_report_{case_id}.pdf`).
- **Errors:** **404** if not owned.
- **Auth:** yes. **Side effect:** writes the PDF to disk.

## Frontend API client (`frontend/lib/api.js`)
- `getToken()/setToken(t)/clearToken()` — JWT in `localStorage` key `vertex_token`.
- `api.register(username, password)`, `api.login(username, password)`.
- `api.listCases()`, `api.createCase(title, seeds, minor_involved=false)`, `api.getCase(id)`, `api.getResults(id)`.
- `api.reportUrl(id)` — raw URL (not used for download). `api.downloadReport(id)` — fetches the PDF **with** the auth header and returns a Blob.
- Base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Core internal interfaces
- **`BaseDataSource.resolve(identifier: str, data_mode: str = "live") -> list[RawProfile]`** — every scraper implements this. **Never raises** (returns `[]` on error). Routes to `_run_live` or `_run_mock`.
- **`correlate(profiles: list[RawProfile]) -> list[CandidatePair]`** — pairwise signal computation.
- **`score(profiles, pairs) -> list[Cluster]`** — clustering + tiers + red-herring rule.
- **`generate_report(case_id, output_path=None) -> str`** — returns PDF path.
- **`log_action(case_id, action, input_data, output_data, actor) -> ledger_id`**, **`verify_chain(case_id) -> (bool, str)`**, **`save_artifact(case_id, entity_id, artifact_type, content, suffix) -> dict`**.

---

# 5. DATABASE / DATA MODELS

SQLite, file at `DB_PATH` (default `cidecode.db`). **WAL journal mode** + `busy_timeout=10000ms`. `PRAGMA foreign_keys = ON`. Created idempotently by `init_db()` in `backend/database/__init__.py`.

### Table `users`
```
user_id       TEXT PRIMARY KEY     -- uuid4().hex
username      TEXT UNIQUE NOT NULL
password_hash TEXT NOT NULL        -- bcrypt hash (never plaintext)
role          TEXT DEFAULT 'investigator'  -- 'investigator' | 'admin' (label only; NOT used to gate any feature)
created_at    TEXT                 -- ISO8601 UTC
```

### Table `cases`
```
case_id        TEXT PRIMARY KEY    -- uuid4().hex
user_id        TEXT NOT NULL       -- FK -> users.user_id (owner)
title          TEXT NOT NULL
seeds_json     TEXT NOT NULL       -- JSON string, e.g. [{"type":"upi","value":"x@oksbi"}]
minor_involved INTEGER DEFAULT 0   -- 1 triggers POCSO/JJ redaction in the PDF
status         TEXT DEFAULT 'pending'  -- 'pending' | 'running' | 'complete' | 'error'
created_at     TEXT
updated_at     TEXT
```

### Table `entities` (one row per discovered account/trace)
```
entity_id     TEXT PRIMARY KEY     -- uuid4().hex
case_id       TEXT NOT NULL        -- FK -> cases.case_id
type          TEXT                 -- social_account|email|phone|username|upi|breach|web_mention|phone_intel|...
value         TEXT                 -- the identifier/handle
platform      TEXT                 -- github|instagram|hibp|upi|derived|...
confidence    REAL                 -- cluster confidence written back after scoring (nullable)
metadata_json TEXT                 -- JSON: fullname, bio, photo_url, phone, posting_hours, location, etc.
source_url    TEXT
data_mode     TEXT                 -- 'live' | 'mock'
sha256        TEXT                 -- SHA256(value:platform:source_url) evidence integrity hash
created_at    TEXT
```

### Table `clusters` (one row per same-person group or singleton)
```
cluster_id       TEXT PRIMARY KEY  -- uuid4().hex
case_id          TEXT NOT NULL     -- FK -> cases.case_id
entity_ids_json  TEXT NOT NULL     -- JSON array of entity_id values in this cluster
confidence_score REAL              -- 0..100 (capped)
tier             TEXT              -- 'HIGH' | 'MEDIUM' | 'LOW' | 'REJECT'
explanation      TEXT              -- plain-English "why these are linked" (LLM or template)
signals_json     TEXT              -- JSON: {signal_name: points}
created_at       TEXT
```

### Table `audit_ledger` (append-only tamper-evident chain)
```
ledger_id     TEXT PRIMARY KEY     -- uuid4().hex
case_id       TEXT
action        TEXT                 -- 'investigation_started','scrape:username','scoring_complete',...
search_id     TEXT                 -- uuid4().hex per entry
input_hash    TEXT                 -- SHA256(json(input_data))
output_hash   TEXT                 -- SHA256(json(output_data))
previous_hash TEXT                 -- chain value of the prior row ('GENESIS' for first)
actor         TEXT                 -- 'system' | username
timestamp     TEXT                 -- ISO8601 UTC
```
> The chain value of a row (used as the next row's `previous_hash`) is NOT stored; it is **recomputed** as `SHA256(previous_hash|input_hash|output_hash|action|actor|timestamp)`. This is intentional so tampering is detectable.

### Table `artifacts`
```
artifact_id   TEXT PRIMARY KEY     -- uuid4().hex
case_id       TEXT
entity_id     TEXT                 -- nullable
artifact_type TEXT                 -- 'json_dump' | 'screenshot' | 'profile_photo'
file_path     TEXT                 -- on disk under REPORT_OUTPUT_DIR/artifacts/{case_id}/
sha256        TEXT                 -- SHA256 of the file content
captured_at   TEXT
```

### Indexes (and why)
```
idx_entities_case  ON entities(case_id)     -- results/report read all entities for a case
idx_entities_value ON entities(value)       -- future cross-case identifier lookups
idx_clusters_case  ON clusters(case_id)     -- results/report read clusters for a case
idx_ledger_case    ON audit_ledger(case_id) -- manifest/chain read ledger for a case
```

### Relationships
`users (1) → (N) cases → (N) entities` and `→ (N) clusters`. `audit_ledger` and `artifacts` reference `case_id` (not enforced as FK to keep them append-only/independent). Clusters reference entities by id stored in `entity_ids_json` (JSON, not a join table).

### Seeded / hardcoded data
- **`scripts/create_admin.py`** creates a user `admin` / `vertex2026` with role `'admin'` (idempotent: resets password if it exists).
- **`scripts/seed_demo_case.py`** builds a complete demo case from mock data (its user has password_hash `"x"` and is NOT loginable — seeding only).
- **`UPI_BANK_MAP`** in `upi_module.py` — hardcoded dict mapping UPI handle suffixes (`oksbi→State Bank of India`, `okhdfcbank→HDFC Bank`, `ybl→PhonePe (Yes Bank)`, etc.).

---

# 6. STATE MANAGEMENT & BUSINESS LOGIC

## Core business logic in plain English
The product answers one question: **"Which of these accounts belong to the same person?"** It deliberately errs on the side of NOT linking. The credibility of the whole system rests on **refusing to over-claim** — that is what a court (and a CID judge) trusts.

## Where state lives
- **Authoritative state:** SQLite (`users`, `cases`, `entities`, `clusters`, `audit_ledger`, `artifacts`).
- **In-memory (transient):** the orchestrator builds `RawProfile`/`CandidatePair`/`Cluster` objects during a run, then persists them.
- **Session:** stateless JWT (no server session store). Frontend keeps the token in `localStorage`.
- **Frontend state:** React component state only (no Redux/Zustand). The results page polls and re-renders.

## The scoring algorithm (step by step) — `correlation_engine.py` + `scoring_engine.py`
1. **Signals & weights** (`SIGNAL_WEIGHTS`): `exact_phone_match`=40, `exact_email_match`=35, `exact_upi_match`=40, `username_exact_match`=30, `username_substring_match`=15, `username_fuzzy_match`=10, `profile_photo_phash`=25, `posting_hours_overlap`=15, `stylometry_cosine`=20, `breach_co_occurrence`=18, `bio_keyword_overlap`=8, `reciprocal_mention`=15.
2. **`correlate()`** compares every pair of profiles and records which signals fired:
   - Phone/email/UPI: normalized exact match (`_phone` keeps last 10 digits).
   - Username: exact → substring (`a in b`) → fuzzy (thefuzz ratio ≥80, else `difflib`). Only the single best tier fires.
   - Photo: `photo_phash` Hamming distance <8 if both present, else `photo_url` equality.
   - Posting hours: Jaccard of `posting_hours` sets > 0.6.
   - Bio keywords: ≥2 shared significant words (stopwords removed).
   - Stylometry: TF-IDF cosine >0.75 (only if scikit-learn installed and bios >15 chars).
   - Breach co-occurrence: shared breach names.
   Returns `CandidatePair(i, j, signals={name: points})`.
3. **`score()`**:
   - **Confidence** = `min(100, sum of distinct signal points within the cluster)`. *(Capping at 100 is intentional: summing all 12 raw weights would make the HIGH threshold unreachable.)*
   - **Tiers** (`_tier`): `>75 HIGH`, `50–75 MEDIUM`, `25–50 LOW`, `<25 REJECT`.
   - **Clustering:** union-find (`_UnionFind`) links two profiles only when a pair between them reaches **MEDIUM** (`raw_points ≥ 50 AND num_signals ≥ 2`).
   - **RED-HERRING RULE (the credibility moment):** if a cluster has only **one** distinct signal, its tier is capped at **LOW** via `_cap_tier`, regardless of that signal's weight. A lone phone or username match is never a link.
   - **Singletons:** unlinked profiles become 1-member clusters carrying their best *attempted* pair score (so the red herring shows as "LOW — not linked" rather than disappearing).
   - **Explanation:** `_explain()` turns fired signals into a sentence ("...share the same registered phone number and have visually identical profile photos."). The orchestrator may replace it with an LLM version for multi-member clusters.

> **Decision tree for tiering a pair/cluster:**
> `num_signals == 0` → REJECT singleton · `num_signals == 1` → capped LOW · `≥2 signals AND points ≥50` → link + tier by score · `≥2 signals AND points <50` → LOW.

## Background jobs / scheduling
- The only "background job" is the investigation, run via **FastAPI `BackgroundTasks`** (in-process thread) when a case is created. There is **no queue, cron, or scheduler**. `run_investigation_sync` wraps `asyncio.run(run_investigation(...))`.

---

# 7. EXTERNAL INTEGRATIONS & SERVICES

### GitHub REST API — `backend/ingestion/github_scraper.py` (`GitHubScraper._run_live`)
- **Used for:** email→user (`/search/users?q={email} in:email`) and username→profile (`/users/{username}`).
- **Creds:** `GITHUB_TOKEN` (optional; raises rate limit to 5000/h). Sent as `Authorization: Bearer` + `User-Agent: VERTEX-OSINT`.
- **Returns:** `RawProfile(platform="github")` with fullname, bio, avatar, location, followers, email.
- **On failure:** non-200 → `[]`. **Verified live** (returns "Linus Torvalds, Portland, OR").

### Serper.dev — `backend/ingestion/serper_scraper.py` (`SerperScraper._run_live`)
- **Used for:** Google dorks per seed type (e.g. `site:linkedin.com/in "{q}"`, `site:truecaller.com "{q}"`, `"{q}"`). Configurable via `query_template`.
- **Creds:** `SERPER_API_KEY` (header `X-API-KEY`). POST to `https://google.serper.dev/search`.
- **Returns:** each organic result → `RawProfile(type="web_mention")` with title, snippet, platform derived from URL host.
- **On failure / no key:** `[]`.

### HIBP — `backend/ingestion/hibp_scraper.py` (`HIBPScraper._run_live`)
- **Used for:** email → breach list. GET `https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=true`.
- **Creds:** `HIBP_API_KEY` (header `hibp-api-key`) **AND** `user-agent` header (both required — missing UA returns 403).
- **Returns:** each breach → `RawProfile(type="breach", platform="hibp")` with `breach_name` and `breaches:[name]`.
- **On failure / no key / 404 (no breaches):** `[]`.

### NVIDIA Cloud LLM — `backend/llm/llm_client.py` (`LLMClient`)
- **Used for (enhancement only):** `extract_entities(text)` (model `LLM_EXTRACT_MODEL` = `meta/llama-3.3-70b-instruct`, temp 0.1), `explain_match(signals, tier)` (model `LLM_EXPLAIN_MODEL` = `deepseek-ai/deepseek-v4-pro`, temp 0.7), `summarize_case(findings)` (temp 0.5).
- **Creds:** `NVIDIA_API_KEY` (Bearer), base `NVIDIA_BASE_URL` = `https://integrate.api.nvidia.com/v1` (OpenAI-compatible `/chat/completions`). 15s timeout.
- **On failure / no key:** **fallbacks** — `extract_entities`→`_regex_entities` (email/phone/UPI regex), `explain_match`→`_template_explanation`, `summarize_case`→`""`. The LLM NEVER decides linking and NEVER blocks the pipeline.

### Maigret (CLI) — `backend/ingestion/maigret_scraper.py` (`MaigretScraper._run_live`)
- **Used for:** primary username scraper. Runs `maigret {username} --json simple --no-recursion --timeout 10 --no-progressbar --folderoutput reports/maigret` via async subprocess.
- **Creds:** none. **Requires** `pip install maigret` (NOT yet installed in this environment).
- **Returns:** only `status=="Claimed"` accounts → `RawProfile` with fullname, bio, photo, etc.
- **On failure / not installed:** `[]` (the orchestrator logs the failure and continues).

### PhoneInfoga + ignorant — `backend/ingestion/phone_scrapers.py`
- **PhoneInfogaScraper:** GET `http://localhost:5000/api/numbers/{digits}/scan/local` (PhoneInfoga REST server). Returns carrier/country/line-type. Needs the PhoneInfoga server running (Docker/binary).
- **IgnorantScraper:** runs the `ignorant` CLI (`ignorant {cc} {national}`) to check IG/Amazon/Snapchat registration.
- **On failure / not installed:** `[]`.

> **Telegram (Telethon)** and **NumVerify** are present in config (`TELEGRAM_API_ID/HASH`, `NUMVERIFY_KEY`) but their scrapers are NOT built yet.

---

# 8. ENVIRONMENT & CONFIGURATION

## Environment variables (loaded in `backend/config.py`; copy `.env.example` → `.env`)
| Name | Required? | What it does | Example |
|------|-----------|--------------|---------|
| `DATA_MODE` | no (default `live`) | `live` = real scrapers; `mock` = fixed dev data | `mock` |
| `DEMO_FALLBACK_ENABLED` | no (default True) | reserved flag | `True` |
| `SERPER_API_KEY` | for Serper | Google search backbone | `abc123…` |
| `GITHUB_TOKEN` | recommended | GitHub API rate limit | `github_pat_…` |
| `NVIDIA_API_KEY` | for LLM | NVIDIA Cloud LLM | `nvapi-…` |
| `NVIDIA_BASE_URL` | no | LLM endpoint | `https://integrate.api.nvidia.com/v1` |
| `HIBP_API_KEY` | optional | breach lookups | `00000…` |
| `NUMVERIFY_KEY` | optional | phone validation (unused yet) | `…` |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | optional | Telethon (unused yet) | `12345` / `abcd` |
| `LLM_EXTRACT_MODEL` | no | extraction model | `meta/llama-3.3-70b-instruct` |
| `LLM_EXPLAIN_MODEL` | no | explanation model | `deepseek-ai/deepseek-v4-pro` |
| `LLM_TIMEOUT_SECONDS` | no (default 15) | per-LLM-call timeout | `15` |
| `DB_PATH` | no | SQLite file path | `cidecode.db` |
| `REPORT_OUTPUT_DIR` | no | where PDFs/artifacts go | `reports/` |
| `SYNTHETIC_DATA_PATH` | no | reserved | `data/synthetic_dataset.json` |
| `JWT_SECRET` | **yes for prod** | signs JWTs (warns if default) | `<32+ random hex>` |
| `TOKEN_EXPIRY_HOURS` | no (default 8) | token lifetime | `8` |
| `CORS_ORIGINS` | no | comma-separated allowed origins (read in `main.py`) | `http://localhost:3000` |
| `NEXT_PUBLIC_API_URL` (frontend) | no | backend base URL | `http://localhost:8000` |

> `validate_keys()` runs at startup (lifespan). It **warns** about missing keys but **never crashes**. Missing keys just disable the tools that need them.

## Local setup from scratch
```bash
# 1. Secrets
cp .env.example .env          # fill SERPER_API_KEY, GITHUB_TOKEN, NVIDIA_API_KEY (rotate any leaked keys!)
python -c "import secrets; print(secrets.token_hex(32))"   # paste into JWT_SECRET

# 2. Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install maigret           # primary username scraper (separate install)
python -m backend.database    # create cidecode.db (6 tables, WAL)
python -m scripts.create_admin  # creates admin / vertex2026
uvicorn backend.main:app --reload --port 8000   # http://localhost:8000/docs

# 3. Frontend
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                   # http://localhost:3000

# 4. Tests
python -m pytest tests/ -q    # 44 tests
```

## Environment differences
There is only one environment (laptop demo). `DATA_MODE=mock` for offline development/testing; `DATA_MODE=live` for the demo. No staging/production config exists.

---

# 9. WHAT'S DONE vs WHAT'S LEFT

## ✅ Fully working (tested)
- ✅ Config + 6-table SQLite DB (WAL, busy_timeout)
- ✅ Auth (register/login/JWT/bcrypt) + `get_current_user`
- ✅ Case CRUD + owner access control (cross-user → 404)
- ✅ `BaseDataSource`/`RawProfile` interface + `MockScraper`
- ✅ Correlation + scoring engine + **red-herring rule** (HIGH/LOW split verified)
- ✅ LLM client + regex/template fallbacks (work with no key)
- ✅ Orchestrator (parallel fan-out, UPI cascade, bio-link expansion, idempotent)
- ✅ Audit ledger hash chain + tamper detection
- ✅ BSA-63 PDF generator (professional layout, page numbers, XML-escaped, hash-verified)
- ✅ GitHub scraper (verified live), Serper, HIBP, UPI parser, phone wrappers (fail-safe)
- ✅ Frontend (login, case list, new-investigation, 3-panel dashboard, graph, timeline, polling, PDF download) — builds clean
- ✅ 44 pytest tests passing

## 🔧 Partially built / needs attention
- 🔧 **Live scrapers** — only GitHub exercised live. Maigret/Serper/HIBP/phone need real keys + installed CLIs on the demo machine. Maigret is NOT installed here.
- 🔧 **Streaming** — implemented as 1.5s polling, not true SSE/WebSocket. Works but re-fetches the full result set each tick.
- 🔧 **Face seed** — `face` is a valid seed type and the UI accepts it, but the pHash matcher scraper is NOT built (`face` maps to `[]` in `SEED_TOOL_MAP`).

## ❌ Not started
- ❌ Scrapers: Blackbird, socialscan, Reddit JSON, Telethon, Wayback CDX, pHash face matcher, Playwright Facebook/UPI-name lookups.
- ❌ Rate limiting on `/auth/*`.
- ❌ JWT server-side revocation (logout is client-side only).
- ❌ Retry-with-backoff/jitter on scrapers.

## Known issues / hacky bits
> - **Admin password `vertex2026` is a known demo default** — change before any real use.
> - **`role='admin'` is a label only** — no feature is gated by role; admin == normal user functionally.
> - **`seed_demo_case.py` creates a non-loginable user** (password_hash `"x"`) — by design, for seeding.
> - **CORS** defaults to `http://localhost:3000`/`127.0.0.1:3000`; set `CORS_ORIGINS` if the frontend runs elsewhere.
> - The **`face` seed type** silently returns nothing (no matcher). Don't promise face search in the demo.

---

# 10. HOW TO CONTINUE DEVELOPMENT

## What the next developer should do first
1. `cp .env.example .env`, fill **rotated** keys, set `JWT_SECRET`. (Keys were exposed in chat earlier — rotate GitHub/Serper/NVIDIA before use.)
2. `pip install -r requirements.txt && pip install maigret`, then run `python -m pytest tests/ -q` to confirm a green baseline.
3. **Verify the live scrapers** (Maigret, Serper, HIBP, phone) on the demo laptop — this is the single biggest unverified risk.

## Most important things to NOT break
> - **The fail-safe contract:** every scraper's `_run_live` may raise; `BaseDataSource.resolve` catches it and returns `[]`. Never let an exception escape a scraper — one broken tool must not stop the run.
> - **The red-herring rule** in `scoring_engine.score()` (single signal → capped LOW). This is the demo's credibility moment. Don't "fix" it to link more aggressively.
> - **`_esc()` in `bsa63_generator.py`:** every dynamic string in a reportlab `Paragraph` must be escaped or the PDF crashes on `&`/`<`.
> - **The audit ledger is append-only.** Re-running an investigation clears `entities`/`clusters` but NOT `audit_ledger`. Keep it that way.
> - **The LLM never decides linking.** It only describes/extracts, always with a fallback. Keep scoring deterministic.
> - **Parameterized SQL only** (`?` placeholders). Never f-string user input into a query.

## Conventions
- **Naming:** snake_case Python; files named by role (`*_scraper.py`, `*_service.py`, `*_routes.py`, `*_engine.py`). Frontend: camelCase JS, PascalCase components.
- **New scraper:** subclass `BaseDataSource`, implement `async def _run_live`, use `make_profile(...)` to build `RawProfile`s (it stamps `collected_at` + `sha256`), return `[]` on any failure, then add the class to `_seed_tool_map()` in `orchestrator.py`.
- **DB access:** always `get_db()` then `try/finally: conn.close()`. Parameterized queries.
- **IDs:** `uuid4().hex` strings everywhere (not ints).
- **Timestamps:** ISO8601 UTC (`datetime.now(timezone.utc).isoformat()`).
- **httpx in scrapers:** use `httpx.AsyncClient` + `await` (NOT sync `httpx.Client` — it blocks the event loop and defeats parallelism).

## Decisions made (and why) — don't undo these
- **No ORM** — stdlib `sqlite3` is enough for one laptop; an ORM adds complexity.
- **No cache layer** — the demo is fully live by design (per the architecture's Decision 1). `mock` mode exists for dev only.
- **WAL + busy_timeout** — chosen so the polling frontend (reader) and the orchestrator (writer) don't hit "database is locked".
- **Confidence capped at `min(100, sum)`** — deliberately, so the HIGH>75 threshold is reachable. Don't normalize against the sum of all weights.
- **LLM enhancement-only** — so the "explainable, auditable, court-ready" story holds; an LLM linking decision can't be defended in court.
- **CORS `allow_credentials=False`** — we use Bearer tokens, not cookies; `*` + credentials is an invalid combo.

## Gotchas that WILL trip you up
> - **Windows console is cp1252** — do NOT print non-ASCII (emoji like `⚠`) at startup; it crashes uvicorn. (This already bit us once in `config.py`.)
> - **Report download must use `api.downloadReport()`** (fetch + Bearer header), not an `<a href>` — navigation can't send auth headers (this caused the "Missing or malformed Authorization header" error).
> - **`conftest.py` must set `DB_PATH`/`DATA_MODE` env BEFORE importing any backend module** — `config.py` reads env at import time. Tests use a temp DB so they never touch `cidecode.db`.
> - **Maigret runs as an async subprocess** — on Windows this needs the Proactor event loop (default on 3.10). If you move the orchestrator off `asyncio.run`, re-test Maigret.
> - **`get_case` returns `None` for both "not found" and "not owned"** → routes return 404 for both (intentional; don't leak existence).
> - **Password min length is 6, username min 3** (enforced in `register_user`). Old test fixtures using `'pw'` will now fail — use ≥6 char passwords.
> - **The frontend graph only rebuilds when the node/cluster signature changes** (not every poll) — if you change the results shape, update the `signature` memo in `Graph.js` or the graph won't refresh.

---

## Quick reference — run commands
```bash
# backend
uvicorn backend.main:app --reload --port 8000
# create admin
python -m scripts.create_admin                 # admin / vertex2026
python -m scripts.create_admin myname mypass    # custom
# seed a demo case (mock)
python -m scripts.seed_demo_case
# tests
python -m pytest tests/ -q
# frontend
cd frontend && npm run dev
```

**Default admin:** `admin` / `vertex2026` (change it). **Legal claims:** see `LEGAL_VERIFICATION.md`. **Original design:** `VERTEX_Master_Architecture (1).md`.

---

# 11. SESSION UPDATE — 2026-07-01 (environment rebuild + full code review & hardening)

> Appended by Claude Opus 4.8 (1M context). Everything in Sections 1–10 still describes the
> system accurately. This section records (a) the **current running state**, (b) **how the
> environment was rebuilt** on this machine, (c) **every code change** made in the 2026-07-01
> hardening pass, and (d) the **facts that now supersede** specific lines above. Where this
> section conflicts with anything earlier, **this section is the current truth.**

## 11.1 Current running state (verified)
- **Backend:** `uvicorn backend.main:app --port 8000` → http://localhost:8000 (`/health` → `{"status":"ok","data_mode":"live"}`, docs at `/docs`).
- **Frontend:** `npm run dev` → http://localhost:3000 (falls back to 3001 if 3000 is busy).
- **Python venv:** `VERTEX/venv` (Python **3.10.0**). The old bundled `.venv` one level up was deleted (see 11.2).
- **DB:** `cidecode.db` — the `audit_ledger` table now has a `chain_hash` column (migration auto-applied by `init_db()`).
- **Tests:** `python -m pytest tests/ -q` → **48 passed** (was 44; +4 over time, +1 added this pass).
- **`.env`:** gitignored, never committed (verified via `git ls-files` / `git log` — keys are NOT in the repo). `JWT_SECRET` rotated to a random 64-hex value.

## 11.2 Environment setup — what actually had to happen on this machine
The repo arrived pre-cloned at `vertex_Ash/ash/ash/VERTEX` (branch `ashwin`) but the **bundled virtualenv was unusable**: it had been created on a different machine (`C:\Users\LENOVO\...`, Python 3.14) and its interpreter path didn't exist here. Steps taken:
1. Deleted the broken `ash/ash/.venv`; created a fresh venv with `C:\Python310\python.exe` at **`VERTEX/venv`** (Python 3.10 matches the project target).
2. `pip install -r requirements.txt`, then **`pip install pytest pytest-asyncio`** — **pytest is NOT in `requirements.txt`** but the suite needs it. `maigret` installs fine from `requirements.txt` (no separate step needed here).
3. Initialised the DB + admin (`python -m scripts.create_admin` → `admin` / `vertex2026`).
4. Frontend: `node_modules` was present; ran `npm install` to reconcile, created **`frontend/.env.local`** (`NEXT_PUBLIC_API_URL=http://localhost:8000`) — there is **no `.env.local.example`** in the repo despite docs referencing one. `npm run build` and `npm run dev` both pass.

> **Port gotcha (cost real time — document it):** `uvicorn --reload` runs as a **parent + multiprocessing child**. If the parent is hard-killed, the **child can be orphaned and keep holding the socket**, and `netstat -ano` still lists the socket under the **dead parent PID** — so `taskkill /PID <parent>` says "not found" while the port stays busy. Fix: find the live python child whose `parent_pid` is that dead PID and kill the child. To find a port owner on Windows: `netstat -ano | findstr :8000`.

## 11.3 Code changes made in the 2026-07-01 hardening pass

### A. Audit ledger — tail-row tamper hole CLOSED (most important)
**Problem:** `verify_chain` sealed each row only via the *next* row's `previous_hash`. The **last** row had no successor, so its content (`input_hash`/`output_hash`/`action`/`actor`/`timestamp`) could be edited and `verify_chain` still returned `True` — a real hole in the court-evidence guarantee.
**Fix (3 files):**
- `backend/database/__init__.py` — added `chain_hash TEXT` to the `audit_ledger` schema **and** an idempotent migration in `init_db()` (`ALTER TABLE audit_ledger ADD COLUMN chain_hash` if absent, since `CREATE TABLE IF NOT EXISTS` never alters an existing table). Also fixed a non-ASCII em-dash in a startup `print` (cp1252 safety).
- `backend/ledger/audit_ledger.py` — `log_action` now computes and stores each row's `chain_hash` (the self-seal). `_last_chain_value` prefers the stored `chain_hash` (falls back to recompute for pre-migration rows). `verify_chain` now checks **both** the forward link (`previous_hash` == prior row's chain value) **and** the self-seal (recomputed chain value == stored `chain_hash`) — so tampering the last row is now detected.
- `tests/test_ledger.py` — added `test_tamper_last_row_detected` regression (edits the final row; expects the chain to break).

### B. Auth correctness / hardening
- `backend/auth/auth_routes.py` — `register` now maps **duplicate username → 409**, **validation errors (too-short username/password) → 400** (previously every `ValueError` → 409). Matches the now-passing `test_short_password_rejected` (accepts 400/409) and `test_duplicate_username_rejected` (409).
- `backend/auth/auth_service.py` — `decode_token` broadened `except JWTError` → `except Exception` so a malformed token can never escape as a **500/stack trace** (always a clean 401). Removed the now-unused `JWTError` import. `_hash_pw`/`_check_pw` now truncate the password to **72 bytes** consistently (modern bcrypt raises on longer input → would otherwise crash register and cause inconsistent login).

### C. Scraper resource leaks (fail-safe contract preserved, zombies removed)
- `backend/ingestion/maigret_scraper.py` — added `await proc.wait()` after `proc.kill()` on timeout (reap the killed subprocess).
- `backend/ingestion/phone_scrapers.py` — `IgnorantScraper` now wraps `asyncio.wait_for` in `try/except asyncio.TimeoutError`, does `kill()` + `await wait()` + returns `[]` (was leaking an orphaned `ignorant` process on timeout).

### D. PDF generation (BSA-63)
- `backend/report/bsa63_generator.py` — the **case-reference cover cell** now passes through `_esc(str(...))` (was the one dynamic Paragraph value not XML-escaped, and would crash on a `NULL` case_id). All other dynamic strings were already escaped.

### E. main.py visibility
- `backend/main.py` — router-load failures now `print` an ASCII warning instead of silently `pass`, so a broken `auth_routes`/`case_routes` import no longer produces a "healthy but 404 everything" app with no log line.

### F. Frontend
- `frontend/lib/api.js` — thrown errors now carry `err.status` (the HTTP status) in both `req()` and `downloadReport()`.
- `frontend/components/Graph.js` — the rebuild **signature now includes `confidence_score`** (rounded) and has `|| []` guards. Previously node sizes/edge weights went stale during polling when a score changed but tier/membership didn't.
- `frontend/app/cases/[id]/page.js` — removed the unused `tick` state (it forced an extra re-render every 1.5 s poll); expired-token detection now uses `e.status === 401` (was the unreliable `String(e).includes("401")`).
- `frontend/app/cases/page.js` — same `e.status === 401` fix for the case-list refresh.

### G. Setup / tooling / config
- **Added `backend/database/__main__.py`** so the documented `python -m backend.database` works (the package had no `__main__`, so the command errored — see the corrected note in 11.4).
- `.env` — `JWT_SECRET` rotated from the weak known string to a random 64-hex value.
- `frontend/.env.local` — created (points the UI at `http://localhost:8000`).

## 11.4 Facts that SUPERSEDE specific earlier lines
- **§5 schema (`audit_ledger`):** the table now also has **`chain_hash TEXT`** (the per-row self-seal). The chain value is now both *recomputed* AND *stored*; `verify_chain` confirms they match.
- **§4 / Flow A:** `POST /auth/register` returns **400** for too-short username/password and **409** only for a duplicate username (Section 1/4 said "409 for both" — that was the old behaviour).
- **§4 `VALID_SEED_TYPES`:** the code set is `{name, email, phone, username, upi, face, url}` — i.e. it also includes **`url`** (the six-type lists above omit it). `face` still maps to `[]` (no matcher).
- **Test count:** **48** passing (Sections 1/2/9 say 44).
- **`python -m backend.database`:** now **works** (creates/upgrades the schema). The earlier setup blocks that show this command are now correct as written.
- **pytest:** must be installed separately (`pip install pytest pytest-asyncio`) — it is not in `requirements.txt`.
- **Frontend env template:** there is **no `frontend/.env.local.example`**; create `frontend/.env.local` with `NEXT_PUBLIC_API_URL` by hand (CORS already allows ports 3000 and 3001).

## 11.5 End-to-end recap (one pass, current build)
1. **Setup:** `VERTEX/venv` (py3.10) with `requirements.txt` + pytest installed; `cidecode.db` created via `python -m backend.database` (or `scripts.create_admin`); admin = `admin`/`vertex2026`; `.env` holds keys + a rotated `JWT_SECRET`; frontend `.env.local` → `:8000`.
2. **Run:** backend `uvicorn backend.main:app --port 8000`; frontend `npm run dev` (`:3000`). `validate_keys()` warns (never crashes) on missing keys at startup.
3. **Auth:** register/login → JWT (HS256, 8 h). Protected routes need `Authorization: Bearer <jwt>`; bad/expired/malformed → 401 (never 500).
4. **Investigate:** `POST /cases` validates seeds, stores the case, and fires `run_investigation_sync` as a background task → orchestrator fans scrapers out in parallel (fail-safe), runs the UPI cascade + LLM entity extraction + bio-link expansion (cap 5), de-dupes, persists `entities`, then `correlate()` → `score()` (12 signals, tiers, **red-herring rule**) → persists `clusters`. Every step appends a **self-sealed** ledger row.
5. **Stream:** the UI polls `GET /cases/{id}/results` every 1.5 s, growing the account list + sigma.js graph (now refreshing on score changes) until `complete`.
6. **Evidence:** `GET /cases/{id}/report` builds the BSA-63 PDF (XML-escaped throughout) and `verify_chain` (now tail-safe) proves the ledger is intact. Hashes are independently recomputable.

## 11.6 Keys / secrets status (current)
- `.env` is **gitignored, untracked, and absent from git history** (verified) — the API keys are **not exposed via the GitHub repo**. They are the team's shared credentials for one project, which is normal; no rotation is required merely because they sit in a local `.env`.
- Rotate a specific third-party key **only** if it was shared somewhere broader than the team (public chat/screenshot/public repo). `JWT_SECRET` (a local token-signing secret, not a third-party key) was rotated to a strong random value this session.

## 11.7 Still open (after the hardening pass)
- `face` seed type still has no matcher; true SSE/WebSocket streaming, rate limiting, JWT server-side revocation, and retry-with-backoff are still not implemented.
- `reference/HANDOVER.md` describes an **older, divergent fork** (Groq LLM, `POST /investigate`, different signal weights, `reddit`/`telethon` scrapers, macOS paths). It is **superseded by this `context.md`**; do not treat it as current.

---

# 12. OSINT CAPABILITY EXPANSION — 2026-07-01 (Sprint 1 & 2)

> Appended by Claude Opus 4.8. This section documents the OSINT collection/analysis
> work done after the §11 hardening pass, in response to the CID requirement list
> (cross-platform identity verification, photo matching, activity analytics, breach
> exposure, email→services). **Audit-first principle:** before building, every existing
> scraper was read; several "wired" scrapers were found to be **stubs or dead** and are
> called out below so nobody mistakes them for working features.

## 12.1 TWO infrastructure bugs that were silently crippling live collection
Both made scrapers return `[]` *silently* (fail-safe contract), so the tool *looked* like it worked while collecting little. Both are FIXED:

1. **Corporate-TLS failure (`backend/config.py`).** On this network (TLS-inspection proxy) httpx raised `CERTIFICATE_VERIFY_FAILED` for many hosts (archive.org, reddit, xposedornot, **and the NVIDIA LLM**) because Python's bundled certifi store didn't trust the proxy CA. Fix: `truststore.inject_into_ssl()` at config import — Python now uses the **OS certificate store** (still fully verifies). Added `truststore` to `requirements.txt`.
2. **CLI tools not on PATH (`base_module.resolve_tool`).** When the backend is launched via `venv\Scripts\python.exe` *without activation*, the venv `Scripts/` dir isn't on PATH, so `create_subprocess_exec("maigret", ...)` failed with `FileNotFoundError` → `[]`. **This meant maigret (the username backbone), holehe, sherlock, blackbird, and ignorant had never actually executed.** Fix: a shared `resolve_tool(name)` resolves via PATH then the interpreter's `Scripts/bin` dir; every CLI scraper now resolves its exe (and returns `[]` only if genuinely not installed). **Verified live after the fix:** maigret → 88 accounts, sherlock → 99 accounts for `torvalds`.

## 12.2 Sprint 1 — made three dead correlation signals REAL
The signals existed in `correlation_engine.py` but no scraper populated their inputs:
- **Profile-photo / face matching** — new `backend/ingestion/photo_enrich.py`: after dedup (live only), downloads each profile picture (keys: `photo_url`/`avatar`/`image`/…) and computes an `imagehash.phash`, written to `metadata["photo_phash"]`. The orchestrator calls `enrich_photos(profiles)` before correlation. The `profile_photo_phash` signal (Hamming<8) now links the **same photo reused across platforms**. *Verified:* identical image → identical hash → correlation fires the signal; different image → no match.
- **Posting-time + frequency** — `reddit_scraper.py` now also fetches the user's recent comments and derives, from real timestamps: `posting_hours` (active-hour fingerprint = hours busier than the user's own average — feeds the `posting_hours_overlap` signal), `posting_frequency_per_day`, a 24-bucket `activity_by_hour` histogram, and `most_active_time_utc`.
- **Breach exposure** — HIBP needs a paid key (the `.env` key is a dummy), so new `backend/ingestion/xposedornot_scraper.py` uses the **free, key-less XposedOrNot** API to populate `metadata["breaches"]` (names only — never passwords). Feeds the `breach_co_occurrence` signal and the report. *Verified:* returns hundreds of real breaches for a test address.

## 12.3 Sprint 2 — new collectors + recall
- **`holehe_scraper.py` (HoleheScraper)** — email → registered services via the `holehe` CLI (`--only-used`, ~120 sites, parses `[+] domain` lines). Replaces the dead Epieos/user-scanner stubs in the email seed map. *Verified:* 4 services for a test address. Lawful: uses password-reset/registration responses, never logs in, never sees passwords.
- **`sherlock_scraper.py` (SherlockScraper)** — second username enumerator alongside Maigret. A site found by **both** is stronger corroboration. Wired into the `username` seed map. *Verified:* 99 accounts for `torvalds`.
- **`variants.py` (`username_variants`)** — generates well-formed handle variants (`j.shankar` → `jshankar`/`j_shankar`/`shankarj`/`shankar.j`; `Arjun Mehta` → `arjunmehta`/`arjun.mehta`/`amehta`/…; strips trailing digits for single tokens). The orchestrator (live only, step "2.5") expands each `username` seed to ≤5 variants (global cap 8) and re-runs the **fast** enumerators (`_fast_username_tools()` = GitHub/Reddit/socialscan/blackbird — **not** Maigret/Sherlock, to bound runtime) on each; profiles are tagged `metadata["found_via_variant"]`. This is the biggest cross-platform recall booster.
- **Reddit app-only OAuth** — `reddit_scraper.py` now uses `oauth.reddit.com` with a cached app-only token when `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are set (config + `.env` placeholders added), avoiding the anti-bot **403s that block datacenter IPs**; falls back to the public endpoint otherwise. *Note:* on this datacenter IP the public endpoint returns 403 — set Reddit creds (free "script" app) or run from a residential/venue network for live Reddit data.

## 12.4 Scraper reality table (what produces data TODAY)
| Scraper | State |
|---|---|
| maigret, sherlock, holehe, socialscan | ✅ Real & resolve now (installed); maigret/sherlock/holehe verified live |
| github, serper, wayback, xposedornot, reddit(code) | ✅ Real HTTP (truststore-fixed); reddit needs OAuth/residential IP for live |
| photo_enrich (pHash) | ✅ Real & verified |
| numverify, phoneinfoga | 🟡 numverify keyed; phoneinfoga needs a local server |
| hibp | 🟡 Real code, dummy key → use XposedOrNot or add a paid key |
| blackbird, ignorant | 🟡 Real wrappers, **not installed** (separate git/pip) → fail-safe `[]` |
| **epieos, facebook_phone** | ❌ **STUBS** (always `[]`); telethon uses a bot token and can't resolve arbitrary users — treat as non-functional. epieos/user_scanner were removed from the active seed map. |

## 12.5 Capabilities vs. the CID wishlist — honest status
- ✅ **Real & defensible / built:** cross-platform username verification (Maigret+Sherlock+variants), email→services (holehe), breach exposure (XposedOrNot), profile-photo/face matching (pHash), posting-time/frequency (Reddit), archived/deleted public content (Wayback), GitHub/Reddit profile data, bio-link expansion, basic stylometry (bio TF-IDF — upgrade pending).
- ⏳ **Planned (Sprint 3):** real stylometry (char n-grams/function words across all collected text), sentiment/keyword analysis, engagement metrics, and a "leads vs. evidence" split in the UI/PDF. Sourcing stance chosen by the user: **include ToS-gray sources as clearly-labelled non-evidentiary leads** (e.g. Instagram/Telegram public data) — must be visually separated from evidence in the UI/PDF.
- ❌ **Not built — deliberately (myth / inadmissible), do not promise:** Telegram "IP from phone/username" (impossible), password harvesting from breaches (illegal to use, inadmissible — we return breach *names* only), viewing private stories / fetching private deleted posts (auth circumvention → inadmissible; Wayback is the lawful substitute), WhatsApp DP harvesting (privacy-gated/ToS), Truecaller/Eyecon scraping (no API, poor provenance — carrier/HLR via NumVerify/PhoneInfoga is the defensible version). Refusing these is a courtroom strength, not a gap.

## 12.6 New dependencies & env
- `requirements.txt`: `truststore`, `holehe`, `sherlock-project` added (pulls pandas/openpyxl/trio).
- `.env`: `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` (optional; for reliable Reddit).
- Tests: `conftest.py` now forces the LLM into its fallback (offline/deterministic) — without this, truststore lets the orchestrator tests make real NVIDIA calls (slow/flaky). Still **48 passing**.

## 12.7 UI legibility + reading the dashboard correctly
- **Graph/tier colour contrast fixed.** On the near-black canvas (`#0E1117`) the old LOW (`#8A4A2E`, muddy brown) and UNLINKED/REJECT (`#4A5568`, dark slate) tiers were nearly invisible — and most nodes are those tiers. Brightened, consistently, in **all** definition sites: `globals.css` (`.tier-*`), `components/Graph.js` (`NODE_COLOR`/`EDGE_COLOR`), `components/Timeline.js` (`TIER_BG`), `app/cases/[id]/page.js` (`NODE_HEX`, AccountCard/ClusterBlock accents, graph legend), and `tailwind.config.js` (`steel`, `rust` tokens). New palette: HIGH `#D4900A` (unchanged brand amber), MEDIUM `#5B9BD5`, LOW `#E08A4A`, UNLINKED/REJECT `#8A97AD`.
- **Why a bare username often shows "0 clusters / all LOW-unlinked" (this is correct, not a bug):** for a username-only seed the engine finds many same-string accounts across platforms, but with **no shared phone/email/photo/activity** between them the **red-herring rule** refuses to merge them — they remain LOW singletons. Multi-account HIGH clusters appear when corroborating signals exist (same registered phone/email/UPI, identical profile photo via the new pHash, overlapping posting hours, shared breaches). Demo with a seed that produces those signals to show HIGH links.
- **Status confirmed (2026-07-01):** running server reflects current code; full endpoint sweep passes (auth/cases/access-control/report — 19/19); `compileall` + import-all (35 modules) clean; report endpoint returns a valid `application/pdf`.

## 12.8 Phone-seed path fixed
The phone seed was effectively empty. Root cause: its only web query was the dork `site:truecaller.com "{q}"`, which returns **0** results (Truecaller `noindex`s profiles), and HIBP (email-only) + the Facebook-phone stub contributed nothing. NumVerify worked but is just one carrier/line-type record.
**Fix (orchestrator `_seed_tool_map`):** `phone → [NumVerifyScraper(), PhoneInfogaScraper(), IgnorantScraper(), SerperScraper('"{q}"')]`. The **plain Serper search** surfaces real web mentions (Truecaller/Facebook/Instagram/Scribd hits), and NumVerify supplies carrier/line-type/country. HIBP and the Facebook stub were removed from the phone path. *Verified live:* ~11 results per number for both a US and an Indian test number. PhoneInfoga/ignorant remain (fail-safe) for when a local PhoneInfoga server / the `ignorant` CLI is present.

## 12.9 Audit of the remaining paths (2026-07-01) — issues found & fixed
A full sweep of the other seed paths (email/name/upi/url) + the remaining scrapers + report/correlation/scoring. **Every seed type now produces output** (email→~20, name→~30, upi→3 w/ cascade, url→3). Fixes applied:
- **socialscan was permanently dead** — it shelled out with a `--json` flag that doesn't exist in socialscan 1.4.2 (empty stdout → `[]`). Rewritten to use the **async Python API** (`await execute_queries([username])`), keeping platforms where `available is False and valid and success`. *Verified:* 4 taken platforms for `torvalds`.
- **url_scraper extracted bogus handles** → false cascade seeds & correlations (`youtube.com/watch?v=…`→`watch`, `instagram.com/p/<id>`→`p`). Fixed: YouTube regex restricted to `@`/`c/`/`user/`; reserved-segment denylist; query/fragment stripped; last-segment fallback only fires for unknown hosts (a known-platform URL with no profile handle is recorded as a URL reference with no cascade).
- **Serper platform mislabel** — `in.linkedin.com`/`uk.linkedin.com` were labelled `in`/`uk`. `_platform_from_url` now uses the second-level domain (`linkedin`).
- **breach_co_occurrence too noisy** (false-link risk) — a single shared mega-breach (Collection #1/LinkedIn/Adobe…) fired the signal. Now fires only on a rare shared breach or ≥2 shared (`_MEGA_BREACHES` denylist).
- **correlation type-robustness** — `_norm`/`_phone` now `str()`-coerce so a scraper emitting a list/int can't abort the pipeline.
- **report PDF crash-safety** — `action`/`actor`/`artifact_type`/filename/`tier` now `_esc()`'d; `search_id`/`*_hash` subscripts NULL-guarded; non-dict seed no longer aborts the cover.

## 12.10 Report now renders the full digital footprint (gap closed)
Added section **"2A. Digital Footprint & Exposure"** to `bsa63_generator.py` (after Findings Summary). It parses each entity's `metadata_json` and renders four `_esc()`/`_redact()`-safe tables:
- **Discovered accounts** — platform, account, name, activity (most-active-hour + posts/day); capped at 40 with total noted.
- **Service registrations** — per email, the services it's registered on (holehe).
- **Data-breach exposure** — identifier, breach count, sample breach names (names only; no credentials).
- **Phone intelligence** — carrier / country / line type (NumVerify).

*Verified live:* an email+phone case produced a **39 KB** PDF (was ~13 KB) with all four tables populated (lastpass/office365 registrations, breach list, carrier data); 48 tests still pass. Remaining Sprint-3 item: an explicit "leads vs. evidence" visual split + real stylometry/sentiment.

> ⚠️ Editing note: `context.md` was once reverted mid-session because it was open & re-saved in the IDE. If you keep it open, close/refresh it before I edit, or my appended sections may be overwritten.

---

# 13. SPRINT 3 — Forensics layer (2026-07-01)

> NOTE: this section was lost once to an IDE re-save and re-added. If it's missing, the
> forensics layer below is still in the code; this is just its documentation.

## 13.1 Entity-bloat fix
A username seed produced ~380 entities, ~170 of them redundant `url` type (the URL parser was re-run on every discovered account URL). Discovered URLs now get a **Wayback archive check only, capped at 20**; the URL parser runs only on user-entered `url` seeds. `torvalds`+email dropped 379 → **196 entities** with no junk nodes.

## 13.2 `backend/analysis/forensics.py` (NEW package + module)
- **`stylometry_similarity(a, b)`** — character n-gram cosine + function-word frequency cosine (authorship style, not topic). Replaces the old 2-bio word-TF-IDF. Identical text → 1.0, unrelated → ~0.007.
- **`summarize(entities)`** — case-level forensic block: VADER **sentiment/tone** (+`flag_negative` for hostile tone), **keywords + hashtags**, **activity-hour profile** (merged `posting_hours`), **engagement** (followers), **footprint** (platforms / breach exposures / registered services).
- `reddit_scraper` now stores sampled comment bodies as `metadata["text_sample"]` to feed stylometry + sentiment. New dep: `vaderSentiment`.

## 13.3 Surfaced in 3 places
- **Results API:** `get_results` now returns a **`forensics`** field (see §14 correction of §4).
- **Frontend:** "LINGUISTIC & BEHAVIOURAL FORENSICS" panel on the case page (above the timeline).
- **Report:** new **"2B. Linguistic & Behavioural Forensics"** section (`bsa63_generator`), `_esc`-safe.

## 13.4 UI contrast round 2
Muted text token `dim` `#4A5568` → `#8693A8`; `.panel-label` → `#8693A8`; `.hash-val` → `#707E96`. (Tier node colours were brightened in §12.7: HIGH `#D4900A`, MEDIUM `#5B9BD5`, LOW `#E08A4A`, UNLINKED `#8A97AD`.)

---

# 14. AUTHORITATIVE CORRECTIONS TO §1–10 (read these over the body)

The body (§1–10) is the original snapshot. Where it conflicts with the list below, **this section is correct** (verified against the code 2026-07-01).

## 14.1 Correlation signal weights — §6 line ~407 is WRONG. Actual `SIGNAL_WEIGHTS` (15 signals):
```
exact_phone_match      = 60      exact_email_match      = 60      exact_upi_match       = 60
username_exact_match   = 45      username_substring_match = 20    username_fuzzy_match  = 15
exact_name_match       = 35      fuzzy_name_match       = 20      location_overlap      = 15
profile_photo_phash    = 35      posting_hours_overlap  = 15      stylometry_cosine     = 20
breach_co_occurrence   = 18      bio_keyword_overlap    = 12      reciprocal_mention    = 15
```
(The §6 numbers — phone=40, email=35, etc. — and the omission of `exact_name_match`/`fuzzy_name_match`/`location_overlap` are stale.)

## 14.2 Other §6 / §7 corrections
- **Stylometry** is now char n-grams + function-word distribution (`forensics.stylometry_similarity`), fired at **> 0.6** over each profile's `bio + text_sample` (length gate 25 chars). NOT "TF-IDF > 0.75 / bios > 15".
- **`username_fuzzy_match`** fires on **thefuzz ratio ≥ 80** (difflib percent fallback), not "Levenshtein < 3".
- **`reciprocal_mention` (15) is defined but NEVER fires** — no scraper supplies mention-graph data. Treat as inactive.
- **`breach_co_occurrence`** no longer fires on a single shared mega-breach (rare-or-≥2 rule; see §12.9).

## 14.3 `/cases/{id}/results` response — §4 (line ~274) and Flow F omit a field. Actual:
```
{ "case": {...}, "entities": [...], "clusters": [...], "forensics": {...}, "status": str }
```

## 14.4 BSA-63 PDF sections — Flow G (§3) is missing two. Actual order:
Cover → 1. Search Manifest → 2. Findings Summary → **2A. Digital Footprint & Exposure** → **2B. Linguistic & Behavioural Forensics** → Annexure A → Certificate Part A → Part B → 3. Chain of Custody → Document Integrity Statement.

## 14.5 File map (§2) — current ingestion + analysis modules
`backend/ingestion/` actually contains: base_module, mock_scraper, github_scraper, serper_scraper, hibp_scraper, **xposedornot_scraper**, **holehe_scraper**, maigret_scraper, **sherlock_scraper**, **socialscan_scraper**, **blackbird_scraper**, **reddit_scraper**, **telethon_scraper**, **wayback_scraper**, **url_scraper**, **variants.py**, **photo_enrich.py**, upi_module, phone_scrapers, plus three **dead/unwired files still on disk**: `epieos_scraper.py`, `facebook_scraper.py`, `user_scanner_scraper.py` (stubs/bot-token — not in the seed map). New package **`backend/analysis/`** → `forensics.py`.

## 14.6 Current live seed → tool map (`orchestrator._seed_tool_map`)
```
email    : HIBP, XposedOrNot, Holehe, BlackbirdEmail, GitHub, Serper('"{q}"')
phone    : NumVerify, PhoneInfoga, Ignorant, Serper('"{q}"')
username : Maigret, Sherlock, BlackbirdUsername, Socialscan, Reddit, Telethon, GitHub, Serper('"{q}"')
upi      : UPI parser, Serper('"{q}"')
name     : Serper(site:linkedin.com/in), Serper(site:instagram.com), Serper(site:twitter.com)
url      : URLScraper, Wayback
face     : []   (no matcher runs; pHash matches photos discovered via other seeds)
```
Pipeline order: per-seed fan-out → **variant expansion** (live; fast tools = GitHub/Reddit/socialscan/blackbird; ≤8 variants) → derived-seed cascade → **archive check** (Wayback, ≤20 URLs) → LLM entity-extraction (≤10 blobs) + bio-link expansion (≤5) → dedup → **photo pHash enrichment** (live) → persist → correlate → score → forensics.

## 14.7 Test count

**71** (was 48 → 59 → 71). pytest/pytest-asyncio install separately (not in requirements.txt).

---

## 15. SPRINT 4 — OSINT tool installation + FP hardening (2026-07-01)

> This section covers work done after the §13/§14 session: installing two missing tools, fixing the FP filter race condition, rewriting the Blackbird scraper from scratch, and extending `resolve_tool()`.

## 15.1 ignorant — installation and verification

`ignorant` is a pip-packaged phone-registration checker (Instagram, Amazon, Snapchat). It was listed in the seed map but not installed.

```bash
pip install ignorant        # installs v1.2 with a console-script entry point
```

**Verification** (live): `IgnorantScraper` runs `ignorant <number>` in a subprocess, parses `[+]` lines, and returns `phone_registration` profiles. Confirmed `[+] instagram.com` returned for a live test number.

`IgnorantScraper` already existed in `phone_scrapers.py`; no scraper rewrite was needed — only the installation.

## 15.2 Blackbird — installation, CLI verification, and scraper rewrite

Blackbird is a **WhatsMyName-based** username/email enumerator that checks ~680 sites. It was listed in the seed map but neither installed nor correct in the scraper code. Three independent bugs were found by manual CLI verification **before touching any code** (lesson from the socialscan `--json` incident):

| Bug | Old scraper assumption | Reality |
| --- | ---------------------- | ------- |
| Output location | `--json` writes JSON to **stdout** | `--json` writes a file to `{repo}/results/{user}_{date}_blackbird/{user}_{date}_blackbird.json` |
| Platform key | `entry.get("site") or entry.get("app")` | `entry.get("name")` |
| Windows encoding | No encoding set | `rich` library prints box-drawing chars → `UnicodeEncodeError` with cp1252 stdout |

**Installation:**

```bash
git clone https://github.com/p1ngul1n0/blackbird C:\path\to\blackbird
pip install -r C:\path\to\blackbird\requirements.txt
# version conflict fix (Blackbird pins older aiohttp/multidict/reportlab than maigret needs):
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"
# .env: BLACKBIRD_PATH=C:\path\to\blackbird
```

Blackbird's `config.py` uses `os.getcwd()` for all data paths (wmn-data.json). The subprocess must always run with `cwd=repo` (the BLACKBIRD_PATH directory), otherwise the data file isn't found.

**`blackbird.bat` wrapper** — created at `venv/Scripts/blackbird.bat`:

```bat
@echo off
"<venv>\Scripts\python.exe" "<blackbird_path>\blackbird.py" %*
```

**`_run_blackbird` key design decisions** (in `backend/ingestion/blackbird_scraper.py`):

- Subprocess command: `.bat` files can't be run directly by `CreateProcess`; wrapped as `["cmd", "/c", bat_path, ...]` via `_build_cmd()` helper.
- `PYTHONIOENCODING=utf-8` injected into subprocess env to prevent cp1252 crash.
- JSON file found via glob (`results/{safe_value}_*_blackbird/*.json`) as fallback if the date in the filename doesn't match (clock drift, timezone).
- `metadata` list `[{name, value}, ...]` is flattened into a dict for the profile's `metadata` field.
- Only entries with `status == "FOUND"` are returned; `ERROR`, `NONE`, `NOT-FOUND` are skipped.

**Verified live**: 87 profiles returned for `torvalds`.

## 15.3 resolve_tool() extended to .bat and .cmd on Windows

`backend/ingestion/base_module.py` — the fallback extension loop now tries `[".exe", ".bat", ".cmd"]` on Windows (was only `".exe"`). Uses `sys.prefix` (the venv root) as the base, **not** `os.path.dirname(sys.executable)` (which is already the Scripts dir, and would create a double-Scripts path like `Scripts/Scripts/blackbird.bat`).

```python
exts = [".exe", ".bat", ".cmd"] if os.name == "nt" else [""]
sub  = "Scripts" if os.name == "nt" else "bin"
for base in (os.path.dirname(sys.executable), sys.prefix):
    for ext in exts:
        cand = os.path.join(base, sub, name + ext)
        if os.path.exists(cand):
            return cand
```

## 15.4 FP filter race condition fix

`backend/ingestion/fp_filter.py` — `_save_cache` had a race condition: Maigret and Sherlock (and now Blackbird) run in parallel via `asyncio.gather`. Each would load the stale (empty) cache dict at the start of `filter_with_control`, then write its own entry at the end — the last writer would stomp the first writer's entry.

Fix: `_save_cache` now does a **read-merge-write** — load the current file, update a single key, save. Since `asyncio` is single-threaded and there is no `await` inside `_save_cache`, there is no interleaving between concurrent callers.

Old signature: `_save_cache(data: dict)` — saved the full stale dict.
New signature: `_save_cache(tool_name: str, entry: dict)` — loads current file, merges one entry, saves.

## 15.5 FP filter extended to Blackbird; Socialscan confirmed FP-free

Control probe runs for Maigret, Sherlock, and Blackbird. Socialscan uses actual registration-flow checks (not HTTP heuristics), confirmed **0 FP** on the garbage username — no filter needed.

**Verified FP exclusion counts (2026-07-01):**

- Maigret: **36 sites** excluded
- Sherlock: **3 sites** excluded (allmylinks, baby, mastodon)
- Blackbird: **1 site** excluded (arch linux gitlab)

**Residual slip-through**: 6 garbage-username entities still appear after filtering. Root cause: these sites use pattern-dependent heuristics (e.g., `"username doesn't exist"` in the body) that happen to fire for the 20-char hex control but not for realistic-looking usernames. This is a known limitation of the control-probe approach, not a code bug.

## 15.6 Test count update

New test file `tests/test_step0_tools.py` — 12 tests:

- `test_resolve_tool_finds_exe/bat/cmd` — uses `monkeypatch.setattr(sys, "prefix", str(tmp_path))`; patches `shutil.which` to None so the PATH fallback doesn't accidentally find a real tool.
- `test_resolve_tool_returns_none_for_missing`
- `test_blackbird_parser_reads_name_field` — verifies `"name"` key (not `"site"`/`"app"`)
- `test_blackbird_parser_skips_non_found` — verifies only `FOUND` entries returned
- `test_blackbird_parser_flattens_metadata` — verifies `[{name, value}]` → dict
- `test_blackbird_parser_no_exe_returns_empty` / `no_repo_returns_empty`
- `test_ignorant_detects_registered/ignores_rate_limit/detects_all_three`

Helper `_setup_bb_json(tmp_path, username, entries)` creates the correct results subdirectory path: `tmp_path/results/{safe}_{date}_blackbird/{safe}_{date}_blackbird.json`.

**Total: 71 tests passing** (`python -m pytest tests/ -q`).

---

## 16. SPRINT 5 — Correlation quality fixes + name-search UX (2026-07-01)

> Three bugs diagnosed against a live case (`f44ce9bf…`): name-seed results showing as REJECT singletons, Wayback wasting 15 s on Serper URLs, and Serper page-titles blocking username correlation. All three are now fixed; test count unchanged at 71.

## 16.1 Root-cause diagnosis (live case `f44ce9bf5228435a94c13ae6ed55bfd6`)

Seeds: email `vismayhs@gmail.com` + name `Vismay H S`.

**Entities found:**

| Type | Platform | Value (before fix) |
| --- | --- | --- |
| email_registration | office365.com / spotify.com / twitter.com | `vismayhs@gmail.com` |
| social_account | github | VismayHS (bio, email, name in metadata) |
| web_mention | linkedin | "Vismay HS - Student at PES University, Bengaluru \| LinkedIn" |
| web_mention | linkedin | "Vismay H.S - Ceh \| Aspiring SOC Analyst…" |
| web_mention | instagram | "vismay.hs (@mr_viz_) • Instagram photos and videos" |
| web_mention | instagram | post title (A little escape from reality…) |
| web_mention | instagram | another post title |

**HIGH cluster found:** GitHub + 3 email_registrations — because `"VismayHS"` is a substring of `"vismayhs@gmail.com"` → `username_substring_match` (20 pts) + `exact_email_match` (60 pts) = 80 pts, 2 signals.

**LinkedIn + Instagram: all REJECT singletons.** Three independent bugs caused this:

**Bug A — No `metadata["name"]` on name-seed profiles.** `_scrape_seed` stamped seed value for email/phone/username seeds but NOT for name seeds. So web_mention profiles from a name search had only `metadata = {"snippet": ..., "query": ...}`. The correlation engine found zero name-signal pairs → all REJECT (0 confidence, 0.5 opacity in UI).

**Bug B — Serper result `value` is the page title, not the username.** `_username_signal` compares `a.value` vs `b.value`. LinkedIn web_mention had `value = "Vismay HS - Student at PES University, Bengaluru | LinkedIn"` (the Google result title). Fuzzy ratio against `"VismayHS"` = 23% — far below the 80% threshold. No username signal fires even though the LinkedIn handle and GitHub handle are literally the same string (`vismayhs` / `VismayHS`).

**Bug C — Wayback ran 20 requests on LinkedIn/Instagram/Twitter URLs.** The archive check was designed for Maigret/Sherlock-discovered profile URLs (to check if a deleted account has an archived copy). It ran on every profile's `source_url` — including the 20 Serper result URLs (LinkedIn/Instagram/Twitter). archive.org never has useful copies of those pages, but each request waits the full 15 s timeout. This added ~15 s to every name-search investigation.

**"PES University" in keywords:** The snippet from the LinkedIn Serper result contained "Student at PES University, Bengaluru. AIESEC in India PES University…". The forensics `summarize()` pulls keywords from all entity snippets, so "pes university" was indexed — the system never actually loaded the LinkedIn page; that text came from Google's index of the page.

## 16.2 Fix A — Stamp `metadata["name"]` for name seeds

`backend/pipeline/orchestrator.py`, `_scrape_seed()`:

```python
# was:
if seed_type in {"email", "phone", "username"}:
# now:
if seed_type in {"email", "phone", "username", "name"}:
    for p in profiles:
        if seed_type not in p.metadata:
            p.metadata[seed_type] = value
```

Effect: all Serper `web_mention` profiles from a name search now carry `metadata["name"] = seed_value` (e.g., `"Vismay H S"`). The correlation engine's `exact_name_match` (35 pts) fires between every pair → singletons promoted from REJECT (0 pts, 0.5 opacity) to LOW (35 pts, full opacity, orange accent). The red-herring rule (`LINK_MIN_SIGNALS ≥ 2`) still prevents them from being incorrectly linked — they're unlinked LOW, which is the correct semantics for "found on the web for this name, unconfirmed".

## 16.3 Fix B — Extract social username from URL in SerperScraper

`backend/ingestion/serper_scraper.py` — new helper `_extract_social_username(url, platform)`:

```python
def _extract_social_username(url: str, platform: str) -> str | None:
    path = urlparse(url).path.strip("/")
    parts = [seg for seg in path.split("/") if seg]
    if platform == "linkedin" and len(parts) >= 2 and parts[0] == "in":
        return parts[1]                        # /in/vismayhs → "vismayhs"
    if platform in {"github", "gitlab"} and len(parts) == 1:
        return parts[0]                        # /VismayHS   → "VismayHS"
    if platform in {"instagram", "twitter", "tiktok"} and parts[0] not in _NON_USERNAME_SEGMENTS:
        return parts[0]                        # /mr_viz_/   → "mr_viz_"
    if platform == "reddit" and len(parts) >= 2 and parts[0] in {"u", "user"}:
        return parts[1]
    return None
```

`_NON_USERNAME_SEGMENTS` blocks known non-profile path prefixes: `p`, `reel`, `explore`, `stories`, `watch`, `channel`, `status`, `intent`, etc. So `instagram.com/p/abc123` → `None` (keeps page title), but `instagram.com/mr_viz_/` → `"mr_viz_"`.

In `_run_live`, the profile `value` is set to the extracted username when one is found; the original page title is stored in `metadata["title"]` for display:

```python
username = _extract_social_username(url, platform)
value    = username if username else item.get("title", identifier)
meta     = {"snippet": item.get("snippet"), "query": query}
if username:
    meta["title"] = item.get("title", "")
```

**Combined effect of Fix A + Fix B for LinkedIn ↔ GitHub:**

```
_username_signal("vismayhs", "VismayHS") → exact_match (45 pts)
exact_name_match("Vismay H S", "Vismay H S") → 35 pts
Total: 80 pts, 2 signals → HIGH cluster — LinkedIn joins GitHub+email_registrations ✓
```

The second LinkedIn handle `vismay-h-s` also links via `username_fuzzy_match` (15 pts) + `exact_name_match` (35 pts) = 50 pts, 2 signals → MEDIUM threshold met → linked ✓.

## 16.4 Fix C — Skip Wayback for web_mention profiles

`backend/pipeline/orchestrator.py`, archive-check section:

```python
# was:
seen_account_urls = {p.source_url for p in all_profiles
                     if p.source_url and p.source_url.startswith("http")}
# now:
seen_account_urls = {p.source_url for p in all_profiles
                     if p.source_url and p.source_url.startswith("http")
                     and p.type != "web_mention"}
```

Web-mention profiles come from Serper (Google's current search index). The Wayback check is designed for `social_account` profiles discovered by Maigret/Sherlock/Blackbird where the account may have been deleted but an archived copy exists. Serper results are by definition current live pages — archive.org checks add no value and cost up to 15 s of timeout.

## 16.5 Frontend fixes

**Auto-expand unlinked accounts when no clusters exist** (`frontend/app/cases/[id]/page.js`):

```javascript
// Before: {showUnlinked && unlinked.map(...)}
// After:
{(showUnlinked || (status === "complete" && multi.length === 0)) && unlinked.map(...)}
```

When an investigation completes with zero multi-account clusters (typical for name-only seeds), the "UNLINKED ACCOUNTS" section now opens automatically so results are visible without the user having to hunt for a collapsed section.

**Show page title under username in AccountCard** — when a Serper result has a `metadata.title` (stored by Fix B), it appears as a dim subtitle under the extracted username, so the investigator sees both `vismayhs` (for correlation) and the full title `"Vismay HS - Student at PES University, Bengaluru | LinkedIn"` (for context).

---

## 17. COMPLETE SETUP GUIDE FOR A FRESH GITHUB CLONE

> Read this section if you are setting VERTEX up from scratch on a new machine after pulling from GitHub. Every step is required. Do them in order.

## 17.1 Prerequisites

| Requirement | Version | Why |
| --- | --- | --- |
| Python | 3.10 or later | Tested on 3.10 and 3.13. Do NOT use < 3.10 (match-statement / type-union syntax). |
| Node.js | 18 or later | Next.js 14 frontend. |
| Git | any | Needed to clone Blackbird (not pip-packaged). |
| Docker | optional | Only if you want PhoneInfoga REST server. |

## 17.2 Clone VERTEX and set up the Python environment

```bash
# Clone the VERTEX repo (already done if you're reading this)
git clone <your-repo-url> VERTEX
cd VERTEX

# Create a fresh virtualenv — NEVER reuse a venv from another machine
# (venv stores absolute interpreter paths that break on a different OS/user)
py -3.10 -m venv venv          # Windows (use py launcher to force 3.10+)
python3 -m venv venv           # macOS / Linux

# Activate the venv (every terminal session that touches this project)
venv\Scripts\activate          # Windows PowerShell / cmd
source venv/bin/activate       # macOS / Linux

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
# ↑ this installs: fastapi, uvicorn, httpx, python-jose, bcrypt, reportlab,
#   maigret, sherlock-project, holehe, socialscan, waybackpy, vaderSentiment,
#   truststore, thefuzz, scikit-learn, imagehash, pillow, telethon, praw,
#   python-dotenv, and their transitive deps.

# Install test tools (NOT in requirements.txt — dev only)
pip install pytest pytest-asyncio
```

## 17.3 Install ignorant (phone registration checker)

`ignorant` is pip-packaged and has a console-script entry point — install it the same way as any other package:

```bash
pip install ignorant
```

Verify it works:

```bash
ignorant +14155552671
# should print: [+] instagram.com  or  [-] instagram.com  etc.
```

`IgnorantScraper` in `backend/ingestion/phone_scrapers.py` calls this CLI automatically. If it is absent the scraper returns `[]` without crashing.

## 17.4 Install Blackbird (username / email enumerator — NOT pip-packaged)

Blackbird is not on PyPI. You must clone it to a **separate directory outside the VERTEX repo**, then tell VERTEX where it lives via the `BLACKBIRD_PATH` env var.

```bash
# Clone Blackbird — pick any location you like outside VERTEX/
git clone https://github.com/p1ngul1n0/blackbird C:\tools\blackbird   # Windows
git clone https://github.com/p1ngul1n0/blackbird ~/tools/blackbird    # macOS/Linux

# Install Blackbird's dependencies into the VERTEX venv
# (same venv — Blackbird is invoked as a subprocess via the venv's python)
pip install -r C:\tools\blackbird\requirements.txt    # Windows
pip install -r ~/tools/blackbird/requirements.txt     # macOS/Linux
```

**Version conflict fix (required):** Blackbird pins older versions of three packages than Maigret needs. After the install above, upgrade them:

```bash
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"
```

**Create the `.bat` wrapper (Windows only):** `asyncio.create_subprocess_exec` cannot run `.py` files directly on Windows; it needs a wrapper script. Create `venv\Scripts\blackbird.bat` with this content (replace both paths with your actual absolute paths):

```bat
@echo off
"C:\path\to\VERTEX\venv\Scripts\python.exe" "C:\tools\blackbird\blackbird.py" %*
```

On macOS/Linux no wrapper is needed — `blackbird.py` is called directly with the venv's python.

**Download the site list (one-time):** Blackbird's database (`wmn-data.json`) is not included in the repo. Run it once without `--no-update` from inside the Blackbird directory to download it:

```bash
cd C:\tools\blackbird          # must be IN the Blackbird dir (it uses os.getcwd())
python blackbird.py -u torvalds   # triggers download then scans; ~87 results expected
cd -                           # back to VERTEX/
```

**Tell VERTEX where Blackbird is (add to `.env`):**

```
BLACKBIRD_PATH=C:\tools\blackbird
```

`resolve_tool()` in `base_module.py` searches `venv/Scripts/*.bat` automatically, so once `blackbird.bat` is in place and `BLACKBIRD_PATH` is set, the scraper works without any further config.

## 17.5 Create your `.env` file

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Edit `.env` and fill in every value:

```ini
# ─── REQUIRED for a strong demo ──────────────────────────────────────────────
SERPER_API_KEY=          # Google search backbone — get from serper.dev (free 2 500 queries)
GITHUB_TOKEN=            # GitHub REST API — no scopes needed, free at github.com/settings/tokens
NVIDIA_API_KEY=          # LLM entity-extraction + explanations — integrate.api.nvidia.com

# ─── REQUIRED for your JWT to be secure ──────────────────────────────────────
JWT_SECRET=              # generate: python -c "import secrets; print(secrets.token_hex(32))"
# ↑ anyone with this value can forge login tokens — NEVER commit it

# ─── REQUIRED: where Blackbird is cloned ─────────────────────────────────────
BLACKBIRD_PATH=C:\tools\blackbird    # Windows path to blackbird clone

# ─── OPTIONAL: improves coverage, fails safely if absent ─────────────────────
HIBP_API_KEY=            # haveibeenpwned.com Core plan (~$4/mo) — email breach lookups
NUMVERIFY_KEY=           # numverify.com free tier — phone carrier/country/line-type
TELEGRAM_API_ID=         # my.telegram.org → "API development tools"
TELEGRAM_API_HASH=       # same as above
REDDIT_CLIENT_ID=        # reddit.com/prefs/apps → "script" app — avoids 403 from VPN/datacenter IPs
REDDIT_CLIENT_SECRET=    # same as above
REDDIT_USER_AGENT=VERTEX-OSINT/1.0 (CIDECODE)

# ─── DATA MODE ────────────────────────────────────────────────────────────────
DATA_MODE=live           # "live" for real scraping; "mock" for offline dev/demo without network
```

**Security note:** `.env` is gitignored. If a key was ever pasted in a chat, screenshot, or committed to git, rotate it in each provider's console before demo day.

## 17.6 Initialise the database and create the admin account

```bash
python -m backend.database          # creates cidecode.db with 6 tables + audit_ledger.chain_hash
python -m scripts.create_admin      # creates user admin / password vertex2026
```

Change the admin password before any real use (`scripts/create_admin.py` — just re-run with different values, or update the DB directly).

## 17.7 Set up and run the frontend

```bash
cd frontend

# Create the env file (there is NO .env.local.example — create it directly)
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm install
npm run dev                    # http://localhost:3000  (3001 if 3000 is in use)
```

CORS already allows both 3000 and 3001 in `backend/main.py`, so either port works.

## 17.8 Run the backend

Open a **separate terminal** (or the same if frontend is backgrounded):

```bash
# From the VERTEX/ root, with venv active:
uvicorn backend.main:app --reload --port 8000
# Interactive API docs: http://localhost:8000/docs
```

On Windows, if `uvicorn` reports "port already in use" after a hard kill, the child process may still hold the socket:

```powershell
netstat -ano | findstr :8000   # find the PID
taskkill /F /PID <pid>
```

## 17.9 Smoke test the install

```bash
# Run the test suite — all 71 tests must pass
python -m pytest tests/ -q

# Quick offline demo (no network, no keys)
# In .env: DATA_MODE=mock  → restart uvicorn → create a case in the UI
```

If any tests fail, check:

1. `venv` is activated (`which python` / `where python` must point inside `venv/`).
2. `pip install -r requirements.txt` completed without errors.
3. `pytest pytest-asyncio` are installed (not in `requirements.txt`).
4. Blackbird dependency conflicts were resolved (step §17.4 upgrade command).

## 17.10 How the external tools wire into VERTEX

This is the part that catches people. VERTEX relies on four CLI tools that are either installed as console-script entry points in the venv (maigret, sherlock, holehe, socialscan, ignorant) or invoked as subprocesses via a wrapper (Blackbird). Here is exactly how each one is found at runtime:

```text
resolve_tool("maigret")
  → shutil.which("maigret")             ← found via PATH (venv/Scripts/maigret.exe or bin/maigret)
  → os.path.join(sys.prefix, "Scripts", "maigret.exe")   ← fallback if PATH not set
  → returns full path or None

resolve_tool("blackbird")
  → shutil.which("blackbird")           ← probably not on PATH
  → os.path.join(sys.prefix, "Scripts", "blackbird.exe") ← not there on Windows
  → os.path.join(sys.prefix, "Scripts", "blackbird.bat") ← FOUND (if you created it in §17.4)
  → returns "venv/Scripts/blackbird.bat"

_blackbird_repo()
  → os.environ.get("BLACKBIRD_PATH")   ← from .env
  → returns "C:\tools\blackbird"

subprocess is then: ["cmd", "/c", "venv/Scripts/blackbird.bat", "-u", username, "--json", "--no-update", "--timeout", "15"]
cwd = "C:\tools\blackbird"            ← CRITICAL: Blackbird uses os.getcwd() for data paths
env["PYTHONIOENCODING"] = "utf-8"     ← CRITICAL: prevents cp1252 crash on Windows console output
```

If Blackbird returns nothing:

1. Check `BLACKBIRD_PATH` is set in `.env`.
2. Check `venv/Scripts/blackbird.bat` exists and the paths inside it are correct.
3. Check `C:\tools\blackbird\data\wmn-data.json` exists (run §17.4 download step).
4. Run `python -m pytest tests/test_step0_tools.py -v` — those 12 tests exercise the parser and resolve logic without a real network call.

## 17.11 What each seed type does and which tools run

| Seed type | Tools invoked | Profiles returned |
| --- | --- | --- |
| `username` | Maigret (3 000+ sites), Sherlock (400+ sites), Blackbird (680 sites), Socialscan (10 platforms), Reddit, Telethon, GitHub API, Serper | social_account per platform found + web_mention from Google |
| `email` | HIBP, XposedOrNot, Holehe, Blackbird-email, GitHub API, Serper | email_registration per service + breach records |
| `phone` | NumVerify, PhoneInfoga, ignorant, Serper | phone_registration per carrier/platform |
| `name` | Serper×3 (`site:linkedin.com/in`, `site:instagram.com`, `site:twitter.com`) | web_mention per result; handles extracted from URLs for correlation |
| `upi` | UPI parser, Serper | upi_account + web_mention |
| `url` | URLScraper (handle extraction), Wayback | url_reference + archive records |
| `face` | none currently | (pHash matches are done against photos collected from other seeds) |

**False-positive filter (username tools only):** Maigret, Sherlock, and Blackbird each run a random 20-char hex control username in parallel. Sites that fire for the control are "broken detectors" and are excluded from real results. Cached 6 h in `reports/false_positive_sites.json`. Socialscan and ignorant have no FP filter (they use real registration-flow checks, not HTTP heuristics).

## 17.12 Correlation signals reference

| Signal | Points | Fires when |
| --- | --- | --- |
| exact_phone_match | 60 | Last 10 digits of phone match |
| exact_email_match | 60 | Normalised email strings match |
| exact_upi_match | 60 | UPI IDs match |
| username_exact_match | 45 | Normalised `value` strings are identical |
| username_substring_match | 20 | One is a substring of the other |
| username_fuzzy_match | 15 | thefuzz ratio ≥ 80 (difflib fallback) |
| exact_name_match | 35 | `metadata["name"]` values match exactly |
| fuzzy_name_match | 20 | Name fuzzy ratio ≥ 80 |
| location_overlap | 15 | `metadata["location"]` values match/contain each other |
| profile_photo_phash | 35 | Perceptual-hash Hamming distance < 8 OR same photo URL |
| posting_hours_overlap | 15 | Jaccard index of active hours > 0.6 |
| stylometry_cosine | 20 | Char n-gram + function-word cosine > 0.6 |
| breach_co_occurrence | 18 | Shared breach (rare or ≥ 2 shared; mega-breaches excluded) |
| bio_keyword_overlap | 12 | ≥ 2 non-stopword bio tokens in common |

**Red-herring rule (hard-coded, DO NOT CHANGE):** linking requires BOTH `num_signals ≥ 2` AND `raw_points ≥ 50`. A single signal — even a 60-pt phone match — is flagged at LOW but never merges accounts into a cluster. This is the system's primary defensive claim for court use.

**Tiers:** HIGH > 75 pts | MEDIUM 50–75 | LOW 25–50 | REJECT < 25

## 17.13 Known limitations and honest non-features

- **Maigret/Sherlock/Blackbird "false positives" that slip through the control probe:** ~6 sites whose broken detection uses heuristics that happen to fire on realistic-looking usernames but not on the 20-char hex control. They appear as LOW singletons and are clearly not linked.
- **Instagram / LinkedIn / Twitter profiles in name searches:** The system finds them via Serper (Google's index) and extracts the handle from the URL for correlation. It does NOT log in, call private APIs, or scrape beyond what is publicly indexed.
- **Telegram:** The Telethon scraper works only for public channels/groups and requires the API credentials from §17.5. It cannot resolve arbitrary phone numbers to users.
- **Face/photo seed:** Accepted as a seed type but no matcher runs on it. Profile photos discovered via other seeds are pHash-compared to each other.
- **Reddit:** Without `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`, Reddit returns 403 from datacenter/VPN IPs. Set up a free "script" app at reddit.com/prefs/apps.
- **PhoneInfoga:** Requires a local Docker container running the PhoneInfoga REST server on port 5000. `docker pull sundowndev/phoneinfoga:latest && docker run -p 5000:5000 sundowndev/phoneinfoga serve`.
- **UPI name lookup:** Returns only the registered name from the UPI payment rail — it does not expose account numbers or bank details.

# 18. SPRINT 6 & THURSDAY HOTFIXES (2026-07-02)

## 18.1 Hotfixes on branch `ashwin-thurs` (Commit `cd9ac0b`)

1. **Seed Auto-Correction & Name-Search Hardening (`backend/pipeline/orchestrator.py`):**
   - **Auto-Correction:** If a user inputs a full name containing spaces (e.g., `"ashwin harish"`) while the UI dropdown defaults to `username`, Step 1 automatically converts `seed["type"] = "name"`.
   - **Targeted Permutations:** Username permutation expansion (generating `ashwinharish`, `aharish`, etc.) is guarded to only run for single-token usernames without spaces. For full-name searches, the pipeline goes directly to Serper site searches (`site:linkedin.com/in`, `site:github.com`, `site:instagram.com`, `site:twitter.com`) to find authenticated profiles first.
   - **Empty Metadata Filter:** Added `_has_content_metadata` post-enrichment check in `orchestrator.py` to discard profiles with only structural boilerplate fields and zero actual user profile data.

2. **Numeric/Short Suffix Variant Guard (`backend/ingestion/variants.py`):**
   - For usernames like `"ash29_03"`, the first-initial rule `toks[0][0] + toks[-1]` previously generated `"a03"`, flooding results with false positives. Restricted the rule to only apply when `toks[-1]` is not digits and has length $\ge 3$.

3. **Scraper Timeout Optimization & UI Polish:**
   - Reduced CLI subprocess timeouts across **Sherlock** (60s), **Blackbird** (60s), and **Maigret** (90s) to fail fast on unresponsive target sites.
   - Restored real-time scanning progress feed (`logLines`) in the left panel of `frontend/app/cases/[id]/page.js` while a case is running.
   - Middle panel now displays the interactive `<NetworkGraph />` correlation chart by default when no card is selected, smoothly transitioning to Account Details upon clicking a node, with an **✕ Close Details** button.

## 18.2 Verification & Test Status
- All **76 automated unit and integration tests** passing cleanly (`pytest tests/`).
- Frontend production build (`npm run build`) compiles with zero TypeScript or bundling errors.
