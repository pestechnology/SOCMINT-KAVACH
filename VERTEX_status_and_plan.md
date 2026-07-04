# VERTEX — Project Status & Plan

**Date:** June 25, 2026
**Hackathon:** CIDECODE 2026 — Saturday/Sunday July 4-5
**Days remaining:** ~9 days of build, then 24h hackathon

---

## Where we stand right now

### What works today

**Identifier types VERTEX handles correctly:**

| Type | Status | Tools | Notes |
|---|---|---|---|
| Username | ✅ Working | Maigret (500+ sites), GitHub API | Returns ~46 platforms for active users like `torvalds` |
| Email | ✅ Working | holehe | Returns ~17 platforms where email is registered |

**Engine components that work:**

- Live scraping via swappable data source layer
- Parallel scraper fan-out via asyncio
- Photo perceptual hashing computed in parallel
- Response caching in SQLite (24h TTL, configurable)
- Correlation engine with 10 weighted signals
- Red-herring rejection (refuses to link strangers sharing only a username)
- Plain-English "why these are the same person" explanations
- Confidence tiers: HIGH / MEDIUM / LOW / REJECT
- SHA-256 audit ledger with tamper-evident hash chain
- Frontend with dark theme, plain-English UI
- Investigator-friendly results (Strong match / Possible match / Not linked)

**Verified demo:**

