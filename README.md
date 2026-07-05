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
- **Re-iteration / identifier cross-pivoting** — select any mix of already-discovered
  accounts, LLM/regex-derived name & alias suggestions, or profile pictures (dragged in
  from the Summary tab), plus manually-typed identifiers, and run ONE combined follow-up
  search that folds new results back into the same case. Repeatable — select again from
  the larger result set after each run. See [`REITERATION_AND_SEARCH_SYSTEM.md`](REITERATION_AND_SEARCH_SYSTEM.md)
  for the full architecture.
- **Automatic email→username bridge** — an email seed's local part (`vismayhs` from
  `vismayhs@gmail.com`) is automatically re-run as a full username search, so an
  email-only investigation still finds Instagram/GitHub/etc., not just breach records.
- **Deep bio scraping** — self-disclosed links in a bio *or* a platform's dedicated
  blog/website field (e.g. GitHub's `blog`) are followed to new accounts; employer/
  school/city are extracted with an LLM pass backed by a deterministic regex fallback
  so facts still populate when the LLM provider is rate-limited.
- **Tier-1 identity enrichment** — Gravatar (avatar existence + verified linked
  accounts), EmailRep (registered-service/reputation lookup), and socid_extractor
  (structured name/location/DOB from known-platform pages) all fold into the same
  fail-safe, no-key-required-by-default pipeline.
- **Agentic browser** — a real, AI-driven browser (browser-use + Playwright) reaches
  login-gated and JavaScript-heavy pages a plain scraper can't, and extracts ONLY what is
  literally on the page — a hard anti-fabrication guardrail returns empty + an honest
  `blocked` flag rather than invent a value. Extracted profiles are re-correlated and
  re-scored like any other source, never inserted as islands.
- **Court-grade evidence capture (Hunchly-style)** — the moment a page is viewed it is
  sealed as a self-contained bundle (full-page screenshot + MHTML + post-JS DOM + a
  metadata certificate), each file SHA-256-hashed into the tamper-evident ledger AND
  anchored to a trusted external RFC-3161 timestamp (FreeTSA) — so "when + unaltered"
  lives outside the system VERTEX controls. A dedicated **Evidence Exhibit Report**
  presents every bundle as a numbered exhibit, structured to BSA §63.
- **NewLeaks breach source + "Additional Data" tab** — an optional Telegram-bot breach/PII
  source folds leaked identity fields (name/location/phone/email/employer/…) into the case;
  they surface in a dedicated Additional Data panel and are grounded into the Kavach assistant.
  Fully inert unless enabled AND a user session exists — never fabricates.
- **Kavach case assistant (RAG)** — grounded, plain-language Q&A over a single case's data,
  hard-constrained to the evidence (never outside knowledge, never invented, cites the
  signal it drew from), with a deterministic retrieval fallback.
- **Investigative copilot** — an adjudicator + reranker extend the deterministic engine
  (AI-assessed links are tagged distinctly from forensically-anchored ones), a next-actions
  recommender ranks concrete next steps, and an **LE data-request directory** maps found
  accounts to the right platform portal + a **BNSS §94** preservation-letter target.
- **Multilingual (Indic) normalization** — Kannada / Tamil / Telugu / Malayalam script
  detection, ISO-15919 transliteration, and phonetic keys (low-weight, never sufficient
  alone; the original string is always preserved as the evidentiary field).
- **Activity timeline** — a per-account posting/activity timeline view of the subject.

---

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.10+, FastAPI, uvicorn, SQLite (stdlib, no ORM), httpx |
| Auth | JWT (python-jose, HS256) + bcrypt |
| Correlation | thefuzz, scikit-learn, imagehash (all optional; degrade gracefully) |
| Report | ReportLab (BSA-63 PDF) |
| LLM | NVIDIA Cloud (`llama-3.3-70b`, `deepseek-v4-pro`) — enhancement-only |
| Scrapers | Maigret, Sherlock, Blackbird, Socialscan, GitHub API, Serper, HIBP, XposedOrNot, Holehe, ignorant, PhoneInfoga, NumVerify, Wayback, Reddit, Telethon, UPI parser, Gravatar, EmailRep, socid_extractor, agentic browser (browser-use + Playwright), NewLeaks (Telegram) |
| Agents / RAG | Agentic browser (Gemini nav), identity-resolution, adjudicator, semantic reranker, Kavach case assistant (NVIDIA/Groq, grounded RAG) — all with deterministic fallbacks |
| Multilingual | aksharamukha (Indic → ISO-15919 transliteration) + phonetic keys for Kannada/Tamil/Telugu/Malayalam |
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
python -m pytest tests/ -q           # 189 tests
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
                       fact_enrich (NER-style employer/city + deterministic fallback),
                       profile_page_fetcher, fp_filter, mock, gravatar_scraper,
                       emailrep_scraper, socid_enrich, derive (re-iteration engine))
  analysis/            forensics.py — stylometry, sentiment, keywords, activity
  correlation/         pairwise 20-signal computation
  scoring/             clustering + tiers + red-herring rule (DO NOT MODIFY)
  llm/                 NVIDIA client with regex/template fallbacks
  pipeline/            orchestrator (investigation + re-iteration/pivot) + lead_reverification
  ledger/              tamper-evident hash chain + artifact hashing
  report/              BSA-63 PDF generator
  models/              face-matching ONNX models (gitignored; run scripts/ below)
  scripts/             download_face_models.py — one-time face-model fetch
  main.py              FastAPI entrypoint
frontend/              Next.js 14 + Tailwind dashboard (incl. ReiterateBar.jsx —
                       the re-iteration staging tray + floating action button)
scripts/               create_admin, seed_demo_case
tests/                 189 pytest tests
context.md             full engineering onboarding doc (read §21 for the latest)
REITERATION_AND_SEARCH_SYSTEM.md  full re-iteration / cross-pivoting architecture
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
| GET | `/cases/{id}/results` | yes | entities + clusters + forensics + reiteration_count |
| GET | `/cases/{id}/report` | yes | download BSA-63 PDF |
| GET | `/cases/{id}/summary_report` | yes | download the executive-summary PDF |
| POST | `/cases/{id}/pivot/suggest` | yes | derive candidate seeds from a set of selected identifiers (free — no scrape) |
| POST | `/cases/{id}/pivot` | yes | run a re-iteration on an explicit list of seeds, merged into this case |

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
