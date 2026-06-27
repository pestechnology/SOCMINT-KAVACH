<div align="center">

# VERTEX

### SOCMINT / OSINT Suspect-Profiling System

**One identifier in. A complete, court-admissible digital profile out.**

Built for **CIDECODE 2026** · CCITR + CID Karnataka · PES University

</div>

---

## What it does

An investigator enters **one** thing they know about a suspect — a username, email, phone
number, UPI ID, or full name — and VERTEX:

1. **Collects** publicly available OSINT data for that identifier across many platforms.
2. **Correlates** every account/trace it finds using a 12-signal engine.
3. **Decides** which accounts belong to the **same person** — and refuses to link on weak
   evidence (the *red-herring rejection*).
4. **Produces** a **court-admissible evidence PDF** under India's **Bharatiya Sakshya
   Adhiniyam (BSA) 2023, Section 63**, with a tamper-evident SHA-256 hash chain.

The product's edge for a law-enforcement audience is **defensibility, not volume**: it would
rather refuse a link than over-claim one that couldn't survive in court.

---

## Key features

- **12-signal correlation engine** — shared phone/email/UPI, username similarity, photo
  perceptual-hash, posting-hour overlap, stylometry, breach co-occurrence, and more.
- **Red-herring rejection** — a single signal (e.g. only a matching username) is never enough
  to link accounts; it is flagged but kept separate.
- **Confidence tiers** — HIGH / MEDIUM / LOW / REJECT, each with a plain-English explanation.
- **BSA-63 court PDF** — cover page, search manifest, findings, Annexure A (artifacts +
  SHA-256), Part A/B §63(4) certificate templates, chain-of-custody log. Hashes are
  independently verifiable.
- **Tamper-evident audit ledger** — every step recorded in an append-only SHA-256 hash chain.
- **Fail-safe scrapers** — any failing tool returns empty; one broken source never stops a run.
- **LLM enhancement (NVIDIA), never on the critical path** — used only to extract entities and
  phrase explanations, always with a deterministic fallback. It never decides linking.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10, FastAPI, uvicorn, SQLite (stdlib, no ORM), httpx |
| Auth | JWT (python-jose, HS256) + bcrypt |
| Correlation | thefuzz, scikit-learn, imagehash (all optional; degrade gracefully) |
| Report | ReportLab (BSA-63 PDF) |
| LLM | NVIDIA Cloud (`llama-3.3-70b`, `deepseek-v4-pro`) — enhancement-only |
| Scrapers | Maigret, GitHub API, Serper, HIBP, UPI parser, PhoneInfoga/ignorant |
| Frontend | Next.js 14 (App Router), Tailwind CSS, sigma.js, vis-timeline |

---

## Quick start

> Requires Python 3.10+ and Node 18+.

```bash
# 1. Secrets
cp .env.example .env                 # fill SERPER_API_KEY, GITHUB_TOKEN, NVIDIA_API_KEY
python -c "import secrets; print(secrets.token_hex(32))"   # paste into JWT_SECRET in .env

# 2. Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install maigret                  # primary username scraper (separate install)
python -m backend.database           # create cidecode.db (6 tables)
python -m scripts.create_admin       # creates admin / vertex2026
uvicorn backend.main:app --reload --port 8000      # API + docs at /docs

# 3. Frontend
cd frontend
cp .env.local.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                          # http://localhost:3000

# 4. Tests
python -m pytest tests/ -q           # 44 tests
```

**Offline demo (no keys/network):** set `DATA_MODE=mock` in `.env`, restart the backend, then run
an investigation — you'll get a HIGH-confidence cluster plus a correctly-rejected red herring.

**Default login:** `admin` / `vertex2026` — change it before any real use.

---

## Project structure

```
backend/
  config.py            env-driven config (warns on missing keys, never crashes)
  database/            SQLite: 6 tables (users, cases, entities, clusters, audit_ledger, artifacts)
  auth/                JWT + bcrypt (register/login/middleware/routes)
  cases/               case CRUD + owner access control
  ingestion/           BaseDataSource + scrapers (mock, github, serper, hibp, maigret, upi, phone)
  correlation/         pairwise signal computation
  scoring/             clustering + tiers + red-herring rule
  llm/                 NVIDIA client with regex/template fallbacks
  pipeline/            orchestrator (parallel fan-out -> correlate -> score -> persist)
  ledger/              tamper-evident hash chain + artifact hashing
  report/              BSA-63 PDF generator
  main.py              FastAPI entrypoint
frontend/              Next.js 14 + Tailwind dashboard (login, registry, 3-panel case view)
scripts/               create_admin, seed_demo_case
tests/                 pytest suite (44 tests)
context.md             full engineering onboarding doc (read this to continue development)
LEGAL_VERIFICATION.md  BSA-63 legal claims verified against primary sources
SETUP.md               detailed run guide
```

---

## API (summary)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | no | liveness |
| POST | `/auth/register` | no | create user → token |
| POST | `/auth/login` | no | authenticate → token |
| POST | `/cases` | yes | create case + start investigation (background) |
| GET | `/cases` | yes | list your cases |
| GET | `/cases/{id}` | yes | one case (owner only) |
| GET | `/cases/{id}/results` | yes | entities + clusters (polled by the UI) |
| GET | `/cases/{id}/report` | yes | download the BSA-63 PDF |

---

## Legal

All BSA-63 claims have been checked against primary/authoritative sources — see
[`LEGAL_VERIFICATION.md`](LEGAL_VERIFICATION.md). The two incorrect citations from the original
brief (PMLA §12, CPCR §12) are replaced with **BNSS §94** and **POCSO §23 / JJ Act §74**. The
report's certificate is a template; Part B is left for a certified expert to sign — VERTEX never
fabricates a signature. **Get a qualified advocate to co-sign before any real/court use.**

---

## Security notes

> - Secrets live in `.env`, which is **gitignored** — never commit real keys, and rotate any key
>   that was ever exposed.
> - The default admin password (`vertex2026`) is for the demo only; change it.
> - This tool collects only **publicly available** data and is intended for **lawful, authorised**
>   investigative use.

---

<div align="center">
<sub>VERTEX — investigative-grade OSINT. Quality of evidence over volume of results.</sub>
</div>
