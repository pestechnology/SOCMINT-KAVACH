# VERTEX - Comprehensive Technical Handover Document

> ⚠️ **SUPERSEDED — DO NOT USE AS GROUND TRUTH (as of 2026-07-01).**
> This document describes an **older, divergent fork** of VERTEX and conflicts with the current
> codebase in major ways: it references **Groq/Llama-3** (current is **NVIDIA Cloud**), a
> **`POST /investigate`** endpoint (current API is `/auth/*` and `/cases/*`), **different signal
> weights** (60/45/35 vs. the current set in `correlation_engine.py`), `reddit`/`telethon` scrapers,
> macOS-specific paths (`/Users/ashwinharish/...`), and an emergency `vismay_v2` branch protocol.
> **The current, authoritative source is [`../context.md`](../context.md) — read it (especially
> Section 11) instead.** The notes below are retained only for historical reference.

---

## 1. System Architecture & Tech Stack

**VERTEX** is an advanced SOCMINT / OSINT pipeline that automatically ingests a target identifier (name, email, phone, username), cascades across multiple intelligence databases, uses an LLM to extract hidden identifiers from unstructured text, and uses a deterministic mathematical graph to correlate profiles into distinct human identities.

### Tech Stack
- **Frontend Framework:** Next.js 14 (React, TypeScript, TailwindCSS)
- **Backend Framework:** Python (FastAPI, Uvicorn)
- **Concurrency:** `asyncio` (Crucial for scraping speed)
- **Database:** SQLite3 (`cidecode.db`)
- **LLM Engine:** Llama-3 (via Groq API)
- **Orchestration:** Directed graph fan-out cascade

### Core Ports & Networking
- **Frontend Server:** Runs on `http://localhost:3001` (or `3000`).
- **Backend Server:** Runs on `http://localhost:8000`.
- **CORS Configuration:** `backend/main.py` explicitly allows `http://localhost:3001` via `CORSMiddleware`. Do NOT remove this, or the Next.js frontend will fail to fetch `API/investigate`.

---

## 2. Deep Dive: Codebase Structure & Data Flow

When a user submits a search via the frontend, the data follows this exact pipeline path in the backend:

### Step 1: `backend/main.py`
- Exposes `POST /investigate` taking an `InvestigateRequest` (`type`, `value`).
- Validates the `IdentifierType` enum.
- Dispatches the request to `run_investigation()` in the orchestrator.

### Step 2: Orchestrator (`backend/pipeline/orchestrator.py`)
- **Function:** `run_investigation(seed: Identifier)`
- **Mechanism:** Implements a highly concurrent loop using `asyncio.gather`. 
- **The Cascade:**
  1. It takes the `seed` and passes it to every applicable `BaseDataSource` (Scraper).
  2. The scrapers return `RawProfile` objects.
  3. The Orchestrator passes the `RawProfile.metadata` into the `LLMClient` to extract *new* seeds (e.g. an Instagram bio might contain a Twitter handle).
  4. The newly extracted seeds are recursively fed back into the scrapers.
- **Critical Fix:** Previously, this file used a `for target in targets:` sequential loop which caused severe deadlocks on high-yield targets. It was rewritten to fan out asynchronously.

### Step 3: Ingestion Engine (`backend/ingestion/`)
All scrapers inherit from `BaseDataSource` in `base_module.py`.
- **`maigret_scraper.py`**: Runs the CLI tool `maigret`. We updated it to map `ids.get("fullname")` directly to the `name` key in metadata. Uses `--no-recursion` flag.
- **`github_scraper.py`**: Hits `api.github.com/users/{username}`. Explicitly extracts `name`, `location`, `email`, `bio`.
- **`reddit_scraper.py`**: Hits `reddit.com/user/{username}/about.json`. Extracts the `subreddit.title` as the `name` key.
- **`telethon_scraper.py`**: Requires Telegram API Hash. Concatenates `user.first_name` + `user.last_name` into the `name` key.
- **`phone_scrapers.py`**: Contains `NumverifyScraper` and `TruecallerScraper` logic.

