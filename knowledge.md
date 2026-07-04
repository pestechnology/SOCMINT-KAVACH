# VERTEX / CIDECODE — Comprehensive System Knowledge Base

**VERTEX** is an advanced, NASA-grade SOCMINT (Social Media Intelligence) and OSINT (Open Source Intelligence) suspect-profiling and correlation engine. It combines deterministic cross-platform enumeration with autonomous LLM agents and web exploration to build court-admissible forensic profiles.

---

## 🛠️ 1. All OSINT Tools & Scrapers (`backend/ingestion/` & `tools/`)

VERTEX integrates over 20 specialized reconnaissance modules, designed with a **fail-safe philosophy** (scrapers return empty results on failure without crashing the pipeline).

### Username & Identity Enumeration
* **`blackbird` (`blackbird_scraper.py` / `tools/blackbird`)**: High-speed CLI username enumeration tool scanning 500+ platforms for exact handle matches.
* **`maigret` (`maigret_scraper.py`)**: Deep social network enumeration engine capable of building comprehensive digital footprints from usernames and generating dossier links.
* **`sherlock` (`sherlock_scraper.py`)**: Multi-threaded username scanner checking thousands of websites for account existence.
* **`socialscan` (`socialscan_scraper.py`)**: Ultra-fast email address and username availability/registration checker.
* **`user_scanner` (`user_scanner_scraper.py`)**: Custom asynchronous availability scanner for specialized Indian and international portals.

### Email & Breach Intelligence
* **`holehe` (`holehe_scraper.py`)**: Checks email registration status across 120+ social media and services without alerting the target.
* **`epieos` (`epieos_scraper.py`)**: Enumerates Google IDs, Google Maps review history, Google Calendar, and public profile data tied to an email address.
* **`hibp` (`hibp_scraper.py`)**: **HaveIBeenPwned** API integration for detecting compromised credentials in public data breaches.
* **`leakcheck` (`leakcheck_scraper.py`)**: Queries intelligence databases for exposed PII, passwords, and historical breach records.
* **`dehashed` (`dehashed_scraper.py`)**: Checks cleartext password databases and hashed credential leaks.
* **`xposedornot` (`xposedornot_scraper.py`)**: Open-source breach verification and alert tool.

### Platform-Specific Deep Scrapers
* **`github` (`github_scraper.py`)**: Uses GitHub Tokens to extract commit history, developer email addresses, SSH public keys, starred repositories, and collaborative networks.
* **`telethon` (`telethon_scraper.py`)**: Connects to Telegram via MTProto/Telethon (`TELEGRAM_API_ID`, `TELEGRAM_BOT_TOKEN`) to monitor target groups (`TARGET_GROUP_NAME`), extract user profiles, and track messaging patterns.
* **`facebook` (`facebook_scraper.py`)**: Enumerates public Facebook profiles, pages, and biographical identifiers.
* **`reddit` (`reddit_scraper.py`)**: Extracts user comment history, submission patterns, active subreddits, and textual sentiment.

### Web Dorking, Archives & Enrichment
* **`serper` (`serper_scraper.py`)**: Executes Google Search dorking queries via Serper API to discover mentions, PDFs, and news articles across the web.
* **`url_scraper` (`url_scraper.py`)**: Direct HTML page scraper that fetches target URLs and extracts structured metadata and textual content.
* **`wayback` (`wayback_scraper.py`)**: Queries the Internet Archive (Wayback Machine) to retrieve historical snapshots of deleted social media profiles or websites.
* **`phone_scrapers` (`phone_scrapers.py`)**: Integrates **NumVerify** for global phone number validation, carrier identification, line type, and geographic location.
* **`upi_module` (`upi_module.py`)**: Specialized Indian financial OSINT module verifying UPI IDs and VPAs (Virtual Payment Addresses) against banking name registries.
* **`photo_enrich` (`photo_enrich.py`)**: Extracts profile avatars and performs facial/image cross-referencing.
* **`fact_enrich` (`fact_enrich.py`)**: Analyzes unstructured bio text to extract cross-referency facts (schools, employers, locations).
* **`country_filter` & `fp_filter`**: Geolocation boundary filters and false-positive elimination rules that prune candidates outside the target jurisdiction (e.g., `INDIA`).
* **`variants` (`variants.py`)**: Automatically mutates input seeds (e.g., handle underscores, name order permutations, phone prefixes) to expand investigation recall.

---

## 🧠 2. All LLM Calls & Models (`backend/llm/llm_client.py` & `agentic_browser/`)

VERTEX uses a multi-tier LLM architecture with automatic failover, combining high-reasoning cloud models with multimodal vision models.

### Cloud LLM Providers
* **Primary Engine (NVIDIA Integrate)**: Runs high-precision reasoning models (`NVIDIA_BASE_URL`, default model: `llama-3.3-70b-versatile` or custom NV endpoints).
* **Failover Engine (Groq Cloud)**: Automatically takes over if the primary endpoint throttles or fails (`GROQ_BASE_URL`, model: `llama-3.3-70b-versatile`) for ultra-low latency inference.
* **Vision & Autonomous Navigation Engine (Google Gemini)**: Powered by `gemini-3.1-flash-lite` via `ChatGoogle` for real-time DOM analysis and visual browser automation.

