# VERTEX — Re-iteration / Identifier Cross-Pivoting & the New Search Sources

**What this document is:** a complete, standalone explanation of the re-iteration
("pivoting") system added to VERTEX, and the search-side improvements that came with it
— three new Tier-1 OSINT sources, an automatic email→username bridge, generalised
bio-link scraping, deterministic fact extraction, and a real bug fix for cases where
re-running an investigation appeared to change nothing. Every claim in this document is
grounded in the actual code and was verified — either by a passing test or a live run
against the running backend — not asserted from memory. File/function names are exact.

For the terse, dated changelog-style summary, see `context.md` §21 and
`VERTEX_status_and_plan.md`'s entry for 2026-07-04/05.

---

## 1. The problem this solves

A single search finds a first cluster of accounts. Often the real gains come AFTER
that — the discovered GitHub bio mentions a real name, that name has its own accounts,
the GitHub's `blog` field links to a Twitter nobody had searched for yet. Before this
work, none of that follow-up happened automatically or manually:

- An email seed never tried the local part as a username, so email-only searches
  routinely found breach records but missed the person's actual social accounts.
- Nothing followed a bio's self-disclosed links to NEW accounts except a single
  bio-text scan — GitHub's own `blog` field (frequently a LinkedIn/Twitter/personal
  site link) was captured but never read by anything.
- Employer/school/city extraction was 100% dependent on an LLM call succeeding; if the
  provider was rate-limited, those fields silently came back empty with no fallback.
- Worst of all: if you manually re-ran an investigation on an account you already had,
  and that re-scrape learned something new (a name, a linked account), it was
  **thrown away** — `ingest_external_profiles` treated a re-scraped account as a
  duplicate (matching `sha256`) and skipped it entirely. Re-running the exact same
  search could never make the case grow.

This work fixes all of that, and adds a deliberate, investigator-controlled way to
select what to search next instead of guessing — "re-iteration."

---

## 2. What re-iteration actually is (the UX model)

Re-iteration is **multi-select, not per-item**. Locked decision (explicit user
feedback mid-session, overriding an earlier per-account-button design): there is
exactly ONE persistent control, not a button scattered on every result.

1. **Everything is selectable.** Every discovered account in the identity list has a
   checkbox. Every name/alias and every profile picture in the Summary tab is
   **draggable** (native HTML5 drag-and-drop) and also clickable as a shortcut.
2. **One staging tray.** Whatever you check or drag lands in a single persistent tray
   — a dashed drop-zone fixed above a floating "Re-iterate (N)" button, bottom-right,
   always visible so the drop target is discoverable even with nothing staged yet.
3. **One combined run.** Opening the tray (click the button) shows:
   - what's staged,
   - **suggested identifiers** derived from the staged selection (guessed emails,
     recovered names, handle variants, AND facts already scraped from those accounts
     — a real name, an employer/school, a bio-linked handle — each individually
     checkable),
   - a manual "type your own" field (pick a type, type a value, add it to the batch),
   - an estimated Serper-query cost for the final combined list.
   Clicking Run fires ONE pivot with everything selected — not one search per item.
4. **Repeatable.** After a run completes, the tray clears and the case's result set is
   larger; you select a NEW batch from it and run again. That's the whole point of
   the name "re-iteration" — it's meant to be done more than once.

---

