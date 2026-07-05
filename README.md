# VERTEX

**SOCMINT / OSINT suspect-profiling that produces defensible evidence — not just leads.**
One identifier in, a complete and court-ready digital profile out.

Developed for CIDECODE 2026 (CCITR + CID Karnataka, PES University).

---

## Overview

Imagine an investigator with one lead — a single username — and three weeks to build a case.
They surface fifty accounts and hundreds of data points, assemble a profile, and walk into
court. Then the suspect's profiles are gone: deleted overnight. The defense asks three
questions:

> *Prove these accounts ever existed. Prove they belong to the same person. Prove you did not
> tamper with any of it.*

If the answers are shaky, three weeks of work is worthless — and the suspect walks.

**That gap — between *finding* data and *proving* it — is where investigations fail. VERTEX is
built to close it.**

VERTEX takes a single identifier (username, email, phone, UPI ID, name, or profile URL), finds
the subject's footprint across dozens of platforms, decides which accounts belong to the same
person, and **seals the evidence the moment it is seen** — captured, hashed, and independently
timestamped — in a report structured to India's Bharatiya Sakshya Adhiniyam (BSA) 2023,
Section 63.

Its guiding principle is **defensibility over volume**: VERTEX would rather refuse a weak link
than over-claim one that cannot withstand scrutiny. It never asserts admissibility — that is
the court's determination — but it preserves, timestamps, and structures evidence so it can be
certified and defended.

---

## How it works

One identifier flows through a five-stage pipeline:

| Stage | What happens |
| ----- | ------------ |
| **1. Collect** | Fan out across dozens of OSINT sources in parallel. For login-gated or JavaScript-heavy pages a plain scraper cannot reach, an AI-driven real browser extracts only what is literally on the page — never fabricating a value. |
| **2. Resolve** | Consolidate noisy fragments into one clean identity (real name, aliases, location, employer). Indian-language names in Kannada, Tamil, Telugu, and Malayalam are transliterated and phonetically matched. |
| **3. Correlate** | A 20-signal engine compares everything — shared phone, photo, face, UPI, writing style, active hours — to determine what belongs to the same person. |
| **4. Decide & seal** | Assign a confidence tier with a plain-English reason. A weak, single-signal match is *rejected, not forced*. Evidence-worthy pages are then sealed: screenshot + MHTML + DOM + metadata, SHA-256-hashed into a tamper-evident ledger and anchored to a trusted external RFC-3161 timestamp. |
| **5. Assist** | The Kavach assistant answers questions grounded strictly in the case, a copilot ranks concrete next steps, and a law-enforcement directory maps each account to the correct data-request portal. |

---

## Key capabilities

**Correlation and decisioning**
- **20-signal engine** — shared phone/email/UPI, username similarity, profile-photo perceptual
  hash, face-embedding match (same person, different photo), self-disclosed bio links,
  posting-hour overlap, stylometry, breach co-occurrence, real-name/location/employer match,
  and more. Each signal is a **hard anchor** (standalone-sufficient) or **context**
  (corroborating only).
- **Red-herring rejection** — a single weak signal (for example, only a matching username)
  never links accounts; it is flagged LOW and kept separate.
- **Confidence tiers** — HIGH / MEDIUM / LOW / REJECT, each with a plain-English explanation.
- **False-positive filter** — a random control username runs in parallel to detect and exclude
  "broken detector" sites.

**Evidence integrity**
- **Court-grade capture** — the moment a page is viewed it is sealed as a self-contained bundle
  (full-page screenshot, MHTML, post-JS DOM, metadata certificate), each file SHA-256-hashed
  and anchored to a trusted external RFC-3161 timestamp (FreeTSA) — so proof of *when and
  unaltered* lives outside the system VERTEX controls.
- **Tamper-evident ledger** — every step recorded in an append-only SHA-256 hash chain.
- **Reports** — a BSA-63 report (findings, SHA-256 annexure, §63(4) certificate templates,
  chain-of-custody), an executive summary, and a numbered Evidence Exhibit Report.

