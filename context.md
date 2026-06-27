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
