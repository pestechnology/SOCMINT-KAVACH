# VERTEX — SOCMINT / OSINT Suspect-Profiling System

**One identifier in. A complete, court-admissible digital profile out.**

Built for **CIDECODE 2026** · CCITR + CID Karnataka · PES University

---

## What it does

An investigator enters **one** thing they know about a suspect — a username, email, phone
number, UPI ID, full name, or social-media URL — and VERTEX:

1. **Collects** publicly available OSINT data for that identifier across dozens of platforms.
2. **Correlates** every account/trace it finds using a 20-signal engine.
3. **Decides** which accounts belong to the **same person** — and refuses to link on weak
   evidence (the *red-herring rejection*).
4. **Produces** a **court-admissible evidence PDF** under India's **Bharatiya Sakshya
   Adhiniyam (BSA) 2023, Section 63**, with a tamper-evident SHA-256 hash chain.

The product's edge for a law-enforcement audience is **defensibility, not volume**: it would
rather refuse a link than over-claim one that couldn't survive in court.

---

## Key features

- **20-signal correlation engine** — shared phone/email/UPI, username similarity (exact /
  substring / fuzzy), profile photo perceptual-hash, face-embedding match (same person,
  different photo), bio self-disclosed links, posting-hour overlap, stylometry, breach
  co-occurrence, bio keywords, real-name match, location overlap, employer/city NER match,
  mutual-connections overlap. Every signal is classified as a **hard anchor** (standalone-
  sufficient evidence) or **context** (corroborating only, never alone-sufficient).
- **Red-herring rejection** — a single signal (e.g. only a matching username) is never enough
  to link accounts; it is flagged LOW but kept separate.
- **Confidence tiers** — HIGH / MEDIUM / LOW / REJECT, each with a plain-English explanation.
- **False-positive filter** — Maigret, Sherlock, and Blackbird each run a random control
  username in parallel; "broken detector" sites are excluded from real results.
- **BSA-63 court PDF** — cover page, search manifest, findings, Annexure A (SHA-256
  hashes), Part A/B §63(4) certificate templates, chain-of-custody log.
- **Tamper-evident audit ledger** — every step in an append-only SHA-256 hash chain.
- **Fail-safe scrapers** — any failing tool returns empty; one broken source never stops a run.
- **LLM enhancement (NVIDIA), never on the critical path** — entity extraction + plain-English
  explanations, always with a deterministic fallback. Never decides linking.
- **Username extraction from Serper URLs** — LinkedIn/Instagram/Twitter/GitHub handles are
  extracted from URL paths so name-seed searches produce correct correlation matches.

---

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.10+, FastAPI, uvicorn, SQLite (stdlib, no ORM), httpx |
| Auth | JWT (python-jose, HS256) + bcrypt |
| Correlation | thefuzz, scikit-learn, imagehash (all optional; degrade gracefully) |
| Report | ReportLab (BSA-63 PDF) |
| LLM | NVIDIA Cloud (`llama-3.3-70b`, `deepseek-v4-pro`) — enhancement-only |
| Scrapers | Maigret, Sherlock, Blackbird, Socialscan, GitHub API, Serper, HIBP, XposedOrNot, Holehe, ignorant, PhoneInfoga, NumVerify, Wayback, Reddit, Telethon, UPI parser |
| Frontend | Next.js 14 (App Router), Tailwind CSS, sigma.js, vis-timeline |

---

## Quick start

> Requires Python 3.10+ and Node 18+. Read `SETUP.md` for the full guide including
> Blackbird (external repo) and all optional tools.

