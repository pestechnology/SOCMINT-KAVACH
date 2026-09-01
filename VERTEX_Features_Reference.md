# VERTEX — Implemented Features Reference

**SOCMINT / OSINT suspect-profiling pipeline — CIDECODE 2026 · Team KAVACH**

This document catalogs every feature actually implemented in the VERTEX codebase,
organized by pipeline stage (Collect → Resolve → Correlate & Decide → Seal → Report →
Assist) plus the dashboard UI and platform layer. Every entry below is sourced
directly from the code and its own docstrings/comments — nothing here is inferred
from marketing copy alone, and any place where the code disagrees with the README's
own description is called out explicitly rather than glossed over.

> For the external OSINT tools/APIs each feature draws on (and which of them are
> currently live vs. broken), see the companion document
> `VERTEX_Tools_Reference.md` / `.pdf`. This document is about **what the product
> does**, not the live status of any one external dependency.

**Legend:** ✅ Implemented & wired in · ⚠️ Partially implemented / gap found ·
🚧 Explicitly marked incomplete by the project itself

---

## 0. Case Setup & Investigation Options

| Feature | What it does | Status |
|---|---|---|
| **Multi-identifier seeding** | Start a case from any mix of username, email, phone, UPI ID, name, or profile URL — one or several at once. | ✅ |
| **Auto seed-type correction** | A username field with a space is silently re-typed as a "name" seed; a name field with no space is re-typed as "username" — prevents the single most common data-entry mistake (wrong dropdown) from making an investigation return nothing. | ✅ |
| **Minor-involved flag** | A `minor_involved` toggle on case creation, feeding the report layer's POCSO §23 / JJ Act §74 legal citation handling for sensitive cases. | ✅ |
| **Country filter** | `ALL` vs `INDIA`-focused mode; when set to India, `country_filter.py` narrows the discovered-profile set post-collection. | ✅ |
| **Free-text case context** | An optional "what kind of case is this?" description (e.g. "investment fraud through Telegram"). Explicitly documented as **never** used to steer the search itself — only to sharpen the LLM-generated guidance layers (next actions, case chat). | ✅ |
| **Opt-in evidence capture toggle** | `capture_evidence` is off by default per case — court-grade page capture (screenshot/MHTML/DOM + external timestamp) only runs when explicitly turned on for that investigation. | ✅ |

---

## 1. Collect — Automated Multi-Source Data Gathering

