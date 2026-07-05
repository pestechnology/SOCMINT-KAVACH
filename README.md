# VERTEX — SOCMINT / OSINT Suspect-Profiling System

**One identifier in. A complete, defensible digital-evidence profile out.**

Developed for CIDECODE 2026 (CCITR + CID Karnataka, PES University).

---

## Overview

An investigator provides a single identifier for a subject — a username, email, phone
number, UPI ID, full name, or social-media URL — and VERTEX:

1. **Collects** publicly available OSINT data for that identifier across dozens of platforms.
2. **Correlates** every account and trace it finds using a 20-signal engine.
3. **Decides** which accounts belong to the same person, and refuses to link on weak
   evidence (red-herring rejection).
4. **Seals** the supporting evidence and produces a report structured to India's Bharatiya
   Sakshya Adhiniyam (BSA) 2023, Section 63, backed by a tamper-evident SHA-256 hash chain.

The design priority is **defensibility over volume**: VERTEX would rather refuse a link than
over-claim one that could not withstand scrutiny. It never asserts admissibility — that is a
determination for the court — but it preserves, timestamps, and structures evidence so it can
be certified and defended.

---

## Key features

- **20-signal correlation engine** — shared phone/email/UPI, username similarity
  (exact / substring / fuzzy), profile-photo perceptual hash, face-embedding match (same
  person, different photo), bio self-disclosed links, posting-hour overlap, stylometry,
  breach co-occurrence, real-name match, location overlap, employer/city NER match, and
  mutual-connections overlap. Each signal is classified as a **hard anchor**
  (standalone-sufficient) or **context** (corroborating only, never sufficient alone).
- **Red-herring rejection** — a single weak signal (for example, only a matching username)
  is never enough to link accounts; it is flagged LOW and kept separate.
- **Confidence tiers** — HIGH / MEDIUM / LOW / REJECT, each with a plain-English explanation.
- **False-positive filter** — Maigret, Sherlock, and Blackbird each run a random control
  username in parallel; "broken detector" sites are excluded from real results.
- **Court-grade evidence capture** — the moment a page is viewed it is sealed as a
  self-contained bundle (full-page screenshot, MHTML, post-JS DOM, and a metadata
  certificate). Each file is SHA-256-hashed into the tamper-evident ledger and anchored to a
  trusted external RFC-3161 timestamp (FreeTSA), so proof of *when and unaltered* lives
  outside the system VERTEX controls. A dedicated Evidence Exhibit Report presents every
  bundle as a numbered exhibit.
- **Tamper-evident audit ledger** — every step recorded in an append-only SHA-256 hash chain.
- **BSA-63 report** — cover page, search manifest, findings, Annexure A (SHA-256 hashes),
  Part A/B §63(4) certificate templates, and a chain-of-custody log.
- **Agentic browser** — a real, AI-driven browser (browser-use + Playwright) reaches
  login-gated and JavaScript-heavy pages a plain scraper cannot, and extracts only what is
  literally on the page. An anti-fabrication guardrail returns an empty result and an honest
  `blocked` flag rather than invent a value. Extracted profiles are re-correlated and
  re-scored like any other source.
- **Kavach case assistant (RAG)** — grounded, plain-language Q&A over a single case's data,
  hard-constrained to the evidence (no outside knowledge, no invented facts, cites the signal
  it draws from), with a deterministic retrieval fallback.
- **Investigative copilot** — an adjudicator and semantic reranker extend the deterministic
  engine (AI-assessed links are tagged distinctly from forensically-anchored ones), a
  next-actions recommender ranks concrete next steps, and a law-enforcement data-request
  directory maps found accounts to the correct platform portal and a BNSS §94
  preservation-letter target.
- **Multilingual (Indic) normalization** — Kannada / Tamil / Telugu / Malayalam script
  detection, ISO-15919 transliteration, and phonetic keys (low-weight, never sufficient
  alone; the original string is always preserved as the evidentiary field).
- **NewLeaks breach source and Additional Data panel** — an optional Telegram-bot breach/PII
  source folds leaked identity fields into the case and surfaces them in a dedicated panel;
  fully inert unless enabled and a user session exists.
- **Re-iteration / identifier cross-pivoting** — select any mix of discovered accounts,
  derived name/alias suggestions, or profile pictures, plus manually-typed identifiers, and
  run one combined follow-up search that folds new results into the same case. Repeatable.
  See [`docs/REITERATION_AND_SEARCH_SYSTEM.md`](docs/REITERATION_AND_SEARCH_SYSTEM.md).
- **Automatic email→username bridge** — an email seed's local part is re-run as a username
  search, so an email-only investigation still finds social accounts, not just breach records.
- **Deep bio scraping** — self-disclosed links in a bio or a platform's blog/website field
  are followed to new accounts; employer/school/city are extracted via an LLM pass with a
  deterministic regex fallback.
- **Tier-1 identity enrichment** — Gravatar, EmailRep, and socid_extractor fold into the same
  fail-safe pipeline.
- **Activity timeline** — a per-account posting/activity timeline view of the subject.
- **LLM enhancement, never on the critical path** — entity extraction and plain-English
  explanations, always with a deterministic fallback. The LLM never decides linking.
- **Fail-safe scrapers** — any failing tool returns empty; one broken source never stops a run.