```bash
# 1. Secrets
cp .env.example .env
# Fill in SERPER_API_KEY, GITHUB_TOKEN, NVIDIA_API_KEY
# Generate JWT_SECRET:  python -c "import secrets; print(secrets.token_hex(32))"

# 2. Backend  (Python 3.10+; never reuse a venv from another machine)
python -m venv venv
venv\Scripts\activate          # Windows  |  source venv/bin/activate  on macOS/Linux
pip install -r requirements.txt
pip install pytest pytest-asyncio    # test deps (not in requirements.txt)
pip install ignorant                 # phone registration checker

# 3. Blackbird (not on PyPI — clone separately)
git clone https://github.com/p1ngul1n0/blackbird C:\tools\blackbird
pip install -r C:\tools\blackbird\requirements.txt
pip install "aiohttp>=3.12.14,<4.0.0" "multidict>=6.6.3,<7.0.0" "reportlab>=4.4.3,<5.0.0"
# Create venv\Scripts\blackbird.bat and add BLACKBIRD_PATH=C:\tools\blackbird to .env
# Full instructions in SETUP.md

# 4. Database + admin
python -m backend.database           # creates cidecode.db (6 tables)
python -m scripts.create_admin       # admin / vertex2026

# 5. Backend
uvicorn backend.main:app --reload --port 8000

# 6. Frontend
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install && npm run dev           # http://localhost:3000

# 7. Tests
python -m pytest tests/ -q           # 101 tests
```

**Offline demo:** set `DATA_MODE=mock` in `.env`, restart the backend, run an investigation.
You get a HIGH-confidence cluster, a correctly-rejected red herring, and a PDF — no network.

**Default login:** `admin` / `vertex2026` — change before any real use.

---

## Project structure

```text
backend/
  config.py            env-driven config (warns on missing keys, never crashes)
  database/            SQLite: 6 tables (users, cases, entities, clusters, audit_ledger, artifacts)
  auth/                JWT + bcrypt
  cases/               case CRUD + owner access control
  ingestion/           BaseDataSource + all scrapers (maigret, sherlock, blackbird,
                       socialscan, github, serper, hibp, xposedornot, holehe,
                       dehashed, leakcheck, phone_scrapers, wayback, reddit, telethon,
                       upi, url, variants, photo_enrich (pHash + face embedding),
                       fact_enrich (NER-style employer/city), profile_page_fetcher,
                       fp_filter, mock)
  analysis/            forensics.py — stylometry, sentiment, keywords, activity
  correlation/         pairwise 20-signal computation
  scoring/             clustering + tiers + red-herring rule (DO NOT MODIFY)
  llm/                 NVIDIA client with regex/template fallbacks
  pipeline/            orchestrator + lead_reverification
  ledger/              tamper-evident hash chain + artifact hashing
  report/              BSA-63 PDF generator
  models/              face-matching ONNX models (gitignored; run scripts/ below)
  scripts/             download_face_models.py — one-time face-model fetch
  main.py              FastAPI entrypoint
frontend/              Next.js 14 + Tailwind dashboard
scripts/               create_admin, seed_demo_case
tests/                 101 pytest tests
context.md             full engineering onboarding doc (read §19-20 for latest)
SETUP.md               step-by-step run guide including Blackbird setup
TRANSFER_CHECKLIST.md  checklist for zip/GitHub transfers to a new machine
LEGAL_VERIFICATION.md  BSA-63 legal claims verified against primary sources
```

---

## API summary

| Method | Path | Auth | Purpose |
| ------ | ---- | ---- | ------- |
| GET | `/health` | no | liveness |
| POST | `/auth/register` | no | create user → token |
| POST | `/auth/login` | no | authenticate → token |
| POST | `/cases` | yes | create case + start investigation |
| GET | `/cases` | yes | list your cases |
| GET | `/cases/{id}` | yes | one case (owner only) |
| GET | `/cases/{id}/results` | yes | entities + clusters + forensics |
| GET | `/cases/{id}/report` | yes | download BSA-63 PDF |

---

## Legal

All BSA-63 claims checked against primary sources — see [`LEGAL_VERIFICATION.md`](LEGAL_VERIFICATION.md).
Two wrong citations from the original brief (PMLA §12, CPCR §12) replaced with **BNSS §94**
and **POCSO §23 / JJ Act §74**. Part B of the certificate is a template for a qualified expert
to sign — VERTEX never fabricates a signature. **Get a qualified advocate to co-sign before
any real or court use.**

---

## Security notes

- Secrets live in `.env`, which is gitignored — never commit real keys; rotate any that were exposed.
- The default admin password (`vertex2026`) is for the demo only; change it.
- This tool collects only **publicly available** data for **lawful, authorised** investigative use.

---

*VERTEX — investigative-grade OSINT. Quality of evidence over volume of results.*
