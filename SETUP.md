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
> Use **Python 3.10** (the project's target). On Windows: `py -3.10 -m venv venv`.
> Do **not** reuse a `venv` created on another machine — the interpreter path is absolute and won't resolve.

```bash
python -m venv venv
# Windows:  venv\Scripts\activate     |  macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio    # NOTE: the test suite needs these; they are NOT in requirements.txt
# maigret is already pinned in requirements.txt (no separate install needed)

# Optional OSINT tools that install separately:
# Blackbird:  git clone https://github.com/p1ngul1n0/blackbird && pip install -r blackbird/requirements.txt
# PhoneInfoga: docker pull sundowndev/phoneinfoga:latest   (then run its REST server on :5000)
# ignorant:   pip install ignorant
```

## 4. Run the backend
```bash
python -m backend.database          # creates/upgrades cidecode.db (6 tables; adds audit_ledger.chain_hash)
python -m scripts.create_admin      # creates admin / vertex2026
uvicorn backend.main:app --reload --port 8000   # API on http://localhost:8000
```
Open http://localhost:8000/docs for the interactive API.

## 4b. Run the frontend (Next.js + Tailwind)
```bash
cd frontend
# There is NO .env.local.example — create the file directly:
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev                          # UI on http://localhost:3000 (3001 if 3000 is busy)
```
> CORS already allows ports 3000 and 3001, so either frontend port works against the backend.

### Troubleshooting: "port already in use"
`uvicorn --reload` runs as a parent + child process. If the parent is hard-killed, the child can be
orphaned and keep the socket — and Windows `netstat` still shows the socket under the **dead parent
PID**, so `taskkill /PID <parent>` reports "not found" while the port stays busy. Find the real owner
and the live child:
```bash
netstat -ano | findstr :8000        # shows the PID holding the port
# if taskkill on that PID says "not found", kill the live python child whose parent is that PID
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

Seed types: `username`, `email`, `phone`, `upi`, `name`, `url`, `face` (`face` is accepted but has no matcher — it returns nothing).

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
**Built & tested (48 pytest tests passing):** config, DB, auth, cases, data-source interface,
mock, correlation, scoring (red-herring rule), LLM client (with fallbacks), orchestrator, audit
ledger (hash chain — now self-sealing every row including the last; see `context.md` §11), BSA-63
PDF. Live scrapers: GitHub ✅, Serper, HIBP, Maigret, UPI, phone (ignorant/PhoneInfoga).
**Frontend:** Next.js + Tailwind dashboard (login, case list, new-investigation form, 3-panel
results with sigma.js graph + vis-timeline, streaming, PDF download) — `npm run build` passes.

> For the full list of 2026-07-01 fixes (ledger self-seal, auth status codes, subprocess
> reaping, PDF escaping, frontend polling/graph), see **`context.md` Section 11**.

**Pending (optional breadth):** remaining scrapers (Blackbird, socialscan, Reddit JSON,
Telethon, Wayback, pHash, Playwright-based FB/UPI-name lookups). All follow the same
`BaseDataSource` pattern — add a class, drop it into `SEED_TOOL_MAP` in the orchestrator.

## 9. Legal
See [LEGAL_VERIFICATION.md](LEGAL_VERIFICATION.md). All BSA-63 claims verified; the
two wrong citations from the original brief (PMLA §12, CPCR §12) are replaced with
BNSS §94 and POCSO §23 / JJ §74. Still get a qualified advocate to co-sign before July 4.