## 3. Architecture — how a re-iterate run actually works end to end

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │  FRONTEND (frontend/app/cases/[id]/page.js, components/ui/ReiterateBar.jsx)│
 │                                                                       │
 │  AccountCard checkbox ──┐                                            │
 │  Name/alias drag+click ─┼──► stagedSeeds: Map<key,{type,value,...}> │
 │  Profile photo drag+click ┘        (unified staging state)          │
 │                                          │                           │
 │                              click "Re-iterate (N)"                 │
 │                                          ▼                           │
 │                          POST /cases/{id}/pivot/suggest              │
 │                          { seeds: [staged {type,value}...] }         │
 │                                          │                           │
 │              suggestions (name/handle/email guesses +                │
 │              facts harvested from those accounts' own bios)         │
 │                                          │                           │
 │            check some suggestions, add manual identifiers            │
 │                                          ▼                           │
 │                             POST /cases/{id}/pivot                   │
 │                    { seeds: [ALL final {type,value,strategy}] }      │
 └───────────────────────────────────┬───────────────────────────────────┘
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │  BACKEND (backend/pipeline/orchestrator.py)                          │
 │                                                                       │
 │  run_pivot_seeds_sync()  — Windows ProactorEventLoop wrapper         │
 │       │                    (same requirement as run_investigation_sync;│
 │       │                     without it, Maigret/Sherlock/Blackbird/  │
 │       │                     Holehe subprocess calls silently return [])│
 │       ▼                                                              │
 │  run_pivot_seeds(case_id, seeds)                                     │
 │    1. status → "running"; log_action("pivot_started")                │
 │    2. append new seeds to cases.seeds_json (audit trail)             │
 │    3. _scrape_pivot_seed() per seed — normal _scrape_seed() for      │
 │       username/name/email/phone/upi/url; build_face_seed_profile()   │
 │       for "face" seeds (gated DATA_MODE=="live")                     │
 │    4. bio_link_seeds() — follow bio/blog/website links to NEW        │
 │       accounts not yet in the case; scrape those too                │
 │    5. (live) enrich_profiles_from_page, enrich_photos, enrich_facts, │
 │       enrich_via_socid — same enrichment run_investigation uses      │
 │    6. ingest_external_profiles(case_id, all_profiles)                │
 │         → genuinely new sha256  = INSERT new entity                 │
 │         → sha256 already exists = _merge_metadata() into it          │
 │           (fills gaps, unions lists, never overwrites — this is     │
 │            the "re-running found nothing" fix)                       │
 │         → re-correlate + re-score the WHOLE case                     │
 │    7. log_action("pivot_complete"); status → "complete"              │
 └─────────────────────────────────────────────────────────────────────┘
                                      │
                     poller (existing) picks up status flip,
                     entities/clusters stream into the SAME case
```

---

## 4. The derivation engine — `backend/ingestion/derive.py`

Pure stdlib, deterministic, no network calls. `derive_seeds(seed_type, value)` is the
router every other part of this system calls.

### 4.1 Routing rules

| Input seed | Produces |
|---|---|
| `username` (e.g. `"vismayhs"`) | 5 guessed emails (`{value}@{gmail,yahoo,outlook,protonmail,icloud}.com`) + a recovered name guess + handle variants **recombined through that recovered name** |
| `name` (e.g. `"Vismay HS"`) | handle variants directly (`username_variants` already handles a spaced name) + a compact-form guessed email |
| `email` (e.g. `"vismayhs@gmail.com"`) | the local part treated as a full username seed (handles + name guesses), i.e. the same machinery entered from the other side |

The username→handle-variant path deserves explanation because it's the least
obvious: `username_variants()` (pre-existing helper) can only recombine ALREADY
tokenized words — it can't split an opaque blob like `"vismayhs"` into `vismay`+`hs`
on its own. So for a username seed, `derive_seeds` first recovers a name via
`names_from_handle("vismayhs")` → `"Vismay HS"`, THEN feeds that recovered name back
into `username_variants("Vismay HS")` → `vismay_hs`, `vismay.hs`, `hsvismay`,
`hs.vismay`. This two-step bounce through the name is what makes the split possible
at all.

### 4.2 Name recovery — `names_from_handle(handle)`

1. Split on separators/camelCase first: `"vismay_hs"` → tokens `["vismay","hs"]` →
   `"Vismay Hs"` (simple title-case join).
2. If the handle is ONE opaque token (no separators), find the **longest** known
   first name (from `backend/analysis/name_intel._COMMON_FIRST_NAMES`) that prefixes
   it. `"vismayhs"` starts with `"vismay"` (a known first name); the ≤3-char
   remainder `"hs"` is treated as initials → `"Vismay HS"`. A longer remainder that
   itself looks like a name is title-cased instead of uppercased.
3. Last resort: de-number and title-case the whole token as a mononym
   (`"ghostrider99"` → `"Ghostrider"`).

Every candidate is gated through `is_plausible_name()`/`is_generic_name()`
(pre-existing helpers) — a lone common first name like `"arjun"` by itself is
**never** surfaced as a "recovered" name, because it isn't identifying evidence on
its own (same rule `resolve_cluster_identity`'s leak-account pivot already applies).

### 4.3 Budget & safety

- `MAX_DERIVED_SEEDS = 20` caps one `derive_seeds()` call.
- `estimate_query_count(derived)` counts how many of a candidate list are
  query-bearing types (username/name/email — phone/upi/url have no derivation
  strategy today), used for the UI's "will use ~N Serper queries" line.
- `_valid_handle()` reuses `orchestrator._is_valid_expansion_handle` (the same
  noise-handle/length guard the rest of the pipeline uses) via a **lazy import
  inside the function body**, not at module top — `orchestrator.py` imports
  `derive_seeds` at its own top level, so importing the other way at module scope
  would be circular. This mirrors an existing pattern already used elsewhere in this
  codebase (`case_service.get_results`'s lazy `name_intel` import).
- Every strategy is a string tag (`username_to_email_guess`, `email_local_part`,
  etc.) carried on the returned dict — this is what the frontend shows as "guessed
  email" / "recovered name" / "handle variant" next to each suggestion.

---

## 5. Three new Tier-1 search sources

All three are wired into `_seed_tool_map()`'s `"email"` list, alongside HIBP/Holehe/
DeHashed/etc. — they run automatically on any email seed (initial search or pivot),
no separate opt-in needed beyond having a key where one is required.

### 5.1 Gravatar — `backend/ingestion/gravatar_scraper.py`

**Verified live against the real API on 2026-07-04** (not assumed from older docs):

- **Avatar-existence check** — `GET /avatar/{sha256(email)}?d=404`. Genuinely free,
  no key: 200 means this email has a Gravatar-linked avatar; 404 means none. Confirmed
  by testing both a random email (404) and a known public Gravatar account (200). The
  resulting `photo_url` feeds the EXISTING pHash/face-embedding pipeline like any
  other discovered photo — no new correlation code.
- **Rich profile** (display name, verified linked accounts) via
  `api.gravatar.com/v3/profiles/{hash}` — despite older documentation calling this
  "free, no key," Automattic now requires an API key (`Authorization: Bearer`) even
  for a public profile. Confirmed live: querying a KNOWN public Gravatar account
  (200 on the avatar endpoint) still returned `404 {"error":"Profile not found"}` on
  the v3 profile endpoint with no key attached. Gated behind optional
  `config.GRAVATAR_API_KEY`; skipped (not an error) when unset.
- When verified linked accounts ARE available, they're folded into
  `metadata["bio"]` — this lets the EXISTING `bio_url_match` signal
  (`correlation_engine.py`) fire on them with zero new signal-wiring.

### 5.2 EmailRep — `backend/ingestion/emailrep_scraper.py`

**Also verified live on 2026-07-04**: the unauthenticated endpoint now returns
`HTTP 429 {"status":"fail","reason":"the unauthenticated API is currently disabled.
please use an API key"}` — contrary to older "free" documentation, a key
(`config.EMAILREP_API_KEY`) is required for ANY lookup now, not just deeper ones.
Once configured:

- Returns one `"email_registration"`-type profile per platform in
  `details.profiles` — deliberately mirrors `holehe_scraper.py`'s exact shape, so it
  rides the same breach/registration corroboration path with zero new correlation
  code.
- Also exposes `is_valid_recipient(email)` (disposable/deliverable check) for future
  use as a pre-flight validity gate before spending a heavier lookup on a guessed
  email — not currently called anywhere, available for a future pivot-cost
  optimization.

### 5.3 socid_extractor — `backend/ingestion/socid_enrich.py`

Wraps `socid_extractor` (github.com/soxoj/socid-extractor — confirmed already
installed in this venv at v0.0.27 before this work started; now also added to
`requirements.txt`, which it was missing from, so a fresh clone won't silently lack
it). `enrich_via_socid(profiles)` fetches the page for any profile still missing a
name and runs the library's per-platform regex/JSON schemes against it — these cover
richer, site-specific structured fields than the generic Open Graph tags
`profile_page_fetcher.py` already extracts.

Maps whatever it recovers into `metadata["name"]`/`["fullname"]`/`["location"]`/
`["dob_candidate"]` — the SAME fields `profile_page_fetcher.py` already writes,
gated through `is_plausible_name()` the same way, so `exact_name_match`/
`location_overlap` fire on it automatically. Wired into BOTH `run_investigation`'s
enrichment sequence (after `enrich_facts`) and `run_pivot_seeds`.

### 5.4 Deliberately NOT built: GHunt

GHunt (gmail → Google Maps reviews/YouTube/real name via scraped session cookies)
was explicitly flagged to the user and skipped rather than silently built — it
relies on undocumented Google internal endpoints and burner-account cookies, which
is meaningfully more ToS-gray than the other three sources (all documented,
official APIs). It was already marked optional/off-by-default in the original plan;
this document records the decision to not implement it at all, pending explicit
confirmation if it's ever wanted.

---

## 6. Automatic email→username bridge (`run_investigation`, new step 1.5)

**The concrete gap this closes:** an email seed's own tool list (HIBP, Holehe,
DeHashed, GitHub-by-email, Gravatar, EmailRep, and a literal Serper search for the
exact email string) never checks social platforms by handle — none of those tools
split the email at `@` and try the result as a fresh username. A real user report
during this work: entering `vismayhs@gmail.com` found breach/registration data but
NOT the Instagram account, even though `github.com/vismayhs` existed and was
trivially findable by username search.

**Fix:** a new step **1.5** in `run_investigation`, immediately after the existing
Username Permutation Engine and before the primary scrape loop. For every `email`
seed, it derives ONLY the `email_local_part` strategy from
`derive_seeds("email", value)` — deliberately not the 5 guessed-email-provider
candidates or name-guess strategies, which stay pivot-only (manual, budget-visible)
— and appends it to `expanded_seeds` as a real `"username"` seed. Because it's
injected into the seed list itself rather than bolted on afterward, it automatically
benefits from the EXISTING username-variant-expansion step too, for free.

Resulting profiles carry `metadata["derived_via"] = {"strategy": "email_local_part",
"from_value": "<email>"}` for provenance in the UI/report. Verified both by
`tests/test_email_bridge.py` (3 tests: fires, doesn't duplicate an explicit username
seed, skips invalid/noise local parts) and a live drive
(`vismayhs@gmail.com` → real Facebook/YouTube/GitHub hits tagged with the bridge).

---

## 7. Deep bio scraping — generalised bio-link cascade

### 7.1 The gap

The ORIGINAL bio-link cascade only scanned `metadata["bio"]`/`["snippet"]` text for
embedded URLs. GitHub's own `blog` field — frequently a LinkedIn/Twitter/personal
site link — was captured by `github_scraper.py` but **never read by anything**
(confirmed by grepping the entire backend for `"blog"` usage before touching it: one
hit, the field being written, zero reads).

### 7.2 The fix — `orchestrator.bio_link_seeds(profiles, already, cap=5)`

A single shared helper, now used by BOTH `run_investigation` (replacing its old
inline loop verbatim) and `run_pivot_seeds` (which had NO bio-link cascade at all
before this work). It scans two kinds of fields:

- `_TEXT_LINK_FIELDS = (bio, snippet, text_sample)` — free text, URLs extracted
  as-is via the existing `extract_bio_urls()`.
- `_URL_LINK_FIELDS = (blog, website, url, external_url, homepage, links)` —
  dedicated URL fields, each **normalised** through `_normalize_url()` first.

**A second real bug found and fixed while building this:** GitHub returns `blog`
**scheme-less** — `"danabra.mov"` or `"twitter.com/foo"` with no `https://` prefix.
The existing URL-extraction regex requires a scheme and silently missed these.
`_normalize_url()` prepends `https://` only to strings that are domain-shaped
(`_BARE_DOMAIN_RE`) — a bare personal site with no social handle
(`"danabra.mov"`) correctly still yields nothing (there's no handle to extract), a
scheme-less social link (`"twitter.com/vismay_hs"`) is now followed correctly.
Verified: `test_bio_link_seeds_normalizes_scheme_less_blog`.

### 7.3 Deterministic fact-extraction fallback — `fact_enrich.deterministic_facts()`

`enrich_facts()`'s employer/school/city extraction was 100% LLM-dependent with no
fallback path. This was caught live during this session's own work: Groq returned
`HTTP 429`, NVIDIA timed out, and `extract_facts()` silently returned empty facts for
every profile in the run. New `deterministic_facts(text)` runs unconditionally
alongside the LLM call, and the two results are unioned (deduplicated,
case-insensitive):

- `_ROLE_AT_RE` — `"<role> at/@ <Proper Noun>"` (works/studies/student/intern/SDE/
  founder/etc. followed by "at" or "@").
- `_INSTITUTION_RE` — `<Proper Noun...> University|College|Institute|...`.
- `_ACRONYM_INST_RE` — well-known Indian institute acronyms (IIT, NIT, IIIT, BITS,
  VIT, PES, RVCE, ...).
- `_CITY_RE` — only unambiguous cues (`based in` / `lives in` / `📍` / `location:`).
  Deliberately excludes a bare `"from X"` cue — it mis-fires on text like
  `"photos from Ashwin"` (the same false-positive `profile_page_fetcher.py`'s own
  location extractor already avoids for the identical reason).

All three proper-noun patterns use a token class with **no interior period**
(`_TOK = r"[A-Z][A-Za-z0-9&'-]*"`) specifically so a sentence-ending
`"University."` can't swallow the next sentence's first word — a real bug caught
and fixed during this session's own testing (an early version of the regex mangled
`"Student at PES University. Based in Bengaluru. Loves ML."` into
`"PES University. Based"` before the token class was tightened). `_GENERIC_ORG`
blocks bare words like `"university"`/`"college"` from ever standing alone as a
candidate — they'd manufacture a false `employer_overlap` between two unrelated
people otherwise. Stays context-tier evidence only (no `scoring_engine.py` change —
that file is explicitly DO NOT MODIFY).

---

## 8. The core fix — re-running now actually changes something

### 8.1 Root cause (three parts, all confirmed against the running code)

1. **The big one:** `ingest_external_profiles` skipped any re-scraped profile whose
   `sha256` matched an existing entity. So if you re-iterated on an account you
   already had, and that re-scrape found something new (a name, a linked account,
   an employer), it was silently discarded — the stored entity never changed.
2. `run_pivot_seeds` ran no bio-link cascade at all before this session (fixed in
   §7.2) — so re-iterating on a GitHub account never even LOOKED at its `blog`
   field's LinkedIn/Twitter link.
3. Fact extraction was LLM-only with no fallback (fixed in §7.3) — so even when a
   bio DID get re-read, employer/school/city extraction could silently fail.

### 8.2 The fix — `_merge_metadata()` + a rewritten `ingest_external_profiles`

New `_merge_metadata(existing, incoming)`:
- Fills a gap (`existing[k]` empty) from `incoming[k]`.
- **Never overwrites** a non-empty scalar value.
- **Unions** list-valued fields (`_LIST_META_FIELDS`: `employer_candidates`,
  `location_candidates`, `followers_sample`, etc.) instead of replacing them.
- Keeps "sticky" flags (`exact_seed_match`) once `True` — never downgraded.
- Returns whether anything actually changed.

`ingest_external_profiles` now keys existing entities by `sha256` in a
`by_hash` map. A genuinely new `sha256` still inserts a new entity row exactly as
before. A MATCHING `sha256` now calls `_merge_metadata()` and, if anything changed,
issues an `UPDATE` on that entity's `metadata_json`/`source_url` instead of silently
`continue`-ing past it. The return dict gained an `"enriched"` count alongside the
existing `"added"` count.

### 8.3 Verification

- `test_reingest_merges_enrichment_into_existing_entity` — asserts `added == 0`
  (not a new account), `enriched >= 1` (it WAS merged), no duplicate entity was
  created, and the new fact is actually present on re-read.
- **Live drive** (the most convincing proof): a real investigation on GitHub user
  `gaearon` (128→ entities), followed by a real re-iterate pivot on that same
  account. Result: entities grew from 42 to 45 and `reiteration_count` went from 0
  to 1 — re-running is no longer a no-op.

---

## 9. Facts surfaced as re-iterate suggestions ("points to improve the search")

`compute_pivot_suggestions(seeds, case_id=None)` gained a second suggestion source
beyond plain `derive_seeds()` guesses. When `case_id` is supplied, a new
`_harvest_case_facts()` looks up each staged seed's matching entity IN THIS CASE and
surfaces what's already been scraped from it as new, individually-checkable
suggestions:

| Strategy tag | What it surfaces | Example |
|---|---|---|
| `bio_name` | the real name already extracted from that account's bio/profile | `"Vismay Real Person"` |
| `bio_employer` | an employer/school candidate already extracted | `"PES University"` |
| `bio_link` | a handle self-disclosed in that account's bio/blog | `vismay_real` (from a `blog` field) |

These sort BEFORE the plain derivation guesses in the returned list — a fact
actually scraped from a real account is a stronger lead than a guessed email
permutation. Verified: `test_suggestions_harvest_bio_link_from_discovered_account`
(stamps a `blog` + real name onto a mock-mode entity, confirms both surface with
the correct strategy tags and provenance).

---

## 10. Reiteration count

`get_results()` (`backend/cases/case_service.py`) now returns `reiteration_count` —
a `COUNT(*)` over `audit_ledger` rows where `case_id` matches and
`action = 'pivot_started'`. Every `run_pivot_seeds` call logs exactly one such row,
so this is a precise count of how many times the investigator has re-iterated on
this case. Shown as a "Re-iterations" tile in the frontend's status strip
(`MiniStat` component, `app/cases/[id]/page.js`), alongside "Accounts found" /
"Strong matches" / "Possible matches" / "Identity groups."

---

## 11. Backend API reference

### `POST /cases/{case_id}/pivot/suggest`

Free — computes candidates, never scrapes anything. Body:

```json
{ "seeds": [ { "type": "username", "value": "vismayhs" } ] }
```

Response:

```json
{
  "suggestions": [
    { "type": "email", "value": "vismayhs@yahoo.com",
      "strategy": "username_to_email_guess", "confidence": 0.3,
      "from_value": "vismayhs" },
    { "type": "username", "value": "vismay_hs",
      "strategy": "bio_link", "confidence": 0.6,
      "from_value": "vismayhs" }
  ],
  "estimated_queries": 6
}
```

### `POST /cases/{case_id}/pivot`

Runs a pivot on an EXPLICIT list of seeds (any mix of re-selected existing-account
values, accepted suggestions, and manually-typed identifiers) as a background task.
Body:

```json
{ "seeds": [
    { "type": "username", "value": "vismayhs", "strategy": "existing_account" },
    { "type": "name", "value": "Vismay Real Person", "strategy": "bio_name" }
] }
```

Returns `{"status": "running"}` immediately; the case's `status` flips
`running → complete` the same way a fresh investigation does, so the EXISTING
results poller (`app/cases/[id]/page.js`) picks it up with no special-casing beyond
the optimistic `onPivotStarted()` status flip that re-arms that poller.

---

## 12. Frontend components

- **`components/ui/AccountCard.jsx`** — gained `reiterateChecked` / `onToggleReiterate`
  props; a checkbox in the card header, independent of the existing click-to-view
  behavior (stops propagation so checking a box doesn't also open the analysis
  panel).
- **`components/ui/ReiterateBar.jsx`** (new, replaced the earlier single-entity
  `PivotPanel.jsx`, which is deleted) — the permanent staging tray (drop target +
  chip list + clear button) and the floating "Re-iterate (N)" button, plus the
  run modal (suggestions, manual-add, cost estimate, Run button).
- **`app/cases/[id]/page.js`** — `stagedSeeds` (a `Map<key, seed>`) is the single
  source of truth, threaded to every `AccountCard` (via a derived `Set<entity_id>`
  for backward-compatible `.has()` checks) and to the Summary tab's `BioFacts`,
  name/alias rows, and `PhotoThumb` components (each `draggable` + clickable,
  dispatching into the same staging map).
- **`BioFacts`** (new, in `page.js`) — a read-only panel shown in the single-account
  and cluster analysis views, listing whatever name/employer-school/city/linked
  accounts were extracted from that account's bio — the visual answer to "show what
  it scraped."

A profile picture staged this way becomes a `{"type": "face", "value": photo_url}`
seed. Running it re-triggers face-embedding matching against that photo via
`build_face_seed_profile()` — this required a new `_scrape_pivot_seed()` wrapper in
`run_pivot_seeds`, because `_seed_tool_map()["face"]` is deliberately `[]` (face
seeds are handled outside the generic scraper fan-out in the normal investigation
flow, and needed the same special-casing here). Gated behind
`config.DATA_MODE == "live"` — caught during testing that `build_face_seed_profile`
has no mock-mode branch of its own and would otherwise fire a real HTTP request
even from a mock-mode/test pivot.

---

## 13. Deliberately deferred — not an oversight

**City/location as a searchable seed type.** There is no backend seed type for a
bare location string today — Serper/Maigret/etc. have no mechanism for "search for
this city" alone. City IS extracted and displayed (§7.3, §9) but is not wired as a
draggable/checkable seed. If built later, the honest options discussed with the
user are:
- **(a)** location as a *qualifier* appended to another seed's search query (e.g.
  `"Vismay HS" Bengaluru` instead of just `"Vismay HS"`) — more powerful, but a
  deeper change to the search-plumbing (`SerperScraper` query templates).
