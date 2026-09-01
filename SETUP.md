# VERTEX — Setup & Run Guide

SOCMINT/OSINT suspect-profiling system for CIDECODE 2026. This guide covers a **native**
install (no Docker) on **Linux** (primary — this is the reference platform below),
**macOS**, and **Windows**. If you'd rather not install anything OS-specific at all, use
Docker instead — see [`DOCKER.md`](DOCKER.md); it's the same on every OS.

## 1. Prerequisites

- Python 3.10 or later (tested on 3.10, 3.13)
- Node 18+ (for the frontend)
- Git (to clone Blackbird — not on PyPI)
- Docker (optional, only needed for PhoneInfoga if you don't run it natively)

**Linux (Debian/Ubuntu) — one-time system packages.** Several Python deps
(`python-Levenshtein`, `pycares`, `opencv-python-headless`'s indirect deps) need a
compiler and Python headers to build if no prebuilt wheel exists for your distro/arch:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential git curl
# Node 18+: use your distro's package, nvm, or nodesource — e.g.:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Fedora/RHEL: `sudo dnf install -y python3 python3-devel gcc gcc-c++ git nodejs`.

## 2. Secrets

```bash
cp .env.example .env
# edit .env and fill in your REAL keys (this file is gitignored, never committed)
# generate a JWT secret:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Required (all free): `SERPER_API_KEY`, `GITHUB_TOKEN`, `NVIDIA_API_KEY`, `NUMVERIFY_KEY`,
`JWT_SECRET`. Telegram (`TELEGRAM_API_ID/HASH` + a one-time session login) is required for
the phone-lookup feature — see `GET_API_KEYS.md`. `BRAVE_API_KEY` is an optional extra
search source (widens coverage, not required) — see `API_KEYS_AND_BOTS.md`.

Optional: `HIBP_API_KEY` (paid — the pipeline runs identically, just with fewer breach
hits, if unset).

> If any key was ever pasted into chat/screenshots, ROTATE it before use.
>
> **NVIDIA model IDs drift.** NVIDIA periodically retires model ids from
> `integrate.api.nvidia.com` (they start returning `410 Gone` even with a perfectly valid
> key). `backend/config.py`'s `LLM_EXTRACT_MODEL` / `LLM_EXPLAIN_MODEL` / `CHAT_LLM_MODEL`
> defaults are kept current as of the date in that file's comment; if the pipeline logs
> `[llm] ... 410` for you, check `curl -H "Authorization: Bearer $NVIDIA_API_KEY"
> https://integrate.api.nvidia.com/v1/models` for a live model id and override the
> relevant `*_MODEL` variable in `.env` (no code change needed).

## 3. Install (Linux / macOS)

> Do **not** reuse a `venv` created on another machine or another user's home directory —
> the interpreter path baked into the venv is absolute.

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-asyncio    # test deps (NOT in requirements.txt)
# maigret, sherlock-project, holehe, socialscan already in requirements.txt

# Agentic browser (backend/agentic_browser) — browser-use/playwright/patchright are
# already in requirements.txt above, but their Chromium binary is a separate download
# (skip this if you don't need the agentic browser; everything else works without it).
# Exact commands from Dockerfile.backend's own build step:
playwright install --with-deps chromium   # --with-deps also apt-installs OS libs (sudo)
python -m patchright install chromium

# Face-matching models (one-time, ~37 MB, NOT committed to git — see
# backend/ingestion/photo_enrich.py's docstring for why OpenCV's YuNet+SFace models
# were chosen over face_recognition/dlib). Optional: if this is skipped, face
# matching is simply disabled — every other signal is unaffected.
python backend/scripts/download_face_models.py

# ignorant (phone registration checker — pip-packaged):
pip install ignorant

# Blackbird (username/email enumerator — NOT pip-packaged, must be cloned):
git clone https://github.com/p1ngul1n0/blackbird tools/blackbird
pip install -r tools/blackbird/requirements.txt
# Fix version conflicts (Blackbird pins older aiohttp/multidict/reportlab than maigret) —
# run this as a SEPARATE pip command right after the one above, not combined with it:
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"

# Create the wrapper so resolve_tool() finds Blackbird on PATH (venv/bin is already
# on PATH once the venv is activated):
cat > venv/bin/blackbird <<'EOF'
#!/usr/bin/env bash
exec "$(dirname "$0")/python" "$(dirname "$0")/../../tools/blackbird/blackbird.py" "$@"
EOF
chmod +x venv/bin/blackbird

# Download Blackbird's site list (one-time — run from inside the Blackbird dir):
(cd tools/blackbird && python blackbird.py -u torvalds)   # triggers wmn-data.json download

# Add to .env:
#   BLACKBIRD_PATH=/absolute/path/to/this/repo/tools/blackbird

# PhoneInfoga (optional — native binary or Docker, either works):
#   docker run -d -p 5000:5000 sundowndev/phoneinfoga serve
#   (or download a native release from github.com/sundowndev/phoneinfoga/releases
#    and put it on PATH as `phoneinfoga`)
```

**macOS notes:** identical to the above. If a package fails to build, `brew install`
the missing system lib it names (Homebrew's Python/OpenSSL are usually already fine).
Apple Silicon: everything here is pure-Python or has arm64 wheels; no Rosetta needed.

### Windows

<details>
<summary>Click to expand native Windows instructions</summary>

> Python 3.10+ required. On Windows: `py -3.10 -m venv venv`.

```powershell
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-asyncio
REM Agentic browser Chromium binary (optional — skip if you don't need it):
playwright install chromium
python -m patchright install chromium
python backend\scripts\download_face_models.py
pip install ignorant

git clone https://github.com/p1ngul1n0/blackbird C:\tools\blackbird
pip install -r C:\tools\blackbird\requirements.txt
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"

REM Create venv\Scripts\blackbird.bat (adjust both paths):
REM   @echo off
REM   "C:\path\to\VERTEX\venv\Scripts\python.exe" "C:\tools\blackbird\blackbird.py" %*

cd C:\tools\blackbird
python blackbird.py -u torvalds
cd -

REM Add to .env:  BLACKBIRD_PATH=C:\tools\blackbird
```

**Windows-specific gotcha:** Sherlock always writes a `<username>.txt` scan dump to its
*current working directory* on every run. `sherlock_scraper.py` gives it a dedicated
`REPORT_OUTPUT_DIR/sherlock` cwd precisely so this doesn't litter your repo root — if
you're on an older checkout without that fix, you'll find stray `<username>.txt` files
appearing at the repo root; safe to delete, and gitignored either way.

</details>

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

**Linux/macOS:**

```bash
lsof -i :8000            # shows the PID holding the port
kill -9 <pid>
# or, to find+kill in one step:
fuser -k 8000/tcp
```

**Windows:** `uvicorn --reload` runs as a parent + child process. If the parent is
hard-killed, the child can be orphaned.

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
5. (Re-iterate) `POST /cases/{case_id}/pivot/suggest` `{seeds:[{type,value}]}` → free
   candidate-identifier list; `POST /cases/{case_id}/pivot` `{seeds:[...]}` → runs a
   combined follow-up search, `status` flips back to `running → complete`, repeatable

Seed types: `username`, `email`, `phone`, `upi`, `name`, `url`, `face`

## 8. The two demo-winning moments

- **Red-herring rejection** — a username-only match shows as `LOW — not linked`, never merged.
- **Hash verification** — recompute any artifact's SHA-256 and match it against the PDF:

```bash
# Linux/macOS:
sha256sum reports/artifacts/<case_id>/<artifact>.json
```

```powershell
# Windows PowerShell:
Get-FileHash .\reports\artifacts\<case_id>\<artifact>.json -Algorithm SHA256
```

## 9. What's built

**Built and tested (300+ pytest tests passing — run `pytest tests/ -q` to confirm on
your machine):**

- Config, DB, auth, cases, data-source interface, mock scraper, correlation (20
  signals — 7 hard-anchor, 7 context-tier, see backend/correlation/), scoring
  (red-herring rule + hard-anchor gating), LLM client (with fallbacks), orchestrator,
  audit ledger (hash chain, scoped per-case so merging/importing another machine's
  case history never disturbs an existing case's verifiable chain), BSA-63 PDF.
- Live scrapers: GitHub (incl. followers sample for mutual-connections), Serper
  (incl. filetype/medium/pinterest/pastebin dorks), Brave (optional second search
  index run in parallel with Serper), HIBP, XposedOrNot, Holehe, Maigret, Sherlock,
  Blackbird (username + email), Socialscan, ignorant, PhoneInfoga, UPI, Wayback,
  Telethon, URL scraper, socid_extractor (structured profile-page facts).
- False-positive filter: Maigret and Sherlock (and Blackbird's username path) each run
  a random control-username probe in parallel and exclude any site that fires for it —
  mitigates rotted per-site detection heuristics; results cached 6h per tool in
  `reports/false_positive_sites.json`.
- Profile photo og:image enrichment, perceptual-hash matching, and face-embedding
  matching (OpenCV YuNet+SFace — see §3 above) + frontend avatar display.
- Bio-link extraction — generalised beyond a bio field to a platform's dedicated
  blog/website field too (e.g. GitHub's `blog`, incl. scheme-less values) — and
  NER-style employer/school/city fact extraction (LLM-based with a deterministic
  regex fallback so facts still populate when the LLM provider is rate-limited;
  context-tier evidence only).
- **Re-iteration / identifier cross-pivoting** — `backend/ingestion/derive.py` derives
  new candidate identifiers (guessed emails, recovered names, handle variants) from
  anything already in a case; the frontend lets you multi-select discovered accounts,
  suggested candidates, and profile pictures (drag-and-drop) into one staging tray and
  run a single combined follow-up search, merged back into the same case.
- An email seed automatically also runs its local part as a username search (finds
  Instagram/GitHub/etc., not just breach records), and re-scraping an account you
  already have now MERGES newly-found facts into it instead of discarding them.
- Confidence labels: CONFIRMED / POSSIBLE LEAD / UNCONFIRMED.
- Lead reverification pipeline.
- Username extraction from Serper result URLs (LinkedIn/Instagram/Twitter/GitHub handles).
- Name-seed metadata stamping so name searches produce visible LOW results, not REJECT.
- Frontend auto-expands unlinked section when no clusters are found.

**Frontend:** Next.js + Tailwind dashboard — profile photos, confidence labels, sigma.js
graph, vis-timeline, forensics panel, re-iteration staging tray + floating action
button. `npm run build` passes.

**Standalone side-tool (not wired into the main pipeline):** `tools/onionsearch-sandbox/`
— a network-isolated Docker sandbox for dark-web (.onion) search via OnionSearch, routed
exclusively through Tor with no route to the real internet even if the tool itself has a
bug. See that folder's `docker-compose.yml` for the isolation model and usage.

**Pending (optional):** Playwright-based Facebook/UPI-name lookups.

## 10. Legal

All BSA-63 claims verified against primary sources.
Two wrong citations from the original brief replaced: BNSS §94 and POCSO §23 / JJ §74.
Get a qualified advocate to co-sign before any real or court use.