| Feature | What it does | Status |
|---|---|---|
| **Parallel multi-source fan-out** | Every seed is dispatched to its full applicable tool set simultaneously via `asyncio.gather`, with `return_exceptions=True` so one failing source never blocks the rest. See `VERTEX_Tools_Reference` for the full per-seed-type tool list. | ✅ |
| **Username permutation engine** | Generates plausible alternate handles from a seed before the first scan even runs — concatenation/separator forms (`ash29_03` → `ash2903`, `ash29.03`) always, plus initial-based forms (`arjun mehta` → `amehta`) only for real alphabetic name tokens, filtered through a noise-handle blocklist so short junk (`a03`, `bot`, `admin`) is never generated as a seed. | ✅ |
| **Username-variant expansion (live mode)** | After the first pass, generates further handle variants (e.g. `j.shankar` / `jshankar` / `shankarj`) and re-runs the fast enumerators on up to 8 of them, to catch the same person using slightly different handles across platforms. | ✅ |
| **Bio-link cascade** | Scans every discovered profile's bio/blog/website fields for URLs pointing to an account not yet found, and feeds up to 5 of them back in as new seeds — one level deep. Shared verbatim between the initial investigation and every re-iteration pivot. | ✅ |
| **Email → username bridging** | An email seed's local-part (`vismay.hs@...` → `vismay.hs`) is automatically run through the full username tool set (Maigret/Sherlock/Blackbird/etc.), since an email search alone never checks social platforms by handle. | ✅ |
| **Targeted LinkedIn search** | LinkedIn blocks the WhatsMyName-style enumeration Maigret/Sherlock/Blackbird rely on, so LinkedIn coverage comes from a dedicated dork built from the raw seed **plus** a name recovered from the handle (`vismayhs` → "Vismay HS") **plus** any real name discovered elsewhere in the case — with an owner-name relevance filter so a hit that merely *mentions* the target (not their own profile) is dropped. | ✅ |
| **Name-based cross-platform search** | Once a real human name is recovered from an enriched profile, searches Facebook/Twitter/Instagram directly by that name — reaching accounts registered under a real-name vanity URL that handle-based enumerators can never find (the specific gap that lets a suspect's separate, real-name Facebook go undiscovered from just their Instagram handle). | ✅ |
| **Archive check** | Every discovered social-account URL (capped at 20 per run) is checked against the Wayback Machine for a historical snapshot — evidence that survives even if the live account is deleted. | ✅ |
| **LLM entity extraction from free text** | Bios and search snippets are run through the LLM (capped at 6 per run to protect the provider's rate budget) to pull out additional email/username candidates a regex alone would miss, each with a deterministic regex fallback. | ✅ |
| **Platform-alias canonicalization** | Different site-list entries that are really the same account (`steamcommunity.com/id/x` vs `steam`, YouTube's several enumerator variants) are collapsed to one canonical platform *before* dedup — otherwise the correlation engine would "match" an account against its own mirror and report it as false evidence. | ✅ |
| **Noise-platform filtering** | Enumerator site definitions that structurally can't produce a real negative (e.g. op.gg's search endpoint returns HTTP 200 for any string) are hard-excluded so they can't flood a case with junk "accounts." | ✅ |
| **Agentic browser** | A real headless browser (browser-use + Playwright, vision-driven by Gemini) for login-gated or JS-heavy sources no plain scraper can reach, under a hard anti-fabrication guardrail — it extracts only what is literally rendered on the page, never invents a field. | 🚧 README marks this "in process"; disabled by default even in the Docker build |

---

## 2. Resolve — Identity Consolidation & Normalization

| Feature | What it does | Status |
|---|---|---|
| **Identity-resolution agent** | Consolidates every account's noisy raw fields (names, handles, bios, snippets, titles, extracted locations/employers) into ONE clean, correctly-classified identity — real names, aliases, location, employer. Built specifically to stop junk like a chess rating ("1796") or a handle ("@vismay_hs") from being shown to the investigator as if it were a real name. | ✅ |
| **Multilingual / Indic normalization** | Script detection, deterministic ISO-15919 transliteration, and phonetic-key generation across Kannada, Tamil, Telugu, and Malayalam — so a name typed in a native script and its Latin-script spelling elsewhere can be matched without relying on an LLM's guess. The original string is always preserved as the evidentiary field alongside the normalized form. | ✅ |
| **Structured profile-page fact extraction** | `socid_extractor` pulls known structured fields (not just a raw scrape) from recognized platform profile pages. | ✅ |
| **Deep bio scraping & LLM fact enrichment** | Employer/city extraction from free-text bios via a constrained LLM prompt, deliberately weighted lower (context-tier, never a hard anchor) than a deterministic NER library would be, to reflect that it's a probabilistic extraction, not a confirmed field. | ✅ |
| **Name plausibility & genericness scoring** | Distinguishes a real human display name from suspect-chosen gibberish ("xk3vzq"), and separately flags common names ("Rahul Sharma") so they require stronger corroboration before anchoring a link — a false-link guard that keeps two different Rahul Sharmas from being merged on name alone. | ✅ |

---

## 3. Correlate & Decide — The Correlation Engine

| Feature | What it does | Status |
|---|---|---|
| **Weighted signal engine** | `SIGNAL_WEIGHTS` in `correlation_engine.py` currently defines **21** named, individually-weighted comparison signals (exact phone/email/UPI/name match, username exact/substring/fuzzy match, fuzzy/phonetic name match, location overlap, profile-photo pHash, face-embedding match, posting-hours overlap, stylometry, breach co-occurrence, bio-keyword overlap, reciprocal mention, bio-URL match, employer overlap, city match, mutual connections). ⚠️ **Note:** the project's own README describes this as a "20-signal engine" — a minor stale rounding versus the current code, not a functional issue. | ✅ (with the noted discrepancy) |
| **`reciprocal_mention` signal — defined but not yet firing** | This signal has a weight (15) and a plain-English explanation string ("mention each other") wired into the report/UI layer, but no code in `correlation_engine.py` was found that actually computes or sets it. It behaves as a placeholder today — it will never fire and can never contribute to a link. | ⚠️ Gap found during this review |
| **Hard-anchor vs. context signal tiers** | 7 signals (`exact_email_match`, `exact_phone_match`, `exact_upi_match`, `profile_photo_phash`, `breach_co_occurrence`, `face_match`, `bio_url_match`) are standalone-sufficient to anchor a link; another 7 (`location_overlap`, `bio_keyword_overlap`, `stylometry_cosine`, `posting_hours_overlap`, `employer_overlap`, `city_match`, `mutual_connections`) are corroborating-only and can never anchor a cluster alone. Username/name-family signals sit between the two, with their own graduated rule (see next row). | ✅ |
| **Graduated name-match anchoring** | An `exact_name_match` can anchor a link with just ONE corroborating context signal; a `fuzzy_name_match` (common names like "Rahul Sharma" vs "Rahul Verma") needs TWO — otherwise two unrelated people sharing a common name and a trivially-shared context signal (e.g. both post in the evening) would false-positive merge. | ✅ |
| **Red-herring rejection rule** | A pair with only one weak signal (e.g. only a matching username) is flagged LOW and explicitly kept **separate**, never force-linked, regardless of how visually similar the accounts look. | ✅ |
| **False-positive filter (control probe)** | Maigret/Sherlock/Blackbird each run a random, meaningless control username in parallel with the real one; any site that "finds" the control username too is auto-excluded from that run's real results, catching enumerator site definitions that are structurally broken (return a false positive for anything). Cached 6h, logged to the audit ledger every run. | ✅ |
| **Confidence tiers** | Every cluster is stamped HIGH / MEDIUM / LOW / REJECT with a plain-English reason built from exactly which signals fired. | ✅ |
| **AI adjudicator** | An LLM reviews a candidate account against the known target holistically (names, handles, bios, locations, interests) for cases a human investigator would confidently link from context alone but the deterministic engine misses — returns a same-person verdict + confidence + plain-English reason, tagged distinctly (`ADJUD`) from forensically-anchored links, and only counted when it actually confirmed the link. | ✅ |
| **Semantic reranker** | Builds a "target persona" (merged keywords/bios/locations/active-hours/names) from already-confirmed clusters, then sends every remaining LOW/REJECT singleton to the LLM in one batch call to catch profiles whose only evidence is semantic (shared interest domain, username variant, bio theme) rather than a rule the deterministic engine can see — tagged as `semantic_rerank_match`, separate from every hard-anchor signal. | ✅ |
| **Stylometry (authorship similarity)** | Compares two accounts' writing style using character n-grams + function-word frequency distribution (not topic/word overlap), specifically chosen to be robust on two short bios where topic-based TF-IDF previously produced false matches. | ✅ |
| **Forensic case summary** | Aggregates sentiment/tone, distinctive keyword/hashtag usage, and active-hour histograms across every account in a case into one investigator-facing forensics block. | ✅ |
| **Bio-keyword stopword curation** | A large (~250-word) curated stopword list prevents generic social-media boilerplate ("follow for more", "check out my videos") from being scored as a matching "keyword overlap" between two total strangers. | ✅ |

---

## 4. Seal — Evidence Integrity & Chain of Custody

| Feature | What it does | Status |
|---|---|---|
| **Court-grade page capture** | Every evidence-worthy page is captured as a self-contained bundle: full-page screenshot, MHTML, post-JavaScript DOM, and a metadata certificate — opt-in per case, runs after the case is already marked complete so results appear instantly and capture never blocks or delays the investigation. | ✅ |
| **SHA-256 hashing of every artifact** | Each captured file is individually hashed at the moment it's captured. | ✅ |
| **External RFC-3161 trusted timestamp** | Every hash is anchored to an independent, externally-issued timestamp (FreeTSA) — proof of "existed at this time, unaltered since" that lives **outside** VERTEX's own control, so the system itself can never be accused of forging a timestamp. | ✅ |
| **Tamper-evident audit ledger** | Every major pipeline step (scrape, cascade, expansion, false-positive filter result, pivot, evidence capture) is written to an append-only SHA-256 hash chain. Idempotent case re-runs clear prior findings but the ledger itself is append-only by design — it is never rewritten. | ✅ |

---

## 5. Reports

| Feature | What it does | Status |
|---|---|---|
| **BSA-63 report** | The primary court-format PDF: findings, a SHA-256 hash annexure, Bharatiya Sakshya Adhiniyam §63(4) certificate templates (Part B left as a template for a qualified expert to sign — never fabricated), and the full chain-of-custody trail. | ✅ |
| **Executive summary report** | A condensed summary PDF of the case for a non-technical reader. | ✅ |
| **Evidence Exhibit Report** | A numbered exhibit-format PDF listing each piece of captured evidence individually. | ✅ |
| **Legal-citation correction** | The project's own README documents that two incorrect citations from the original brief (PMLA §12, CPCR §12) were checked against primary sources and replaced with the correct ones (BNSS §94, POCSO §23 / JJ Act §74). | ✅ |

---

## 6. Assist — Investigator Workflow Tools

| Feature | What it does | Status |
|---|---|---|
| **Kavach case-chat assistant (RAG)** | Free-text Q&A ("which accounts share a phone?", "summarise the strongest link") answered **strictly** from that case's own evidence — a compact structured digest of case state fed as grounded context, hard-constrained so the model can't invent an identifier or fact not actually in the case; has a deterministic fallback if the LLM call fails. | ✅ |
| **Investigative copilot (next actions)** | After scoring, produces a short, ranked list of concrete next steps (corroborate a lead, pivot on a leaked email/phone, reverse-image-search an avatar, pull a breach dump, manually verify before filing) — a deterministic rule engine always seeds a baseline first, with the LLM proposing additions on top, not replacing it. | ✅ |
| **Law-enforcement data-request directory** | A static, verifiable (no scraping, no LLM, nothing invented at runtime) directory mapping each discovered platform to its correct legal data-request portal/contact, plus a BNSS §94 preservation-letter target — resolved automatically against what the case actually found. | ✅ |
| **Re-iteration / cross-pivoting** | Two-step workflow: `pivot/suggest` derives candidate follow-up identifiers for free (guessed emails, recovered names, handle variants, **plus** facts already harvested from the case's own discovered accounts — sorted first since a real discovered fact outranks a guess); `pivot` then runs an explicit, investigator-chosen seed list and merges results back into the SAME case (new accounts inserted, re-scrapes of known accounts merged, never a standalone island), re-correlating everything together. Fully repeatable — each round can seed the next. | ✅ |

---

## 7. Dashboard (Frontend UI)

| Feature | What it does | Status |
|---|---|---|
| **Case dashboard** | Case creation and case list views. | ✅ |
| **Summary tab** | Entity/cluster/identity overview with clickable signal-filter pills (click a correlation signal to see every cluster where it fired, any tier), confidence-tier and platform filters, and staged-selection for re-iteration pivots. | ✅ |
| **Network graph** | Visual account-link graph; above 30 nodes it defaults to showing only clustered nodes (multi-member, or a singleton whose tier isn't REJECT) to "tame the hairball," with a "Show all" toggle. | ✅ |
| **Activity timeline tab** | Shown **only** when at least one entity has real `posting_hours` data — hidden entirely otherwise rather than shown empty. | ✅ (conditional) |
| **Writing & Activity tab** | Shows the forensics block (tone, distinctive keywords, hashtags, active-hours) — shown **only** when forensics actually has a populated field. | ✅ (conditional) |
| **Additional Data / Leak Data tab** | Shown **only** when the NewLeaks bot returned results for that case — every result in it is a breach/PII source, flagged distinctly rather than presented like a verified profile. | ✅ (conditional) |
| **KAVACH CHAT tab** | The case-chat assistant's UI panel, always present. | ✅ |

---

## 8. Platform, Auth & Deployment

| Feature | What it does | Status |
|---|---|---|
| **JWT + bcrypt auth, per-case owner access control** | Standard token auth; every case is only visible/actionable by the user who created it. | ✅ |
| **Docker Compose stack** | Backend + frontend + PhoneInfoga containers, brought up with two commands. | ✅ |
| **Fail-safe-by-design config** | `validate_keys()` warns (never crashes) about missing keys — a missing key disables only the specific tool that needs it; the rest of the pipeline runs identically. | ✅ |
| **Offline mock demo mode** | `DATA_MODE=mock` routes every seed type to a fixed synthetic dataset — the full pipeline (scrape → correlate → score → ledger → PDF) runs completely offline with zero API keys, producing a HIGH-confidence cluster, a correctly-rejected red herring, and a real PDF report. | ✅ |
| **Idempotent re-runs** | Re-running an investigation clears prior entities/clusters for that case before re-scraping, while the audit ledger itself stays append-only and is never rewritten. | ✅ |

---

*Companion documents: `VERTEX_Tools_Reference.md` / `.pdf` (every external tool/API, why it's used, and live working status).*
