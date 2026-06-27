# VERTEX — Setup & Run Guide

SOCMINT/OSINT suspect-profiling system for CIDECODE 2026.

## 1. Prerequisites
- Python 3.10+
- Node 18+ (for the frontend, once built)
- (Optional) Docker — for PhoneInfoga

## 2. Secrets
```bash
cp .env.example .env
# edit .env and fill in your REAL keys (this file is gitignored, never committed)
# generate a JWT secret:
python -c "import secrets; print(secrets.token_hex(32))"
```
Required for a strong demo: `SERPER_API_KEY`, `GITHUB_TOKEN`, `NVIDIA_API_KEY`.
Optional: `HIBP_API_KEY`, `TELEGRAM_API_ID/HASH`, `NUMVERIFY_KEY`.

> ⚠ If any key was ever pasted into chat/screenshots, ROTATE it before use.

## 3. Install
```bash
python -m venv venv
# Windows:  venv\Scripts\activate     |  macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# OSINT tools that install separately:
pip install maigret           # primary username scraper
# Blackbird:  git clone https://github.com/p1ngul1n0/blackbird && pip install -r blackbird/requirements.txt
# PhoneInfoga: docker pull sundowndev/phoneinfoga:latest   (then run its REST server on :5000)
# ignorant:   pip install ignorant
```

## 4. Run the backend
```bash
python -m backend.database          # creates cidecode.db with 6 tables
uvicorn backend.main:app --reload   # API on http://localhost:8000
```
Open http://localhost:8000/docs for the interactive API.

## 4b. Run the frontend (Next.js + Tailwind)
```bash
cd frontend
cp .env.local.example .env.local    # points at http://localhost:8000
npm install
npm run dev                          # UI on http://localhost:3000
```
Screens: login → case list → new investigation (seed dropdown) → 3-panel results
(accounts | sigma.js connection map | details) → timeline → "Generate evidence report".
Results stream in by polling while the investigation runs.

## 5. Quick smoke test (no network needed — mock mode)
```bash
# set DATA_MODE=mock in .env, then:
python -m scripts.seed_demo_case    # builds a full demo case, prints the case_id
```
Then generate the court PDF for that case_id:
```bash
python -c "from backend.report.bsa63_generator import generate_report; print(generate_report('PASTE_CASE_ID'))"
```

## 6. The demo flow (API)
1. `POST /auth/register` `{username, password}` → returns a token
2. `POST /cases` `{title, seeds:[{type,value}]}` (Bearer token) → returns `case_id`, starts the investigation in the background
3. Poll `GET /cases/{case_id}/results` → `status` goes `pending → running → complete`; entities/clusters stream in
4. `GET /cases/{case_id}/report` → downloads the BSA-63 PDF

Seed types: `username`, `email`, `phone`, `upi`, `name`, `face`.

## 7. The two demo-winning moments (both work today, both offline-safe)
- **Red-herring rejection** — a username-only match is shown as `LOW — not linked`, never merged.
- **Hash verification** — recompute any artifact's SHA-256 and match it against the PDF:
  ```bash
  # Windows PowerShell:
  Get-FileHash .\reports\artifacts\<case_id>\<artifact>.json -Algorithm SHA256
  # macOS/Linux:
  shasum -a 256 reports/artifacts/<case_id>/<artifact>.json
  ```

## 8. What's built vs. pending
**Built & tested:** config, DB, auth, cases, data-source interface, mock, correlation,
scoring (red-herring rule), LLM client (with fallbacks), orchestrator, audit ledger
(hash chain), BSA-63 PDF. Live scrapers: GitHub ✅, Serper, HIBP, Maigret, UPI, phone
(ignorant/PhoneInfoga). **Frontend:** Next.js + Tailwind dashboard (login, case list,
new-investigation form, 3-panel results with sigma.js graph + vis-timeline, streaming,
PDF download) — `npm run build` passes.

**Pending (optional breadth):** remaining scrapers (Blackbird, socialscan, Reddit JSON,
Telethon, Wayback, pHash, Playwright-based FB/UPI-name lookups). All follow the same
`BaseDataSource` pattern — add a class, drop it into `SEED_TOOL_MAP` in the orchestrator.

## 9. Legal
See [LEGAL_VERIFICATION.md](LEGAL_VERIFICATION.md). All BSA-63 claims verified; the
two wrong citations from the original brief (PMLA §12, CPCR §12) are replaced with
BNSS §94 and POCSO §23 / JJ §74. Still get a qualified advocate to co-sign before July 4.