---

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Backend | Python 3.10+, FastAPI, uvicorn, SQLite (stdlib, no ORM), httpx |
| Auth | JWT (python-jose, HS256) + bcrypt |
| Correlation | thefuzz, scikit-learn, imagehash (all optional; degrade gracefully) |
| Evidence | ReportLab (PDF), RFC-3161 external timestamp (FreeTSA), SHA-256 hash chain |
| LLM | NVIDIA Cloud + Groq (Llama 3.3 70B) — enhancement-only, with deterministic fallbacks |
| Agents / RAG | Agentic browser (browser-use + Playwright, Gemini navigation), identity-resolution, adjudicator, semantic reranker, Kavach case assistant (grounded RAG) |
| Multilingual | aksharamukha (Indic → ISO-15919 transliteration) + phonetic keys (Kannada/Tamil/Telugu/Malayalam) |
| Scrapers | Maigret, Sherlock, Blackbird, Socialscan, GitHub API, Serper, HIBP, XposedOrNot, Holehe, ignorant, PhoneInfoga, NumVerify, Wayback, Reddit, Telethon, UPI parser, Gravatar, EmailRep, socid_extractor, NewLeaks (Telegram) |
| Frontend | Next.js 14 (App Router), Tailwind CSS, sigma.js, vis-timeline |

---

## Quick start

Requires Python 3.10+ and Node 18+. See [`SETUP.md`](SETUP.md) for the full guide, including
Blackbird (an external repo) and all optional tools.

```bash
# 1. Secrets
cp .env.example .env
# Fill in SERPER_API_KEY, GITHUB_TOKEN, NVIDIA_API_KEY.
# Generate a JWT secret:  python -c "import secrets; print(secrets.token_hex(32))"

# 2. Backend (Python 3.10+; do not reuse a venv created on another machine)
python -m venv venv
source venv/bin/activate          # macOS/Linux   |   venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install pytest pytest-asyncio # test deps (not in requirements.txt)

# 3. Database + admin user
python -m backend.database        # creates the SQLite database
python -m scripts.create_admin    # creates the default admin user

# 4. Run the backend
uvicorn backend.main:app --reload --port 8000

# 5. Frontend
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install && npm run dev         # http://localhost:3000

# 6. Tests
python -m pytest tests/ -q
```

**Offline demo:** set `DATA_MODE=mock` in `.env`, restart the backend, and run an
investigation. You get a HIGH-confidence cluster, a correctly-rejected red herring, and a
PDF — with no network access.

The default admin credentials are for local development only; change them before any real use.

---

## Project structure

```text
backend/
  config.py          env-driven config (warns on missing keys, never crashes)
  database/          SQLite schema and access (users, cases, entities, clusters,
                     audit_ledger, artifacts)
  auth/              JWT + bcrypt
  cases/             case CRUD, routes, and owner access control
  ingestion/         BaseDataSource + all scrapers, plus photo_enrich (pHash + face
                     embedding), fact_enrich, browser_fetch, newleaks_scraper,
                     leak_classify, and derive (re-iteration engine)
  agentic_browser/   real-browser OSINT agent (browser-use + Playwright) and its service layer
  normalization/     Indic script detection, transliteration, and phonetic keys
  analysis/          forensics, identity_agent, adjudicator, reranker, name_intel,
                     case_chat (Kavach RAG), next_actions, le_directory
  correlation/       pairwise 20-signal computation
  scoring/           clustering, confidence tiers, and the red-herring rule
  llm/               NVIDIA/Groq client with regex/template fallbacks
  pipeline/          orchestrator (investigation + re-iteration/pivot) + lead_reverification
  ledger/            tamper-evident hash chain + artifact hashing
  evidence/          court-grade page capture (screenshot/MHTML/DOM + external timestamp)
  report/            BSA-63 report, executive summary, and evidence-exhibit generators
  models/            face-matching ONNX models (gitignored; fetched by a setup script)
  main.py            FastAPI entrypoint
frontend/            Next.js 14 + Tailwind dashboard
scripts/             create_admin, seed_demo_case, download_face_models, telegram_login,
                     render_pdf
tests/               pytest suite
docs/                design and integration notes
SETUP.md             step-by-step run guide, including Blackbird setup
LEGAL_VERIFICATION.md  BSA-63 legal claims verified against primary sources
```

---

## API summary

| Method | Path | Auth | Purpose |
| ------ | ---- | ---- | ------- |
| GET | `/health` | no | liveness |
| POST | `/auth/register` | no | create user, returns token |
| POST | `/auth/login` | no | authenticate, returns token |
| POST | `/cases` | yes | create case and start investigation |
| GET | `/cases` | yes | list your cases |
| GET | `/cases/{id}` | yes | one case (owner only) |
| GET | `/cases/{id}/results` | yes | entities + clusters + forensics + reiteration count |
| GET | `/cases/{id}/report` | yes | download the BSA-63 report |
| GET | `/cases/{id}/summary_report` | yes | download the executive-summary report |
| GET | `/cases/{id}/evidence_report` | yes | download the Evidence Exhibit Report |
| POST | `/cases/{id}/chat` | yes | ask the Kavach case assistant a grounded question |
| POST | `/cases/{id}/pivot/suggest` | yes | derive candidate seeds from selected identifiers (no scrape) |
| POST | `/cases/{id}/pivot` | yes | run a re-iteration on a list of seeds, merged into the case |

---

## Legal

All BSA-63 claims are checked against primary sources — see
[`LEGAL_VERIFICATION.md`](LEGAL_VERIFICATION.md). Two incorrect citations from the original
brief (PMLA §12, CPCR §12) were replaced with BNSS §94 and POCSO §23 / JJ Act §74. Part B of
the certificate is a template for a qualified expert to sign; VERTEX never fabricates a
signature. Have a qualified advocate co-sign before any real or court use.

---

## Security notes

- Secrets live in `.env`, which is gitignored. Never commit real keys, and rotate any that
  were exposed.
- The default admin password is for local development only; change it.
- This tool collects only publicly available data, for lawful, authorised investigative use.