- **(b)** a genuinely stricter "India-only" region filter that excludes global
  platforms too — flagged separately as carrying real regression risk (a prior,
  stricter filter was tried and reverted after it dropped 75% of real results,
  including the investigator's own literal search target).

Both were explicitly deferred by the user's own decision, not built silently.

**GHunt** — see §5.4.

---

## 14. Test & verification summary

- **189 tests passing** (`python -m pytest tests/ -q`), up from 101 before this
  work — 88 new tests across `tests/test_derive.py`, `tests/test_email_norm.py`,
  `tests/test_new_scrapers.py`, `tests/test_pivot.py`, `tests/test_email_bridge.py`,
  and `tests/test_bio_enrichment.py`.
- `npm run build` clean throughout every frontend change.
- Every backend change was ALSO verified against a real, running server at least
  once — not just mock-mode pytest:
  - Live Gravatar/EmailRep API calls confirming their actual current auth
    requirements (both now require a key where older docs said "free").
  - A live `torvalds` investigation → pivot, confirming the combined multi-seed
    run model end to end.
  - A live `gaearon` GitHub investigation → re-iteration, confirming the merge fix
    (entities 42→45) and `reiteration_count` (0→1).
  - A live `POST /pivot/suggest` call with two different input seeds, confirming
    cross-input deduplication and provenance tagging.