### Specific LLM Call Workflows
1. **`extract_entities(text)`**: Scans free-form unstructured text, scraped bios, or breach dumps to extract JSON-structured entities (names, handles, emails, phones, crypto wallets).
2. **`extract_facts(text)`**: Converts noisy biographical descriptions into structured dossier facts (e.g., current employer, university, hometown, associated links).
3. **`extract_keywords(text, entities)`**: Generates targeted Google dorking keywords and search terms from discovered profiles to feed secondary expansion scans.
4. **`rerank_profiles(seed_type, seed_value, profiles)`**: The core intelligence evaluator. It compares discovered candidate accounts against the verified seed evidence, assigning an AI confidence score (`0-100%`), promoting genuine matches, and discarding homonyms or false positives.
5. **`explain_match(signals, tier)`**: Generates human-readable, court-admissible "AI Examiner Verdicts" explaining *why* a cluster of accounts belongs to the same individual based on overlapping evidence.
6. **`summarize_case(findings)`**: Synthesizes the entire multi-profile investigation into an executive SOCMINT summary for legal briefing.
7. **`semantic_similarity_check(profile_a, profile_b)`**: Performs deep semantic cross-comparison between two ambiguous profiles to determine identity equivalence when exact string matching fails.

---

## 🤖 3. All Autonomous Agents & Pipelines

VERTEX organizes its intelligence operations into specialized, autonomous agent pipelines:

### 1. The Orchestrator Agent (`backend/pipeline/orchestrator.py`)
* **Role**: The central mission controller.
* **What it does**: When an investigation begins, it orchestrates a multi-phase asynchronous scan. It runs Phase 1 (Primary Seed Scan) across all relevant scrapers simultaneously using `asyncio.gather()`, passes discovered clues to `variants.py`, and immediately launches Phase 2 (Expansion Scan) to uncover secondary identities tied to newly discovered usernames or phones.

### 2. The Correlation & Clustering Agent (`backend/correlation/correlation_engine.py`)
* **Role**: The identity resolver.
* **What it does**: Ingests raw profiles from all scrapers and normalizes strings (`_norm`). It constructs an identity graph by linking profiles that share hard signals (exact email, phone, or exact username). It enforces strict NASA-grade evidence rules: a cluster is only formed if `LINK_MIN_SIGNALS >= 2` and `LINK_MIN_POINTS >= 50`, preventing accidental profile merging.

### 3. The Scoring & Reranking Agent (`backend/scoring/scoring_engine.py`, `backend/analysis/reranker.py`)
* **Role**: The quality assurance examiner.
* **What it does**: Evaluates every correlated identity cluster on **two independent axes**:

  **1. Forensic linkage tier** (`scoring_engine.py` → `tier`, `confidence_score`) — answers *"are these accounts the same person?"* Deterministic, governed by the red-herring rule (never links on a single signal), and drives the BSA-63 court report. Tiers: `HIGH` (>75) / `MEDIUM` (50-75) / `LOW` (25-50) / `REJECT` (<25).

  **2. User-facing match confidence** (`scoring/confidence.py` → `match_tier`, `match_score`) — answers *"is this a correct match for what the investigator searched?"* This is what each result card shows. Three tiers only — **`HIGH` / `MEDIUM` / `LOW`**:
    * An **exact username / seed match is always `HIGH`** — the account that literally *is* the searched identifier is the strongest lead, even if it isn't cross-linked to anything.
    * Everything else is graded by a blend of the deterministic correlation strength (algo), the LLM adjudicator's same-person probability (when it confirmed the link), and the LLM reranker's relevance score — where **relevance alone is capped below `HIGH`** (a lead to verify, not a confirmed match). Two independent moderate signals earn a corroboration bonus.

  Match confidence never changes which accounts are *linked* — it only grades and orders results. Exact matches sort first, then by match tier and score.

### 4. The Report & Compliance Agent (`backend/report/bsa63_generator.py`, `backend/ledger/`)
* **Role**: The forensic documentation officer.
* **What it does**: Compiles verified identity clusters into BSA-63 compliant legal reports. It maintains an append-only, tamper-evident audit ledger (`ledger/`) recording every tool execution, timestamp, and raw output. If the analyst flags the subject as a minor (`minor=True`), this agent automatically applies POCSO Act protections by redacting identifying PII from exported reports.

### 5. The Autonomous Agentic Browser (`backend/agentic_browser/`)
* **Role**: The live web explorer (for tools without API keys).
* **What it does**: When traditional APIs are blocked or unavailable, this agent takes control of a real headless Chromium browser via Playwright and `browser-use`. Powered by Gemini multimodal vision (`gemini-3.1-flash-lite`), it dynamically navigates target web portals:
  * **`socialsearcher` template**: Navigates to Social Searcher, executes queries, and extracts live social media mentions across web platforms.
  * **`inflact` template**: Navigates to Inflact Instagram Viewer, handles Cloudflare challenges, searches usernames, and extracts anonymous Instagram bios and metrics.
  * **`custom` template**: Accepts any user-provided URL and plain-English instruction (e.g., *"Go to xyz.com, search for John Doe, and scrape the result table"*), executing clicks, typing, and data extraction autonomously.
* **Honest Reporting**: It extracts *only* what appears on the DOM. If a site enforces an insurmountable CAPTCHA or login wall, it sets status to `blocked` and reports the barrier honestly without fabricating data. Discovered profiles are automatically pushed into the main correlation DB with an `🤖 Agentic` discovery tag.