Type `torvalds` (username) → ~46 platforms found, 1 MEDIUM-confidence cluster containing the real Linus Torvalds accounts (Disqus, Twitter, Telegram, LiveJournal), 42 singletons correctly NOT merged (they're different people sharing the username string).

This is real working OSINT. Live data. No mocking.

### What's broken or missing

**Known bugs:**

1. **Duplicate platform rows** — when Maigret AND GitHub both return a profile for the same platform/handle, they appear as two cards in the same cluster instead of one merged card.
2. **Holehe platform name parsing** — `any.do` gets stored as `"any"`, header row "email" gets misparsed as a platform name.

**Identifier types NOT yet supported:**

| Type | Status | Tool needed |
|---|---|---|
| Phone number | ❌ Not built | PhoneInfoga + ignorant |
| UPI ID | ❌ Not built | Custom parser → cascade to username search |
| Full name | ❌ Not built | Serper (Google search) for `"Name" "City"` queries |
| Social media URL | ❌ Not built | URL parser → extract handle → username search |
| Photo / face | ❌ Out of scope | Decided not to build |

**Differentiators NOT yet built:**

- BSA-63 court-ready PDF (the moat — most important missing piece)
- Bio-link extraction + iterative seed expansion
- Visualizations beyond results card (graph view, timeline)

### Honest verdict: we are about 40-50% done

The foundation is genuinely solid. The hard architectural decisions (data source layer, swappable scrapers, audit ledger, correlation engine) are all done and proven to work. What's left is:

- Mechanical: adding more scrapers using the established pattern (phone, UPI, name, URL)
- Critical: building the BSA-63 PDF (defensibility moat)
- Polish: bug fixes, UI cleanup, demo rehearsal

---

## What VERTEX will be able to do by hackathon (realistic forecast)

This is what you should promise judges, and what you should NOT promise.

### Promise these — confident

When a judge enters **a real public username** (`naval`, `torvalds`, `pieter`, an Indian dev/influencer with linked socials), VERTEX will:

- Search 500+ platforms via Maigret
- Pull rich profile data from GitHub
- Compute photo similarity across all collected photos
- Cluster accounts that genuinely belong to the same person
- Refuse to merge accounts where evidence is insufficient (this is the strength)
- Generate a BSA-63-compliant court PDF with dual-signature certificate and SHA-256 hashes of every captured artifact
- Show audit trail of every scrape and every decision

When they enter **an email** (`someone@gmail.com`):

- Run holehe to find ~10-30 platforms where it's registered
- Run GitHub API in case the email is publicly listed on a GitHub profile
- Cluster results
- Generate court PDF

When they enter **a phone number** (`+919876543210`):

- Run PhoneInfoga to get carrier, country, validity
- Run ignorant to check WhatsApp/Telegram/Instagram/Amazon/Snapchat registration
- Show which platforms confirm the number is registered

When they enter a **UPI ID** (`arjun@oksbi`):

- Parse bank handle to identify the bank/PSP
- Take the localpart (`arjun`) and run full username search on Maigret + GitHub
- Cluster results

When they enter a **social media URL** (`instagram.com/someone`):

- Extract the handle from the URL
- Run the username search flow

### Don't promise these — honest

When a judge enters **a full name only** (`Rahul Sharma`):

- VERTEX will use Serper to Google-search the name
- Returns candidate profile URLs from search results
- BUT: name searches return many candidates of different people. The system will show them as separate clusters because there's no bridge to merge "Rahul Sharma the lawyer" with "Rahul Sharma the developer."
- Be ready to say: *"Common names produce many candidates. We require additional identifiers — city, photo, or username — to corroborate which one is the suspect. This is intentional — we refuse to claim links we can't defend in court."*

When they enter **a first name alone** (`Rahul`):

- Cannot work. No tool in the world can. Say this honestly.

### What WON'T work no matter what

- **Suspects who actively hide.** Different photo per platform, no cross-links in bios, different usernames everywhere. No tool solves this without insider data.
- **Private accounts.** Instagram private accounts, locked Facebook profiles. We see nothing.
- **Platforms we can't scrape.** Facebook posts, TikTok content, full Twitter timelines — these are walled off without paid APIs.

---

## The pitch to memorize

When judges hand you a test case and you find 4 out of 8 accounts a suspect has, don't apologize. Say this:

> *"VERTEX returned [N] linked accounts at high confidence and [M] at medium confidence. The remaining candidates share only partial signals and would require human investigator judgment to confirm. We chose to refuse low-confidence links rather than risk false positives — those would be inadmissible under BSA Section 63 and could pollute a real prosecution. Here is the court-ready evidence PDF with hash chain. This is how investigative-grade OSINT must work."*

That answer wins. Volume of results doesn't win. Defensibility wins.

---

## Plan for remaining 9 days

### Day 1 (today, June 25 — what's left of it)

**Session 11: Phone scrapers + UPI parser**

- Install PhoneInfoga and ignorant locally
- Build PhoneInfogaScraper, IgnorantScraper, UPIParser
- Wire into orchestrator
- Add UPI→username cascade

Goal: VERTEX now accepts phone and UPI inputs.

### Day 2 (June 26)

**Session 12: Social URL parser + bug fixes**

- URL parser that detects `instagram.com/X`, `twitter.com/X`, etc. and extracts the handle
- Routes the extracted handle through the existing USERNAME flow
- Fix duplicate platform bug (Maigret + GitHub returning same platform)
- Fix holehe platform name parsing

Goal: VERTEX now accepts URLs. Two annoying bugs gone.

### Day 3 (June 27)

**Session 13: Serper integration for full-name search**

- SerperScraper that takes a NAME and Google-searches with multiple queries
- Returns candidate profile URLs from search results
- Each candidate URL gets the URL parser treatment from Day 2
- Honest UI labeling: "name searches return multiple candidates — review manually"

Goal: VERTEX now accepts full names with honest expectations.

### Day 4 (June 28)

**Session 14: Bio-link extraction + iterative expansion**

- Scan every scraped bio for additional emails, usernames, phones
- New identifiers found feed back into the scraper pool
- Max 3 iterations to prevent runaway
- Audit ledger logs each expansion step

Goal: Cross-platform linkage when usernames DIFFER but bios self-disclose.

### Day 5 (June 29)

**Session 15: BSA-63 PDF generator (the moat)**

- ReportLab-based PDF
- Cover page, case summary, findings, annexures of every artifact with SHA-256
- Part A certificate (auto-filled investigator section)
- Part B certificate (hash values, SHA-256 algorithm, expert signature line)
- Chain of custody log

Goal: The court-ready deliverable. Most teams won't build this. This wins the demo.

### Day 6 (June 30)

**Session 16: PDF polish + audit ledger integration**

- Make the PDF look like a real police document (serif headers, conservative styling, no colors)
- Wire ledger entries into the PDF's chain of custody section
- "Verify this report" demo: re-run the search → show same hash → prove no tampering

Goal: BSA-63 PDF goes from working to court-credible.

### Day 7 (July 1)

**Session 17: UI polish + investigator experience**

- Fix any remaining display bugs
- Loading states, error states
- Empty states (no results found, server unreachable, etc.)
- Walk through the full demo flow as an investigator would

Goal: Frontend feels like a real tool, not a hackathon project.

### Day 8 (July 2)

**Session 18: Demo rehearsal + edge cases**

- Run the full demo end-to-end at least 5 times
- Time it (target 5 minutes)
- Practice the honest pitch
- Practice answers to obvious questions ("What about privacy?", "How does this scale?", "What if a suspect uses a VPN?")
- Record a video backup in case live network fails on demo day

Goal: You can demo VERTEX cold, in your sleep, with the network down.

### Day 9 (July 3)

**Buffer / pre-hackathon prep**

- Pack laptops, chargers, ethernet adapter, mobile hotspot
- Test the demo on the actual venue laptop
- Have all dependencies pre-installed
- Sleep early

Goal: Show up to the hackathon ready.

### Day 10-11 (July 4-5) — Hackathon

- 24-hour hackathon
- Integrate whatever test case CCITR gives you (~2-4 hours)
- Polish, demo prep
- Sleep 3 hours
- Present

---

## What success looks like at hackathon

When a CCITR judge hands you a test identifier on July 5:

1. You type it into VERTEX
2. Wait 30-90 seconds while scrapers fan out
3. See a clean dashboard with:
   - 1-3 high-confidence linked clusters
   - Several medium-confidence candidates
   - Singletons clearly marked "not linked"
4. Click "Generate court report"
5. Download a BSA-63-compliant PDF with hash chain, dual-signature certificate, and every captured artifact annexed
6. Show the audit ledger — every search has a unique hash, fully re-verifiable

That's the demo. That's what wins.

---

## Risks to flag

1. **Live network at venue** — College WiFi may block scrapers. Mobile hotspot as backup.
2. **API rate limits** — Serper free tier is 2500 queries. GitHub is 5000/hour. Plan testing carefully.
3. **PhoneInfoga reliability** — Some OSINT scanners it queries are flaky. Failures should be graceful, not crash.
4. **Demo machine** — Set up everything on ONE laptop early in the week. Don't demo from a machine you've never run the system on.
5. **Mentor scope changes** — The mentor confirmed 5 input types. If a judge tests with photo or UPI or something else, have a graceful answer ready.

---

## Bottom line

You will have a working SOCMINT tool that handles 5 input types, refuses false positives, and produces court-admissible evidence packages. You will not have a Maltego-killer. That's the right trade. Quality of evidence beats volume of results for the audience you're presenting to.

---

## ADDENDUM — Current state as of 2026-07-01 (supersedes the June 25 snapshot above)

The "40–50% done" estimate above is **out of date**. Since then the project has been built out and hardened. Current reality:

**Now DONE (was listed as not-built / missing above):**
- ✅ **BSA-63 court PDF** — the moat. Built, polished, and now **tail-safe** (every ledger row self-seals via `chain_hash`, so even the last entry can't be edited undetected).
- ✅ **Phone** (PhoneInfoga + ignorant, fail-safe), **UPI** (parser + bank map + username cascade), **full name** (Serper), **social URL** (parser → username flow). All wired into the orchestrator.
- ✅ **Bio-link extraction + iterative seed expansion** (capped at 5).
- ✅ **Graph view (sigma.js) + timeline (vis-timeline)**, streaming via 1.5 s polling.
- ✅ **48 pytest tests passing.**

**Architecture note:** the LLM engine is **NVIDIA Cloud** (`llama-3.3-70b`, `deepseek-v4-pro`), enhancement-only — *not* Groq, and *not* on the linking path. Caching described above is **not** part of the current design (the demo is live by design; `mock` mode exists for dev/tests only).

**2026-07-01 hardening pass** fixed the ledger tail-row tamper hole, auth status codes (400 vs 409) + token-decode robustness + bcrypt 72-byte handling, subprocess reaping (maigret/ignorant), one un-escaped PDF field, and several frontend issues (graph refresh on score change, reliable 401 handling). Full details: **`context.md` Section 11**.

### 2026-07-01 OSINT expansion (Sprint 1 & 2) — `context.md` Section 12
Two infrastructure bugs were found that had been **silently crippling live collection** (every scraper is fail-safe, so failures returned `[]` with no error):
- **Corporate-TLS failure** — httpx couldn't verify certs behind the TLS-inspection proxy, so archive.org/reddit/breach API **and the NVIDIA LLM** were dead. Fixed with `truststore` (uses the OS cert store; still verifies).
- **CLI tools not on PATH** — `maigret` (the username backbone), holehe, sherlock, blackbird, ignorant all failed to launch (`FileNotFoundError`) → had **never actually run**. Fixed with a shared `resolve_tool()`. Verified live: maigret → 88, sherlock → 99 accounts.

New/real capabilities now working & verified live:
- **Profile-photo / face matching** (perceptual hash) — links the same photo across platforms.
- **Posting-time + frequency / most-active-hours** from real Reddit timestamps (needs Reddit OAuth or a residential IP on this datacenter network).
- **Breach exposure** via free XposedOrNot (no key; HIBP key is a dummy).
- **Email → registered services** via holehe (replaces the dead Epieos/user-scanner stubs).
- **Sherlock** as a 2nd username enumerator (corroborates Maigret) + **username-variant expansion** (`j.shankar`→`jshankar`/`j_shankar`/`shankarj`).
- **Phone path fixed** — was effectively empty (the `site:truecaller.com` Serper dork returns 0 because Truecaller blocks indexing). Now uses **NumVerify** (carrier/line-type/country, key works) + a **plain Serper web search** (~10 web mentions incl. Truecaller/Facebook/Instagram hits) + PhoneInfoga/ignorant if available. Verified: ~11 results per number. (HIBP, which is email-only, and the Facebook-phone stub were removed from the phone path.)

**Known-dead (do not present as working):** Epieos & Facebook-phone are stubs; Telethon uses a bot token and can't resolve arbitrary users; Reddit requires OAuth credentials (CLIENT_ID/SECRET) to avoid 403s. **Deliberately NOT built (myth/inadmissible):** Telegram-IP-from-phone, password harvesting, private story/deleted-post scraping, WhatsApp DP, Truecaller name scraping.

### 2026-07-01 Sprint 3 — forensics layer (`context.md` Section 13)
- **Fixed entity bloat:** a username seed was producing ~170 redundant `url` entities (URL parser re-run on every discovered account URL). Discovered URLs now get a capped Wayback archive check only → `torvalds`+email dropped 379→196 entities, no junk nodes.
- **Linguistic & behavioural forensics** (`backend/analysis/forensics.py`): real **stylometry** (char n-grams + function-word distribution; replaces the weak 2-bio TF-IDF), **sentiment/tone** (VADER, with a negative/hostile-tone flag), **keywords + hashtags**, **activity-hour profile**, **engagement**. Surfaced in a new frontend **Forensics panel** and a report **"2B. Linguistic & Behavioural Forensics"** section.
- **UI contrast round 2:** muted `dim` text `#4A5568`→`#8693A8` (was unreadable on the near-black canvas).
- Verified live; 48 tests pass.

> The single source of truth for current architecture, data flows, and run instructions is **`context.md`** (read Sections 11–14 for the latest deltas). The June-25 "known bugs" list above (duplicate platform rows, holehe parsing) predates the current scraper set and no longer applies.

### 2026-07-01 Sprint 4 — OSINT tool installation + FP hardening (`context.md` Section 14)

**Step 0 — installed the two missing OSINT tools:**

- **`ignorant`** (`pip install ignorant`) — phone registration checker (Instagram/Amazon/Snapchat). Verified: `IgnorantScraper.resolve("+919876543210")` returns `[instagram] registered=True`.
- **Blackbird** (cloned from GitHub, `pip install -r blackbird/requirements.txt`) — WhatsMyName-based username/email enumerator across 680 sites. Verified: 87 profiles for `torvalds`.
  - `resolve_tool()` extended to search `.exe`, `.bat`, `.cmd` on Windows (was `.exe` only) — `blackbird.bat` wrapper in `venv/Scripts/` is found automatically.
  - Three bugs in the old `blackbird_scraper.py` fixed: (1) `--json` writes a *file*, not stdout; (2) JSON field is `"name"` not `"site"`/`"app"`; (3) Windows cp1252 crash on ASCII-art banner fixed with `PYTHONIOENCODING=utf-8` in subprocess env.
  - `BLACKBIRD_PATH` env var added to `.env` so the scraper knows where to find the output file.

**Step 1 — false-positive control-probe filter (all four enumeration tools):**

- Maigret, Sherlock, and Blackbird now each run a random 20-char control username in parallel with the real query. Sites that fire for the control are "broken detectors" and excluded from real results. Cached in `reports/false_positive_sites.json` with a 6-hour TTL.
- Fixed a race condition in `_save_cache`: both tools ran in parallel and the last writer stomped the other's entry. Now does read-merge-write atomically.
- Verified FP exclusions: Maigret **36 sites**, Sherlock **3 sites**, Blackbird **1 site**.
- Socialscan confirmed **0 FP** (uses real registration-flow checks, not HTTP heuristics — no filter needed).
- Garbage username (`zzqxwv847629nonexistent`) before filter: ~43 Maigret hits; after: **6 slip through** (sites whose broken detection isn't exposed by the hex-format control probe — known limitation).

**Steps 2 & 3** (og:image photo enrichment, frontend confidence labels, PDF status column, lead reverification) were implemented in the prior sprint and remain unchanged.

**Test count: 71 pytest tests passing** (was 48 → 59 → 71).

### 2026-07-01 Sprint 5 — name-search fixes, Serper URL extraction, frontend (`context.md` Section 16)

This sprint fixes a cluster of bugs that made name-seed investigations slow, visually empty, and miss the most obvious profiles (LinkedIn, Instagram).

### 1. Name-seed profiles had no `metadata["name"]` → 0 correlation signals → invisible results

The correlation engine's `exact_name_match` signal (35 pts) reads `p.metadata["name"]`. The orchestrator stamped `metadata["email"]`, `metadata["username"]`, etc. for every seed type, but `"name"` was not in the list, so every Serper profile for a name seed had an empty metadata dict and scored 0 against every other profile. All three Serper profiles (LinkedIn, Instagram, Twitter) were REJECT singletons — the UI showed nothing.

Fix (`backend/pipeline/orchestrator.py`): added `"name"` to the seed-stamp loop:

```python
if seed_type in {"email", "phone", "username", "name"}:
    for p in profiles:
        if seed_type not in p.metadata:
            p.metadata[seed_type] = value
```

Now `exact_name_match` fires between all three Serper profiles → 35 pts each pair, 2 signals → qualifies for a HIGH cluster under the red-herring rule (≥ 2 signals, ≥ 50 pts).

### 2. Serper profiles stored page titles as `value`, not the actual handle → username correlation missed everything

Before this fix, `SerperScraper._run_live()` stored the Google page title ("Vismay HS - Student at PES University | LinkedIn") as the profile `value`. When the correlation engine's `_username_signal()` compared that against the GitHub/Maigret value `"VismayHS"`, the fuzzy ratio was 23% → no match. The LinkedIn profile was missed even when it was the top result.

Fix (`backend/ingestion/serper_scraper.py`): added `_extract_social_username(url, platform)` which parses the URL path and returns the handle portion.

- LinkedIn: `/in/{username}/...` → `parts[1]` (requires `parts[0] == "in"`)
- Instagram/Twitter/TikTok: `/{username}` if `parts[0]` not in `_NON_USERNAME_SEGMENTS`
- GitHub/GitLab: `/{username}` for single-segment paths
- Reddit: `/u/{username}` or `/user/{username}`
- Instagram post URLs (`/p/abc123`, `/reel/...`) → `None` (blocked by denylist)

`_NON_USERNAME_SEGMENTS` denylist covers: `p`, `reel`, `reels`, `explore`, `stories`, `i`, `tv`, `watch`, `channel`, `user`, `c`, `hashtag`, `trending`, `shorts`, `status`, `intent`, `search`, `home`, `feed`, `jobs`, `company`, `school`, `posts`, `pulse`, `wiki`, `comments`, `r`.

The extracted handle becomes the profile `value`; the original page title is saved in `metadata["title"]` for display. When no handle can be extracted, the page title falls back as before (graceful degradation for unexpected URL shapes).

Combined effect for a `name` seed `"VismayHS"`:

- LinkedIn `/in/vismayhs` → `value = "vismayhs"` → `username_exact_match` vs Maigret (45 pts) + `exact_name_match` (35 pts) = **80 pts, 2 signals → HIGH**

### 3. Wayback archive check ran on Serper (web_mention) profiles → ~15 s wasted per name search

The orchestrator iterated over all profiles for Wayback deduplication, including `web_mention` type. Serper results are always live (they're Google search results), so checking their archive status is meaningless — and with 20 profiles it added up to 15 seconds of dead-wait.

Fix (`backend/pipeline/orchestrator.py`): filter out `web_mention` type from the set of URLs fed to Wayback:

```python
seen_account_urls = {p.source_url for p in all_profiles
                     if p.source_url and p.source_url.startswith("http")
                     and p.type != "web_mention"}
```

### 4. "UNLINKED ACCOUNTS" section auto-collapsed when no clusters existed → blank page on name searches

When a name search produced 3 singleton LOW profiles (or 0 clusters before the metadata fix), the UI showed a blank "complete" state because the unlinked section was collapsed by default. Users had to know to click "▸ expand" to see anything.

Fix (`frontend/app/cases/[id]/page.js`):

- Auto-expand the unlinked section when `status === "complete" && multi.length === 0`
- Toggle button label updates to reflect auto-expand state
- Account cards now show the page title as a subtitle (`metadata.title`) in smaller dim text beneath the handle, so users can see "Vismay HS - Student at PES University..." alongside `vismayhs`
- Unlinked reason text: "Single signal — insufficient to link across platforms" (was "Not enough signals to link across platforms") for profiles with signals, or "No corroborating signals found" for true singletons

**What the "PES University" keyword came from:**

`forensics.summarize()` extracts keywords from all entity snippets and bios. Serper returns the Google snippet of the indexed LinkedIn page ("Vismay HS · Student at PES University, Bengaluru"), which becomes the entity's `metadata["snippet"]`. The forensics engine pulls "PES University" from that snippet. This happens **without visiting LinkedIn** — it's data from Google's index.

**No test regressions:** 71 tests still pass after all changes.

---

## 2026-07-02 Sprint 6 & Thursday Hotfixes (`ashwin-thurs` — Commit `cd9ac0b`)

### 1. Seed Auto-Correction & Name-Search Hardening (`backend/pipeline/orchestrator.py`)
- **Auto-Correction:** When users input a full name with spaces (e.g., `"ashwin harish"`) while the seed dropdown is set to `username`, Step 1 automatically converts `seed["type"] = "name"`.
- **Targeted Permutations:** Username permutation expansion (generating `ashwinharish`, `aharish`, etc.) is guarded to only execute for single-token username seeds without spaces. Full-name searches proceed directly to Serper site searches (`site:linkedin.com/in`, `site:github.com`, `site:instagram.com`, `site:twitter.com`) to find authentic profiles first.
- **Empty Metadata Filter:** Added `_has_content_metadata` check to drop profiles containing only structural boilerplate fields and zero substantive user data.

### 2. Numeric/Short Suffix Variant Guard (`backend/ingestion/variants.py`)
- For usernames like `"ash29_03"`, the first-initial rule `toks[0][0] + toks[-1]` previously generated `"a03"`, flooding results with false positives. Restricted the rule to only apply when `toks[-1]` is not digits and has length $\ge 3$.

### 3. Scraper Timeout Optimization & UI Polish
- Reduced CLI tool timeouts across **Sherlock** (60s), **Blackbird** (60s), and **Maigret** (90s) to fail fast on unresponsive target platforms.
- Restored real-time scanning progress feed (`logLines`) in the left panel of `frontend/app/cases/[id]/page.js` while a case is running.
- Middle panel now displays the interactive `<NetworkGraph />` correlation chart by default when no card is selected, smoothly transitioning to Account Details upon clicking a node, with an **✕ Close Details** button.

**Test status:** 76 tests pass. `npm run build` clean.

---

## 2026-07-02 Correlation-accuracy precision audit

Full audit of every matching/scoring function in `correlation_engine.py`,
`scoring_engine.py`, `fp_filter.py`, and `reranker.py`, tracing each signal for false
positives (unrelated accounts merged) and false negatives (real matches missed). Full
detail: `context.md` §19.

### 1. SEVERE — LLM reranker could single-handedly confirm an unlinked account (`backend/analysis/reranker.py`)

A high-relevance singleton with zero hard signals had its `confidence_score`/`tier`
directly overwritten by the raw LLM relevance number — the LLM alone could produce a
"HIGH"/"CONFIRMED" cluster. Fixed: LLM relevance now lives only in `relevance_score`
(a lead-ordering field, surfaced as "a lead to verify, not a confirmed link") and
never touches `confidence_score`/`tier`.

### 2. SEVERE — promoting a singleton into a cluster upgraded that cluster's tier on LLM evidence alone (`reranker.py`)

Merging a promoted singleton added a `semantic_rerank_match` signal and recomputed the
tier from the new point total, with no hard-anchor check — two LLM calls could push a
MEDIUM cluster to HIGH. Fixed: promotion adds the member (recall) but `confidence`/
`tier` are pinned to the pre-promotion values (precision).

### 3. MODERATE — common name + one weak signal counted as a hard anchor (`scoring_engine._has_hard_anchor`)

Two different "Rahul Sharma"/"Rahul Verma" accounts both posting in the evening could
hard-anchor and reach HIGH. Fixed: `fuzzy_name_match` (common names) now needs 2
independent context signals to anchor; `exact_name_match` still needs only 1.

### 4. MODERATE — photo pHash hard-anchor threshold too loose (`correlation_engine._photo_match`)

Hamming distance `<8` sat inside the ambiguous same-vs-different-photo band. Tightened
to `<6`.

### 5-6. LOW — two smaller fixes

Username substring matching on 2-char fragments, and a negative Jaro-Winkler match
window on very short strings. Both fixed.

**Test status:** 84 tests pass (6 new regressions, `tests/test_reranker_precision.py` + additions to `tests/test_scoring.py`). Red-herring rule untouched.

---

## 2026-07-02 "More signal, more data" — six new evidence sources

Added six new, API-verified correlation signals without reopening the precision fixes
above. Every new signal is weighted and classified hard-anchor/context in
`scoring_engine.py`; every new scraper/enrichment step fails safe when its API
key/model is absent. Full detail: `context.md` §20.

1. **Real face matching** (`face_match`, hard anchor, weight 40) — `photo_enrich.py`
   now computes a 128-d SFace face embedding (OpenCV Zoo's YuNet+SFace ONNX models,
   chosen over `face_recognition`/dlib because dlib has no prebuilt Windows wheel here
   and needs a CMake/MSVC toolchain this machine doesn't have). Threshold cosine
   ≥ 0.363 is OpenCV's own calibrated same-person cutoff, not guessed. The `"face"`
   seed type (previously a dead hook) is now wired: a reference photo's embedding is
   compared against every discovered profile automatically. Models are ~37 MB,
   fetched once via `python backend/scripts/download_face_models.py`, not committed
   to git.
2. **Bio/description link extraction** (`bio_url_match`, hard anchor, weight 55) —
   self-disclosed cross-platform links in a bio (e.g. a GitHub bio linking the exact
   Twitter account independently discovered) now fire a signal; bio URLs to
   NOT-yet-discovered accounts are cascaded in as new seeds.
3. **Structured fact extraction** (`employer_overlap` weight 16, `city_match` weight
   14, both context-tier) — LLM-based NER-style extraction of employer/school and city
   mentions from bio text (`fact_enrich.py`), chosen over spaCy to avoid a second
   binary-model-download dependency in one pass.
4. **Mutual connections** (`mutual_connections`, context-tier, 10/20 tiered) — GitHub
   followers sample (≤100), weighted by shared-follower count: <2 is noise, 2-4 is
   weak, 5+ is the ceiling weight.
5. **Expanded Google-dork coverage** — `filetype:pdf/doc`, `site:medium.com`,
   `site:pinterest.com`, `site:pastebin.com` (flagged `sensitive_source` — lower
   confidence, higher sensitivity) added to the name-seed dork list.
6. **DeHashed + LeakCheck breach scrapers** — fully implemented, feed the same
   `metadata["breaches"]` field HIBP/XposedOrNot already populate (zero
   correlation-engine changes needed). **Stubbed in this environment** — no paid key
   available; both return `[]` exactly like every other optional-key scraper does.

**Test status:** 101 tests pass (17 new regressions in `tests/test_new_signals.py`).
`npm run build` reconfirmed clean — no frontend files touched in this backend-only
pass. Signal count: 15 → 20.

**Test Status:** 76/76 unit and integration tests passing cleanly. Next.js production build (`npm run build`) compiles with zero errors.