**AI, with guardrails**
- **Agentic browser** — a real browser (browser-use + Playwright) reaches sources a scraper
  cannot, under a hard anti-fabrication guardrail; results re-correlate like any other source.
- **Kavach case assistant (RAG)** — grounded Q&A hard-constrained to the case evidence, with a
  deterministic fallback; never invents an identifier or fact.
- **Adjudicator and reranker** — extend the deterministic engine, with AI-assessed links tagged
  distinctly from forensically-anchored ones.
- Every AI component has a deterministic fallback, and **no AI ever decides a link on its own**.

**Coverage and enrichment**
- **Multilingual (Indic) normalization** — script detection, ISO-15919 transliteration, and
  phonetic keys; the original string is always preserved as the evidentiary field.
- **Breach data** — optional NewLeaks source folds leaked identity fields into a dedicated
  Additional Data panel (inert unless enabled with a valid session).
- **Deep bio scraping**, **email→username bridging**, and **Tier-1 enrichment** (Gravatar,
  EmailRep, socid_extractor).

**Investigator workflow**
- **Re-iteration / cross-pivoting** — select discovered accounts, derived names, or profile
  photos and run one combined follow-up search that folds back into the same case.
  See [`docs/REITERATION_AND_SEARCH_SYSTEM.md`](docs/REITERATION_AND_SEARCH_SYSTEM.md).
- **Investigative copilot** — ranked next actions plus a law-enforcement data-request directory
  (correct portal + a BNSS §94 preservation-letter target).
- **Network graph** and **activity timeline** views.

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
PDF — with no network access. The default admin credentials are for local development only;
change them before any real use.

---

## Project structure

```text
backend/
  config.py          env-driven config (warns on missing keys, never crashes)
  database/          SQLite schema and access
  auth/              JWT + bcrypt
  cases/             case CRUD, routes, and owner access control
  ingestion/         BaseDataSource + all scrapers, photo/fact enrichment,
                     browser_fetch, newleaks_scraper, leak_classify, derive (re-iteration)
  agentic_browser/   real-browser OSINT agent (browser-use + Playwright) and service layer
  normalization/     Indic script detection, transliteration, and phonetic keys
  analysis/          forensics, identity_agent, adjudicator, reranker, name_intel,
                     case_chat (Kavach RAG), next_actions, le_directory
  correlation/       pairwise 20-signal computation
  scoring/           clustering, confidence tiers, and the red-herring rule
  llm/               NVIDIA/Groq client with regex/template fallbacks
  pipeline/          orchestrator (investigation + re-iteration) + lead_reverification
  ledger/            tamper-evident hash chain + artifact hashing
  evidence/          court-grade page capture (screenshot/MHTML/DOM + external timestamp)
  report/            BSA-63, executive-summary, and evidence-exhibit generators
  main.py            FastAPI entrypoint
frontend/            Next.js 14 + Tailwind dashboard
scripts/             create_admin, seed_demo_case, download_face_models, telegram_login
tests/               pytest suite
docs/                design and integration notes
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

## Legal and responsible use

VERTEX collects only publicly available data, for lawful and authorised investigative use.
All BSA-63 claims are checked against primary sources — see
[`LEGAL_VERIFICATION.md`](LEGAL_VERIFICATION.md). Two incorrect citations from the original
brief (PMLA §12, CPCR §12) were replaced with BNSS §94 and POCSO §23 / JJ Act §74. Part B of
the certificate is a template for a qualified expert to sign; VERTEX never fabricates a
signature. Have a qualified advocate co-sign before any real or court use.

---

## Security

- Secrets live in `.env`, which is gitignored. Never commit real keys, and rotate any that
  were exposed.
- The default admin password is for local development only; change it.

---

## License

Released under the [MIT License](LICENSE).
