# VERTEX - LLM Handover & Context Report

This document is intended for any future LLM or developer picking up the `VERTEX` project. It provides a complete summary of the architecture, recent critical upgrades, known issues, and pending tasks.

---

## 1. Project Overview & Architecture
VERTEX is an automated SOCMINT / OSINT investigation pipeline designed to map digital footprints. 
- **Frontend:** Next.js (React), running by default on port `3001` (because `3000` is often occupied). Connects to backend via `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- **Backend:** Python (FastAPI). Uses `sqlite3` (`cidecode.db`) for storage. 
- **Core Engine Flow:**
  1. **Ingestion:** Scraping modules (`backend/ingestion/`) hit APIs and CLIs (Maigret, Blackbird, etc.) to produce `RawProfile` objects.
  2. **Orchestrator:** `backend/pipeline/orchestrator.py` manages a highly-parallelized fan-out cascade.
  3. **LLM Extraction:** Llama-3 (via Groq) reads the unstructured bios/metadata to extract hidden phone numbers, emails, or usernames.
  4. **Correlation:** `backend/correlation/correlation_engine.py` compares all profiles mathematically, assigning points based on `SIGNAL_WEIGHTS`.
  5. **Scoring:** `backend/scoring/scoring_engine.py` groups profiles into `Clusters` if they exceed the 50-point MEDIUM threshold, obeying the OSINT "Red-Herring" rule (requiring ≥2 distinct signals to link).

---

## 2. Recent Critical Upgrades (What Was Just Done)
A massive overhaul was applied to fix deadlocks and boost the accuracy of the correlation graphs:

### 2.1 Concurrency Fixes (Orchestrator Deadlocks)
- **The Bug:** Previously, the orchestrator would fan-out the initial seeds but then iterate through cascading URL targets sequentially, causing endless hangs on targets with many links.
- **The Fix:** Completely rewrote `orchestrator.py` to use `asyncio.gather` for URL cascading and LLM extraction phases. The system now footprint-scans targets across 15+ websites instantly in parallel.

### 2.2 Correlation Mathematics Overhaul (Breaking the 30/100 Cap)
- **The Bug:** The system was hard-capping clusters at 30 points (LOW Tier) because it lacked multi-signal triangulation (like matching a username *and* a real name).
- **The Fix:** 
  - Added new signals to `correlation_engine.py`: `exact_name_match` (+35), `fuzzy_name_match` (+20), and `location_overlap` (+15).
  - Boosted baseline high-confidence weights: `username_exact_match` (45 points), `exact_phone_match` (60 points), `exact_email_match` (60 points).
- **Metadata Extraction:** Updated `github`, `telethon`, `maigret`, and `reddit` scrapers in `backend/ingestion/` to proactively pull "Real Name" and "Location" into the `metadata` dictionary so the correlation engine can read them.

### 2.3 Auth, CORS, and Git Fixes
- **Login Fix:** Force-reset the `admin` password to `vertex2026` in `cidecode.db`.
- **CORS Fix:** Updated `backend/main.py` CORS middleware to explicitly allow `http://localhost:3001` to fix network rejections.
- **Git State:** Recovered from a messy ghost branch. Re-created the `ashwin` branch from the correct upstream, stashed/popped all the upgrades, and force-pushed to the remote.

---

## 3. Pending Tasks & Handover Instructions

For the next LLM or engineer continuing this work, here are the outstanding items to address:

### A. API Keys & Missing Dependencies
- **HaveIBeenPwned:** `HIBPScraper` is functional but currently skipping because the key is a dummy. Update `.env`.
- **Numverify:** API key missing.
- **User-Scanner:** The `user-scanner` Python CLI was installed via pip to `~/Library/Python/3.12/bin/user-scanner`. If the backend throws a "command not found" error, ensure that directory is added to the system `PATH` before starting `uvicorn`.

### B. Correlation Engine Tuning
- **Stylometry:** The `stylometry_cosine` signal in the correlation engine requires `scikit-learn` to be installed. If not present, the system safely ignores stylometry.
- **LLM Prompting:** The `LLMClient` in `backend/llm/llm_client.py` does a decent job extracting clues, but could be heavily optimized with few-shot prompting to better separate real names from generic bio text.

### C. Scaling
- SQLite `cidecode.db` works fine for a hackathon, but concurrency issues (locked databases) may occur if many users hit the FastAPI endpoints simultaneously. Consider migrating `backend/database.py` to PostgreSQL. 

### Start Commands
```bash
# Terminal 1: Backend
cd backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm run dev 
# (UI will start on localhost:3001 if 3000 is blocked)
```
