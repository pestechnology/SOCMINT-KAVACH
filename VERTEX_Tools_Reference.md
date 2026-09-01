# VERTEX — Tools & Technology Reference

**SOCMINT / OSINT suspect-profiling pipeline — CIDECODE 2026 · Team KAVACH**

This document lists every tool, API, and library the VERTEX pipeline actually uses,
organized into three groups: the AI/LLM layer, the OSINT data-collection tools, and
the supporting infrastructure. For each one it states what the tool does, why it was
specifically chosen for this pipeline (sourced from the project's own code comments
and design docs), and its verified working status.

> Status was verified live — by actually calling each API, running each CLI tool, or
> launching each browser/model — during a working session on **2026-09-01**, not
> inferred from documentation alone. API keys, quotas, and external services can
> change after this date; treat status as a snapshot.

**Legend:** ✅ Working (verified live) · ❌ Not working (verified) · ⚙️ Core local
dependency, not an external call to verify

---

## 1. AI / LLM Calls

The AI layer is a genuine "assist," not a decision-maker: every extraction or
explanation has a deterministic fallback, and no AI component is ever allowed to
decide a match on its own — the correlation engine's signal scoring always has the
final say.

| Provider / Feature | What it does | Why it's used | Status |
|---|---|---|---|
| **Groq** (primary LLM) | Bio/fact entity extraction, per-cluster match explanations, and the Kavach case-chat assistant. | Chosen as the PRIMARY provider specifically for speed — the pipeline runs many small LLM calls (one per bio, one per cluster), and Groq's inference is fast enough (~0.2s class) to not bottleneck the investigation. Every call still has a deterministic regex/template fallback so a Groq outage never breaks the pipeline, only degrades AI-assisted quality. | ✅ Working — verified live |
| **NVIDIA** (fallback LLM) | Same role as Groq (extraction / explanations) — invoked only if Groq fails or rate-limits. | A second, independent LLM provider (NVIDIA's free-tier NIM catalog, OpenAI-compatible) gives real redundancy: if Groq is down or throttled, the pipeline still gets AI-assisted output instead of silently degrading to the template fallback for the whole run. | ✅ Working — fixed & verified this session |
| **Gemini** | Navigation/vision reasoning for the agentic browser (interpreting screenshots and page state to decide the next click/scroll). | The agentic-browser feature needs a model that can reason over VISUAL page state, not just text — Gemini was picked for this vision capability, separate from the text-only Groq/NVIDIA models used for extraction. | ✅ Working — verified live |
| **Agentic Browser** (browser-use, orchestrating Gemini over Playwright) | LLM-driven autonomous page navigation for sources a plain scraper can't reach — login-gated or heavily JavaScript pages — under a hard anti-fabrication guardrail (extracts only what is literally on the page). | Some evidence (e.g. content behind a login wall) is invisible to every other tool in this document. This is the one component built specifically to reach it, while still re-correlating its output through the same scoring engine as any other source — no AI component is allowed to decide a link on its own. | ❌ Not verified — README marks it "in process"; disabled by default even in Docker |

---

## 2. OSINT Data-Source Tools

Every scraper below follows the same fail-safe contract: it **never** raises or
crashes the pipeline — a missing key or a blocked request just makes that one tool
return no results, silently. "Not working" below means verified silently returning
nothing right now, not a crash.

| Tool | What it does | Why it's used | Status |
|---|---|---|---|
| **Serper** | Google-style search dorking (`site:`/`filetype:`/exact-phrase queries) across the open web. | Described in the project README as "the widest OSINT net" — it covers platforms and content types (PDF/DOC filings, Pastebin leaks, Medium, Pinterest, LinkedIn) that no dedicated username enumerator reaches. | ✅ Working |
| **Brave Search API** | A second, independent search index (not a Google/Bing reseller), run in parallel with Serper for the same dork queries. | Adds recall Serper alone can miss, since Brave's index is built independently. Wired as an ADDITION, not a replacement — its `site:`/`filetype:` operators are documented by Brave as "experimental" and can be silently dropped, so every result is defensively re-verified against the queried domain before being trusted as platform-scoped evidence. | ⚙️ Built this session — needs a key to activate |
| **Maigret** | Checks a username against 500+ site definitions in one pass. | The primary, broadest-coverage username enumerator — the first-pass net for any username seed. | ✅ Working |
| **Sherlock** | A second, independently-implemented username enumerator. | Corroborates Maigret's hits (README: "a second username enumerator"). An account confirmed by two independent detectors is a stronger anchor than one confirmed by a single tool, and each runs its own false-positive control probe. | ✅ Working |
| **Blackbird** | A third username/email enumerator using a different (WhatsMyName-based) site database. | Widens coverage past whatever Maigret + Sherlock's overlapping site lists miss between them; also independently covers email-based enumeration. | ✅ Working |
| **Socialscan** | Checks username/email registration status (taken vs. available) across major platforms. | A third, fast, accuracy-focused corroborating signal for username seeds — distinct implementation from Maigret/Sherlock/Blackbird. | ✅ Working |
| **Holehe** | Checks which of 150+ online services a given EMAIL is registered on. | Username enumerators don't cover emails at all — Holehe is the dedicated tool for "which services does this address use," letting a case be built from just an email seed. | ✅ Working |
| **XposedOrNot** | Checks whether an email has appeared in a known data breach — free, no key required. | Keeps SOME breach-exposure coverage active even with zero paid keys — matches the project's own "full demo runs with no keys" promise. | ✅ Working |
| **Gravatar** | Free avatar-existence check for an email (200/404); with an optional key, a full public profile lookup. | The keyless tier still supplies a real `photo_url` from just an email — that photo feeds directly into the perceptual-hash / face-embedding correlation pipeline, a rare case of a free source producing biometric-grade evidence. | ✅ Working (avatar tier); profile tier needs a key |
| **GitHub API** | Reads a public GitHub profile's bio, followers, and self-disclosed links via GitHub's own API. | Structured, authoritative data straight from the platform (not a guessed search-engine hit) — bio links and stated employer/location are high-quality corroborating fields for the correlation engine. | ✅ Working — token verified live |
| **NumVerify** | Validates a phone number and returns carrier, line type, and country. | Confirms a number is real and geographically plausible before the pipeline spends further scraping budget chasing it. | ✅ Working |
| **Ignorant** | Checks which services (WhatsApp, Instagram, etc.) a phone number is registered on. | The phone-number equivalent of Holehe — dedicated tool for "which platforms use this number." | ✅ Working |
| **Wayback Machine** | Finds an archived historical snapshot of a discovered profile URL. | Evidence integrity: if a suspect deletes an account after realizing they're being investigated, this is what proves the account ever existed — directly answers the project's own framing ("prove these accounts ever existed"). | ✅ Working |
| **UPI module** | Parses and validates Indian UPI (Unified Payments Interface) payment identifiers. | India-specific financial-fraud cases often start from a scam UPI handle; this decodes the bank/PSP portion of the ID as a new investigative seed. | ✅ Working |
| **URL scraper** | Extracts a platform + handle from any arbitrary profile URL. | Lets an investigator start a case directly from a pasted profile link, not only from a raw username/email/phone/UPI value. | ✅ Working |
| **Playwright / Patchright** (stealth Chromium) | Headless browser that renders JavaScript-heavy or bot-blocked pages. | Some data (e.g. Facebook's public "Intro" contact-email box) is invisible to a plain HTTP GET — this is the fallback that actually renders the page the way a browser would. | ✅ Working — browser launch verified live |
| **Face recognition** (YuNet + SFace, ONNX) | Detects a face in a photo and embeds it, so the same face on two different profile photos can be matched. | "Same person, different photo" is one of the correlation engine's hard-anchor signals — strong standalone evidence even when bios/usernames differ. Chosen over dlib specifically because it needs no C++ build toolchain, only a pure-wheel install (relevant for a hackathon judge running this cold on Windows). | ✅ Working — model files present |
| **HIBP** (Have I Been Pwned) | The canonical, most widely recognized breach-database lookup for an email. | Adds the most authoritative breach-check source available — useful evidentiary weight precisely because of its recognizability, despite being paid. | ❌ Not working — no active paid subscription |
| **DeHashed** | Deep leaked-credential / breach-record search. | Covers breach records HIBP/XposedOrNot don't index. Wired as a zero-cost-to-add optional source — activates fully the moment a key is added, no code change needed. | ❌ Not working — no API key configured |
| **LeakCheck** | A second deep breach-record search provider. | Same rationale as DeHashed — a second, independent breach-data provider raises the odds of finding a genuinely leaked record for a given identifier. | ❌ Not working — no API key configured |
| **EmailRep** | Email reputation score plus which platforms it's registered on. | Validates an address is real/deliverable BEFORE the pipeline spends Serper or enumerator budget chasing email-derived pivot guesses. | ❌ Not working — no API key (free tier retired industry-wide) |
| **Reddit scraper** | Pulls a Reddit profile plus REAL posting-time analytics from public post timestamps. | Feeds a genuinely behavioral correlation signal (`posting_hours_overlap`) — WHEN someone is typically active is much harder for a suspect to fake than a bio or username. | ❌ Not working — blocked by Reddit's anti-bot (403); no OAuth app configured |
| **Telegram username lookup** (Telethon) | Looks up a Telegram username's display name and bio. | Telegram is heavily used in Indian cybercrime (scam/phishing channels) and isn't indexed by a normal web search, so a dedicated lookup is needed to cover it at all. | ❌ Not working — bot-token quota exhausted, plus a peer-resolution bug |
| **NewLeaks OSINT bot** | Queries a specialized Telegram bot for leaked PII fields. | An additional breach/PII source reached through a channel none of the HTTP-based scrapers can touch — a Telegram bot conversation. | ❌ Not working — same Telegram issue, plus missing session file |
| **PhoneInfoga** | Deeper phone OSINT/footprinting via a dedicated open-source recon tool. | Goes beyond NumVerify's simple carrier validation into broader footprinting; containerized specifically so it's a one-command dependency, not a manual install. | ❌ Not working — Docker container not currently running |

---

## 3. Infrastructure & Core Libraries

These aren't OSINT sources themselves — they're the framework, storage,
evidence-integrity, and matching-math layers everything else runs on top of. All are
local/self-contained, so there is no external "working / not working" status to
verify — they are simply part of the codebase.

| Component | What it does | Why it's used | Type |
|---|---|---|---|
| **FastAPI + Uvicorn** | The backend web framework and ASGI server. | Async-first by design — matches the pipeline's heavy use of `asyncio.gather()` to fan dozens of scrapers out in parallel per seed; also auto-generates the `/docs` OpenAPI reference. | ⚙️ Core dependency |
| **Next.js 14 + Tailwind CSS** | The investigator-facing web dashboard — case creation, results view, network graph, activity timeline, case chat. | A modern, component-based framework for the UI that consumes the FastAPI backend's REST endpoints. | ⚙️ Core dependency |
| **SQLite** | The application's embedded database (cases, entities, clusters, ledger). | Zero-setup, single-file storage appropriate for a single-machine investigative tool — no separate database server to install or manage. | ⚙️ Core dependency |
| **JWT + bcrypt** | Authentication tokens and password hashing. | Standard, well-audited primitives for the multi-investigator dashboard's login and per-case owner access control. | ⚙️ Core dependency |
| **reportlab + svglib** | Generates the BSA-63 court-format report, executive summary, and Evidence Exhibit Report as PDFs (this document's PDF counterpart was built with reportlab). | Produces the court-facing PDF entirely offline/deterministically — no external PDF-rendering service in the evidence chain, which matters for chain-of-custody integrity. | ⚙️ Core dependency |
| **SHA-256 ledger + RFC-3161 timestamp** (FreeTSA) | Hashes every captured evidence artifact into an append-only chain, and anchors the hash to an externally-issued trusted timestamp. | Court-admissibility: proves evidence existed at a specific time and hasn't been altered since — anchored OUTSIDE VERTEX's own control (an external timestamp authority) so the system itself can't be accused of forging a timestamp. | ⚙️ Core dependency |
| **aksharamukha** | Deterministic ISO-15919 transliteration between scripts (e.g. Kannada, Tamil, Telugu, Malayalam ↔ Latin), plus phonetic-key matching. | Indian suspects' names often appear in multiple native scripts across platforms — this lets the correlation engine match a Kannada-script name against its Latin-script spelling without relying on an LLM's guess. | ⚙️ Core dependency |
| **thefuzz / python-Levenshtein / scikit-learn** | Fuzzy string matching (name/username similarity) and stylometry (cosine similarity of writing style between two accounts' text samples). | Powers several of the correlation engine's 20 signals — `fuzzy_name_match`, `username_fuzzy_match`, and `stylometry_cosine` specifically. | ⚙️ Core dependency |
| **imagehash** | Perceptual hashing (pHash) of profile photos. | A fast, deterministic, non-ML pre-check for "same photo used across platforms" — runs before the heavier ONNX face-embedding path, catching identical/near-identical images cheaply. | ⚙️ Core dependency |
| **Docker Compose** (backend + frontend + PhoneInfoga containers) | One-command reproducible deployment of the full stack. | Lets any investigator or judge stand up the entire system (backend, frontend, PhoneInfoga) in two commands without manually installing Python, Node, or PhoneInfoga's own dependencies. | ⚙️ Core dependency |

---

*Companion PDF: `VERTEX_Tools_Reference.pdf` (same content, print/report-formatted).*