### Step 4: Correlation Engine (`backend/correlation/correlation_engine.py`)
- **Function:** `correlate_profiles(profiles)`
- **Mechanism:** Takes a flat array of `RawProfile` objects and compares every profile against every other profile $O(N^2)$.
- **The Algorithm:** It calls `_pair_signals(ma, mb)` to determine mathematical overlap.
- **Core Weights (CRITICAL):**
  - `exact_phone_match` / `exact_email_match` = **60 points**
  - `username_exact_match` = **45 points**
  - `exact_name_match` = **35 points**
  - `fuzzy_name_match` = **20 points**
  - `location_overlap` = **15 points**

### Step 5: Scoring & Clustering (`backend/scoring/scoring_engine.py`)
- **Function:** Groups the correlated profiles into distinct `Clusters`.
- **The "Red Herring" Rule:** In OSINT, a single signal (e.g., matching username only) is NOT enough to merge two profiles. To clear the **MEDIUM (50 points)** threshold, a cluster MUST have ≥2 matching signals (e.g., `username_exact_match` [45] + `location_overlap` [15] = 60 points).
- **Tiers:** `< 50` (REJECT/LOW), `50 - 75` (MEDIUM), `> 75` (HIGH).
- **Output:** The Engine outputs a list of strings (`_SIGNAL_PHRASES`) explaining exactly *why* the cluster was grouped, ensuring court-admissibility for the CDI.

---

## 3. Database Schema (`cidecode.db`)
The system uses SQLite. To query it: `sqlite3 cidecode.db "SELECT * FROM cases;"`
- **Table `cases`**: `case_id`, `title`, `status`, `created_at`.
- **Table `clusters`**: Stores the output of the scoring engine (`tier`, `confidence_score`, `explanation`).
- **Table `users`**: Contains auth credentials. 
  - **Note:** The `admin` password was manually reset in the DB to `vertex2026`.

---

## 4. Pending Tasks & Unfinished Integrations

When the next LLM takes over, these are the immediate technical debts that must be resolved:

### Missing API Keys
1. **HaveIBeenPwned (`HIBPScraper`)**: Currently skipping real network requests because the `.env` key is a dummy. Needs a paid API key to check data breaches.
2. **Numverify (`NumverifyScraper`)**: The API key is missing.
3. **Telegram (`TelethonScraper`)**: Requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in the `.env` to execute live Telegram OSINT.

### Missing System Dependencies
1. **User-Scanner (`user_scanner_scraper.py`)**: The `user-scanner` Python package was installed in `/Users/ashwinharish/Library/Python/3.12/bin/`. If `uvicorn` throws a `subprocess.Popen` error, it is because this directory is not in the system `$PATH`. 
   - *Fix:* Ensure `export PATH="$PATH:/Users/ashwinharish/Library/Python/3.12/bin"` is run before starting the backend.
2. **Scikit-Learn (Stylometry)**: `correlation_engine.py` looks for `sklearn` to compute `stylometry_cosine` distance. It gracefully degrades if missing, but should be installed for linguistic analysis.

### Prompt Engineering Debt
- The file `backend/llm/llm_client.py` uses Groq (Llama-3). It relies on zero-shot extraction. 
- *Next Step:* The prompt should be upgraded to use few-shot JSON schema enforcement to stop the LLM from hallucinating handles that don't actually exist in the bio text.

---

## 5. Quick-Start Commands

### Backend
```bash
# Ensure Python bin path is loaded for Maigret & User-Scanner
export PATH="$PATH:/Users/ashwinharish/Library/Python/3.12/bin"
cd backend
source ../venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Git Recovery 
If the `ashwin` branch gets corrupted again due to upstream conflicts, the emergency recovery protocol is:
```bash
git checkout vismay_v2
git branch -D ashwin
git checkout -b ashwin
git push -f origin ashwin
```
