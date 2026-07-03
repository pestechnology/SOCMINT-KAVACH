# VERTEX — Setup & Run Guide

SOCMINT/OSINT suspect-profiling system for CIDECODE 2026.

## 1. Prerequisites

- Python 3.10 or later (tested on 3.10 and 3.13)
- Node 18+ (for the frontend)
- Git (to clone Blackbird — not on PyPI)
- Docker (optional, only for PhoneInfoga)

## 2. Secrets

```bash
cp .env.example .env
# edit .env and fill in your REAL keys (this file is gitignored, never committed)
# generate a JWT secret:
python -c "import secrets; print(secrets.token_hex(32))"
```

Required for a strong demo: `SERPER_API_KEY`, `GITHUB_TOKEN`, `NVIDIA_API_KEY`, `JWT_SECRET`.

Optional: `HIBP_API_KEY`, `TELEGRAM_API_ID/HASH`, `NUMVERIFY_KEY`, `REDDIT_CLIENT_ID/SECRET`,
`DEHASHED_EMAIL`/`DEHASHED_API_KEY`, `LEAKCHECK_API_KEY` (deeper breach coverage — the
pipeline runs identically, just with fewer breach hits, if these are unset).

> If any key was ever pasted into chat/screenshots, ROTATE it before use.

## 3. Install

> Python 3.10+ required. On Windows: `py -3.10 -m venv venv`.
> Do **not** reuse a `venv` created on another machine — the interpreter path is absolute.

```bash
python -m venv venv
# Windows:  venv\Scripts\activate     |  macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio    # test deps (NOT in requirements.txt)
# maigret, sherlock-project, holehe, socialscan already in requirements.txt

# Face-matching models (one-time, ~37 MB, NOT committed to git — see
# backend/ingestion/photo_enrich.py's docstring for why OpenCV's YuNet+SFace models
# were chosen over face_recognition/dlib). Optional: if this is skipped, face
# matching is simply disabled — every other signal is unaffected.
python backend/scripts/download_face_models.py

# ignorant (phone registration checker — pip-packaged):
pip install ignorant

# Blackbird (username/email enumerator — NOT pip-packaged, must be cloned):
git clone https://github.com/p1ngul1n0/blackbird C:\tools\blackbird
pip install -r C:\tools\blackbird\requirements.txt
# Fix version conflicts (Blackbird pins older aiohttp/multidict/reportlab than maigret):
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"

# Create the .bat wrapper so resolve_tool() can find Blackbird on Windows:
# Create venv\Scripts\blackbird.bat with this content (adjust both paths):
#   @echo off
#   "C:\path\to\VERTEX\venv\Scripts\python.exe" "C:\tools\blackbird\blackbird.py" %*

# Download Blackbird's site list (one-time — run from inside the Blackbird dir):
cd C:\tools\blackbird
python blackbird.py -u torvalds    # triggers wmn-data.json download
cd -

# Add to .env:
#   BLACKBIRD_PATH=C:\tools\blackbird

# PhoneInfoga (optional):
#   docker pull sundowndev/phoneinfoga:latest
#   docker run -p 5000:5000 sundowndev/phoneinfoga serve
```

## 4. Run the backend

```bash
python -m backend.database          # creates/upgrades cidecode.db (6 tables)
python -m scripts.create_admin      # creates admin / vertex2026
uvicorn backend.main:app --reload --port 8000   # API on http://localhost:8000
```

Open `http://localhost:8000/docs` for the interactive API.

## 5. Run the frontend (Next.js + Tailwind)

```bash
cd frontend
# There is NO .env.local.example — create the file directly:
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev     # UI on http://localhost:3000 (3001 if 3000 is busy)
```

CORS already allows ports 3000 and 3001.

### Troubleshooting: "port already in use"

`uvicorn --reload` runs as a parent + child process. If the parent is hard-killed, the child
can be orphaned. Find the real owner:

```powershell
netstat -ano | findstr :8000   # shows the PID holding the port
taskkill /F /PID <pid>
```

## 6. Quick smoke test (no network needed — mock mode)

```bash
# Set DATA_MODE=mock in .env, then:
python -m scripts.seed_demo_case    # builds a full demo case, prints the case_id
```

Then generate the court PDF for that case_id:

```bash
python -c "from backend.report.bsa63_generator import generate_report; print(generate_report('PASTE_CASE_ID'))"
```

## 7. The demo flow (API)

1. `POST /auth/register` `{username, password}` → returns a token
2. `POST /cases` `{title, seeds:[{type,value}]}` (Bearer token) → returns `case_id`, starts investigation
3. Poll `GET /cases/{case_id}/results` → `status` goes `pending → running → complete`
4. `GET /cases/{case_id}/report` → downloads the BSA-63 PDF

Seed types: `username`, `email`, `phone`, `upi`, `name`, `url`, `face`

## 8. The two demo-winning moments

- **Red-herring rejection** — a username-only match shows as `LOW — not linked`, never merged.
- **Hash verification** — recompute any artifact's SHA-256 and match it against the PDF:

```powershell
# Windows PowerShell:
Get-FileHash .\reports\artifacts\<case_id>\<artifact>.json -Algorithm SHA256
```

```bash
# macOS/Linux:
shasum -a 256 reports/artifacts/<case_id>/<artifact>.json
```

## 9. What's built

**Built and tested (101 pytest tests passing):**

- Config, DB, auth, cases, data-source interface, mock scraper, correlation (20
  signals — 7 hard-anchor, 7 context-tier, see context.md §17.12), scoring
  (red-herring rule + hard-anchor gating), LLM client (with fallbacks), orchestrator,
  audit ledger (hash chain), BSA-63 PDF.
- Live scrapers: GitHub (incl. followers sample for mutual-connections), Serper
  (incl. filetype/medium/pinterest/pastebin dorks), HIBP, XposedOrNot, DeHashed,
  LeakCheck (both stubbed pending API keys), Holehe, Maigret, Sherlock, Blackbird
  (username + email), Socialscan, ignorant, PhoneInfoga, UPI, Wayback, Reddit,
  Telethon, URL scraper.
- False-positive filter: Maigret (36 excluded sites), Sherlock (3), Blackbird (1).
- Profile photo og:image enrichment, perceptual-hash matching, and face-embedding
  matching (OpenCV YuNet+SFace — see §3 above) + frontend avatar display.
- Bio-link extraction (self-disclosed cross-platform links) and NER-style
  employer/city fact extraction (LLM-based, context-tier evidence only).
- Confidence labels: CONFIRMED / POSSIBLE LEAD / UNCONFIRMED.
- Lead reverification pipeline.
- Username extraction from Serper result URLs (LinkedIn/Instagram/Twitter/GitHub handles).
- Name-seed metadata stamping so name searches produce visible LOW results, not REJECT.
- Frontend auto-expands unlinked section when no clusters are found.

**Frontend:** Next.js + Tailwind dashboard — profile photos, confidence labels, sigma.js
graph, vis-timeline, forensics panel. `npm run build` passes.

**Pending (optional):** Telethon (needs bot-token), Playwright-based Facebook/UPI-name
lookups, Reddit OAuth (needs CLIENT_ID/SECRET).

## 10. Legal

See [`LEGAL_VERIFICATION.md`](LEGAL_VERIFICATION.md). All BSA-63 claims verified.
Two wrong citations from the original brief replaced: BNSS §94 and POCSO §23 / JJ §74.
Get a qualified advocate to co-sign before July 4.
