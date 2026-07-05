# VERTEX — LinkedIn Search: Root Cause, Fix, and Verification

**What this document is:** a complete, accurate record of everything done to make
LinkedIn search actually work — reliably, accurately, and on *every* search and every
re-iteration — covering the full investigation (including the wrong turns), the real
root cause, the final architecture, every integration point, and the live verification
that proves it works. Nothing here is asserted from memory; every code reference was
re-read from the current file at the time of writing, and every behavioral claim was
either a passing test or a live call against the real Serper/GitHub/LinkedIn APIs.

This picks up immediately after the `vismay-saturday-0015-reiteration` branch push —
none of the work in this document has been committed yet (see §10).

---

## 1. The original complaint

Across several searches, LinkedIn results simply weren't showing up. The investigation
went through three distinct, disproven hypotheses before finding the real cause — all
three are recorded here because they're genuinely how the debugging happened, and
because two of them ("intermittent quotes issue," "needs more retries") produced code
that was written, tested, and then **reverted** once the real cause was found. Nothing
from those dead ends survives in the final code — this section exists so the reasoning
is traceable, not because any of it is still true.

### 1.1 Hypothesis 1 — LinkedIn wasn't wired for username searches at all (TRUE, but incomplete)

Confirmed by reading `backend/pipeline/orchestrator.py`'s `_seed_tool_map()`: the
LinkedIn dork (`site:linkedin.com/in "{q}"`) originally existed **only** in the
`"name"` seed's tool list, never in `"username"` or `"email"`. Since Maigret's own
site database has **zero** `linkedin.com` entries (verified by loading
`maigret/resources/data.json` directly and grepping for `linkedin` — empty result),
a username-seeded investigation had no path to LinkedIn whatsoever. This was real and
is fixed (see §3), but it wasn't the whole story — even after wiring it in, results
were inconsistent.

### 1.2 Hypothesis 2 — Serper rejects `site:` + quoted-phrase as a "premium pattern" (DISPROVEN)

Live testing showed `site:linkedin.com/in "vismayhs"` returning `HTTP 400
{"message":"Query pattern not allowed for free accounts"}` on some calls and `HTTP 200`
with real results on others — with the *exact same query string*, seconds apart. A
`site:instagram.com "vismayhs"` call with the identical quoting pattern returned a
normal `200` every time, which at that point looked like LinkedIn specifically being
gated. Acted on this by removing the quotes from the LinkedIn query
(`site:linkedin.com/in {q}`) — this was **later reverted** once §1.4 found the truth,
because quotes were never actually the variable that mattered.

### 1.3 Hypothesis 3 — genuine flakiness needing more retries (DISPROVEN)

Added a 1-retry-on-{400,429} policy to `SerperScraper`, then a stronger 3-attempt
version with growing backoff (0s / 1.5s / 3s). Neither made the failure rate
predictable — the *same* query, run three times in under a minute through the retry
logic, still failed 3/3. This ruled out "just needs to wait out a rate limit."

### 1.4 The real, deterministic root cause (CONFIRMED)

Isolated by testing the one variable nothing else had touched: the `num` parameter
(results per page). Direct, repeatable proof:

```
site:linkedin.com/in vismayhs   num=10  ->  200 OK, real results
site:linkedin.com/in vismayhs   num=20  ->  400 "Query pattern not allowed for free accounts"
site:linkedin.com/in vismayhs   num=15  ->  400
site:linkedin.com/in vismayhs   num=11  ->  400
vismayhs (no site:)             num=20  ->  200 OK
site:instagram.com vismayhs     num=20  ->  400   (same cap, just hadn't been noticed yet)
filetype:pdf vismayhs           num=20  ->  200 OK (filetype: is NOT capped)
```

**Serper's free tier hard-rejects any `site:`-scoped query once `num > 10`.** It is
**not** a rate limit (the `x-ratelimit-remaining` header showed 23 of 25 requests still
available when a 400 fired), not related to quoting, and not related to the specific
domain — it reproduces on every `site:` dork tested. `SerperScraper._run_live`
hardcoded `"num": 20` for every request, which means **every `site:` dork in the
entire codebase** — the whole `"name"` seed tool list (LinkedIn, Instagram, Twitter,
GitHub, Reddit, YouTube, Telegram, Facebook, Medium, Pinterest, Pastebin) — was
silently returning zero results any time this cap was hit, indistinguishable from a
genuine "nothing found." This bug almost certainly predates this session and affected
name-seed search quality broadly, not just LinkedIn.

---

## 2. The fix — `backend/ingestion/serper_scraper.py`

`SerperScraper._run_live` now chooses `num` based on the query template itself:

```python
num = 10 if "site:" in self.query_template.lower() else 20
```

Confirmed live, 3/3 consecutive runs, zero failures after this change — see §8 for the
full verification transcript. A single retry-on-429 remains (a *real* rate limit is
still possible and distinct from the num-cap 400), matching the same conservative
"one short retry, don't hammer a struggling provider" policy `llm_client.py` already
uses elsewhere in this codebase. The elaborate 3-attempt retry from §1.3 was removed —
it's not needed once the actual cause is fixed, and keeping unnecessary retry
complexity around would just make the code harder to reason about.

This fix is NOT LinkedIn-specific — every `site:` dork in `_seed_tool_map()`'s
`"name"` list benefits from it too, automatically, with zero other changes.

---

## 3. The LinkedIn search architecture — `backend/pipeline/orchestrator.py`

Four new functions, all added this session, all shared by both the initial
investigation and every re-iteration (§5) so LinkedIn coverage never depends on which
code path happens to run.

### 3.1 `discover_real_names(profiles) -> set[str]`

Extracted (not duplicated) from logic that used to live inline in the "2-Hop Name
Pivot" step. Scans every profile on a `LEGITIMATE_PLATFORMS` platform for a real,
multi-token human name (from `metadata["name"]`/`["fullname"]`, or isolated from a
page `<title>`), excluding anything digit-bearing or single-token (handles are
single-token; real names aren't). Shared by the name-pivot step and the LinkedIn
search so both agree on "what do we actually know this person is called."

### 3.2 `linkedin_candidates(seed_type, seed_value, discovered_names=None, cap=4) -> list[str]`

Directly answers the brief: *"assume only normal username we start with... use the
existing details."* A raw username's LinkedIn vanity URL is usually name-based
(`/in/vismay-h-s`), not handle-based, so dorking the bare handle alone finds almost
nothing on its own. This function builds a small, deduplicated candidate list:

- **`seed_type == "name"`** → just the name itself.
- **`seed_type == "username"`** → the raw handle (sometimes the vanity URL *does*
  match it directly) **plus** the recovered name via `derive.py`'s
  `names_from_handle()` — the exact same recovery already used for re-iteration
  suggestions (`"vismayhs"` → `"Vismay HS"`).
- **Any `discovered_names`** passed in (from `discover_real_names()`) are added too —
  a name actually discovered elsewhere in the case is a stronger candidate than a
  guess, but never replaces the guess (the guess is all there is until something
  better turns up).

Deduplicated case-insensitively, capped (default 4, callers pass their own cap).

### 3.3 `_alnum(s)` and `_linkedin_relevant(candidate, profile)` — the accuracy filter

A raw `site:linkedin.com/in "Satya Nadella"` search correctly finds his real profile
— but also finds profiles like *"J.D. Meier - Satya Nadella's Former Head Coach"*,
which merely **mentions** him. Left unfiltered, every re-iteration on a common or
notable name would inject irrelevant people into the case.

LinkedIn's search-result titles are consistently formatted
`"{Profile Owner's Name} - {headline} - LinkedIn"`. `_linkedin_relevant` exploits this:

1. `_alnum()` collapses a string to just `[a-z0-9]` — so `"Vismay H.S"`,
   `"vismay-h-s"`, and `"vismayhs"` all compare equal.
2. First check: does the candidate match the **URL handle** itself (either direction
   substring)? If so, relevant immediately (handles the `vismayhs` ↔ `vismay-h-s`
   case).
3. Otherwise, isolate the **owner segment** — the text before the first
   ` - ` / ` | ` / ` • ` / ` – ` separator in the title.
4. Relevant if the candidate's collapsed form is inside the owner segment, or (for
   multi-word names) every token of the candidate appears in the owner segment.
5. Anything else — a headline that merely *mentions* the candidate — is dropped.

Verified against real captured data (see §8.2 for the exact titles this was tested
against): correctly **keeps** the real Satya Nadella profile, the real Vismay HS
profile (both the exact-handle and the name-variant hit), and correctly **drops**
J.D. Meier and Rolf Harms (real people, real LinkedIn profiles, who simply mention
Nadella in their own headline).

### 3.4 `linkedin_search(candidates) -> list[RawProfile]`

The single call site every other piece of this feeds into:

1. Builds one `SerperScraper('site:linkedin.com/in "{q}"')` instance.
2. Fans out one search **per candidate, in parallel** (`asyncio.gather`).
3. Deduplicates by resulting profile URL (the same person guessed two different ways
   — raw handle and recovered name — shouldn't double-count).
4. Runs every result through `_linkedin_relevant()` before accepting it.
5. Stamps `metadata["found_via_linkedin_search"] = <candidate that found it>` on every
   accepted profile, for provenance in the UI/report/audit trail.
6. Returns `[]` immediately (no network call at all) if `candidates` is empty.

---

## 4. What was removed (to avoid double-querying)

Two old single-shot LinkedIn dorks were removed once the shared mechanism replaced
them — keeping LinkedIn logic in exactly one place:

- The ad-hoc `SerperScraper('site:linkedin.com/in "{q}"')` that had briefly been added
  directly to the `"username"` tool list — removed; `linkedin_search()` covers this
  seed type more accurately (raw value **and** recovered name, not just the raw value).
- The original `site:linkedin.com/in "{q}"` entry in the `"name"` seed's tool list —
  removed; the same query would otherwise run twice (once from the tool list, once
  from `linkedin_search()`'s own candidate list for a `"name"` seed).

Every other `"name"`-seed dork (Instagram, Twitter, GitHub, Reddit, YouTube, Telegram,
Facebook, `filetype:pdf/doc`, Medium, Pinterest, Pastebin) is untouched and still
benefits from the `num`-cap fix in §2 automatically.

---

## 5. Integration — wired into BOTH code paths, unconditionally

This is the part that directly answers *"whenever there's a re-iteration... that
should work perfectly too"* — LinkedIn search is not conditional on anything having
already been discovered; it always runs off at least the seed itself.

### 5.1 `run_investigation` — step "3.5" (initial search)

File: `backend/pipeline/orchestrator.py`, inside the existing
`if config.DATA_MODE == "live":` block, right after `discover_real_names()` runs.

```python
original_id_seeds = [
    (s.get("type"), s["value"]) for s in seeds
    if s.get("type") in ("username", "name") and isinstance(s.get("value"), str)
    and s["value"].strip().lower() in original_seed_values
]
```

Builds candidates from every *original* username/name seed the investigator actually
typed (not permutation noise — filtered against `original_seed_values`, which is
captured before the Username Permutation Engine expands the seed list), **plus** any
`discovered_names`. Capped at 6 total candidates. Runs
**unconditionally** — not gated behind `if discovered_names:` — precisely so a plain
username with nothing else discovered yet still gets a LinkedIn search off the
recovered-name guess alone. Logged to the audit ledger as action `"linkedin_search"`.

### 5.2 `run_pivot_seeds` — every re-iteration

File: `backend/pipeline/orchestrator.py`, inside the existing
`if config.DATA_MODE == "live" and all_profiles:` block, **after** the enrichment
passes (`enrich_profiles_from_page`, `enrich_photos`, `enrich_facts`,
`enrich_via_socid`) — so a name freshly recovered by `socid_extractor` or
`fact_enrich` during *this very pivot* is included as a candidate too, not just names
known before the pivot started.

Builds candidates from the pivot's own username/name seeds **plus**
`discover_real_names(all_profiles)` run over everything the pivot found. Logged as
action `"pivot_linkedin_search"`. Results are merged into `all_profiles` and
re-deduplicated before `ingest_external_profiles` runs — meaning a LinkedIn hit found
during a re-iteration is subject to the exact same merge-not-discard logic documented
in `REITERATION_AND_SEARCH_SYSTEM.md` §8: if it's a genuinely new account, it's
inserted; if it happens to match an account already in the case, its metadata is
merged in.

**Same function, same relevance filter, same candidate-building logic, called from
two places.** There is no separate "re-iteration version" of LinkedIn search to drift
out of sync with the main one.

---

## 6. Audit trail

Every LinkedIn search run — whether from the first investigation or a re-iteration —
is recorded in the tamper-evident ledger (`backend/ledger/audit_ledger.py`):

| Action | Fired from | What's recorded |
|---|---|---|
| `linkedin_search` | `run_investigation` | hash of `{candidates}` in, hash of `{found: N}` out |
| `pivot_linkedin_search` | `run_pivot_seeds` | hash of `{candidates}` in, hash of `{found: N}` out |

Note on what's actually retrievable: `log_action()` stores a **SHA-256 hash** of the
input/output dicts, not the raw JSON (confirmed by inspecting the real
`audit_ledger` table schema: `ledger_id, case_id, action, search_id, input_hash,
output_hash, previous_hash, chain_hash, actor, timestamp` — there is no
`input_data`/`output_data` column). This is by design (§ the module's own docstring:
"the tamper-evident spine of the court story") — the ledger proves a step happened
and its result wasn't altered after the fact, it isn't a queryable data store. The
actual candidates/results live in the entities themselves
(`metadata["found_via_linkedin_search"]`).

---

## 7. Tests — `tests/test_linkedin_search.py` (15 tests, all passing)

| Test | Verifies |
|---|---|
| `test_relevance_keeps_exact_handle_match` | handle-match path of the relevance filter |
| `test_relevance_keeps_name_matching_the_owner_segment` | owner-segment match for a name candidate |
| `test_relevance_keeps_handle_variant_for_a_name` | `"Vismay HS"` candidate matches `vismay-h-s` handle |
| `test_relevance_drops_profile_that_merely_mentions_the_name` | J.D. Meier case — real regression guard |
| `test_relevance_drops_unrelated_profile` | Rolf Harms case — real regression guard |
| `test_linkedin_candidates_username_includes_raw_and_recovered_name` | username → raw + `"Vismay HS"` |
| `test_linkedin_candidates_name_seed_is_just_the_name` | name seed → itself only |
| `test_linkedin_candidates_includes_discovered_names_deduped` | discovered names added, no duplicate of the recovered guess |
| `test_linkedin_candidates_capped` | `cap` parameter enforced against 20 candidate names |
| `test_linkedin_candidates_noise_handle_yields_no_recovered_name` | `"a03"` (a noise handle) → only the raw value, no fabricated name |
| `test_discover_real_names_extracts_from_legitimate_platform` | positive case |
| `test_discover_real_names_ignores_non_legitimate_platform` | a random breach-site "name" field doesn't count |
| `test_discover_real_names_excludes_single_token_and_digit_bearing` | handles and `"Name123"` excluded |
| `test_discover_real_names_excludes_handle_echoed_as_name` | a name identical to its own handle excluded |
| `test_linkedin_search_empty_candidates_is_a_safe_noop` | `[]` in → `[]` out, no network call |

**Full project test suite: 204 passed, 0 failed** (`python -m pytest tests/ -q`) — up
from 189 before this LinkedIn work began (189 → 199 after the first 10 tests → 204
after the 5 relevance-filter tests added once the accuracy issue was found).

---

## 8. Live verification (not simulated — real Serper/LinkedIn calls)

### 8.1 The fix itself, in isolation

```
site:linkedin.com/in vismayhs   num=10 (fixed)  ->  200 OK, 3/3 consecutive runs, zero failures
```

### 8.2 Six known real people, both seed types, with the relevance filter active

| Seed | Type | Result |
|---|---|---|
| `vismayhs` | username | 2 relevant hits: `vismayhs`, `vismay-h-s` |
| `satyanadella` | username | 1 relevant hit: `satyanadella` |
| `Satya Nadella` | name | 5 relevant hits (all genuinely named Satya Nadella); J.D. Meier and Rolf Harms correctly **dropped** |
| `sundarpichai` | username | 3 relevant hits (main handle + 2 real variants) |
| `Andrew Ng` | name | 10 relevant hits, all real people named Andrew Ng |
| `jeffweiner` | username | 3 relevant hits |

### 8.3 Full normal investigation (not a unit test — the real `run_investigation` path)

Ran end-to-end for username `vismayhs` against a throwaway database (to avoid
polluting the real one), using the real `DATA_MODE=live` config:

```
investigation result: {'status': 'complete', 'accounts': 26, 'clusters': 14}
LINKEDIN entities in normal query: 2
   - vismayhs     | https://in.linkedin.com/in/vismayhs    | via: vismayhs
   - vismay-h-s   | https://in.linkedin.com/in/vismay-h-s  | via: Vismay HS
```

### 8.4 Full re-iteration (the real `run_pivot_seeds` path)

Ran a normal investigation for `satyanadella`, then re-iterated on that same account:

```
after initial search:   entities=65  linkedin=5
RE-ITERATING on the account...
pivot result: {'status': 'complete', 'seeds': 1, 'added': 11, 'enriched': 52,
               'total_entities': 76, 'clusters': 51}
after re-iteration:      linkedin=5
   - satyanadella              | https://www.linkedin.com/in/satyanadella
   - satya-nadella-1152401b2   | https://in.linkedin.com/in/satya-nadella-1152401b2
   - gurusatyanadella          | https://my.linkedin.com/in/gurusatyanadella
   - satya-nadella-b1566318    | https://ca.linkedin.com/in/satya-nadella-b1566318
   - satya-nadella-19995393    | https://in.linkedin.com/in/satya-nadella-19995393
```

Confirms: LinkedIn search reruns on re-iteration exactly as designed, the pivot grew
the case (65 → 76 entities), and LinkedIn coverage was maintained through the merge.

---

## 9. Full endpoint reference (confirmed currently registered and working)

Read directly from the running FastAPI app (`app.routes`), not from memory:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | liveness |
| `POST` | `/auth/register` | create user → token |
| `POST` | `/auth/login` | authenticate → token |
| `GET` | `/auth/me` | current user |
| `POST` | `/cases` | create case + start investigation (LinkedIn search runs inside this automatically, per §5.1) |
| `GET` | `/cases` | list my cases |
| `GET` | `/cases/{case_id}` | one case (owner-only) |
| `GET` | `/cases/{case_id}/results` | entities + clusters + forensics + `reiteration_count` |
| `GET` | `/cases/{case_id}/report` | BSA-63 PDF |
| `GET` | `/cases/{case_id}/summary_report` | executive summary PDF |
| `POST` | `/cases/{case_id}/pivot/suggest` | free — derive candidate seeds, no scrape |
| `POST` | `/cases/{case_id}/pivot` | run a re-iteration (LinkedIn search runs inside this automatically, per §5.2) |
| `GET` | `/api/agentic-browser/tools` | agentic browser (separate feature, unaffected by this work) |
| `POST` | `/api/agentic-browser/investigate` | ″ |
| `GET` | `/api/agentic-browser/status/{task_id}` | ″ |
| `POST` | `/api/agentic-browser/run` | ″ |
| `GET` | `/api/agentic-browser/case/{case_id}` | ″ |

No endpoint contract changed because of this work — `/cases` and `/cases/{id}/pivot`
behave exactly as documented in `REITERATION_AND_SEARCH_SYSTEM.md` §11; LinkedIn
coverage is an internal improvement to what those endpoints already do, not a new
endpoint.

---

## 10. Bonus fix found during this work: GitHub profile URL silently lost to a dedup collision

Reported separately from the LinkedIn work ("why is it not finding the GitHub
properly now"), but found and fixed in the same session and using the same
evidence-first approach as the rest of this document, so it's recorded here rather
than in a third file.

### 10.1 The investigation (including the red herring)

The user had just rotated `GITHUB_TOKEN` (a new fine-grained PAT) right before
reporting the problem, which made the token swap look like the obvious suspect.
Reproduced the failure live, twice — once with the old token, once with the new
one — with `username=vismayhs`:

```
GitHubScraper._run_live('vismayhs')  ->  200 OK, real profile, html_url =
  https://github.com/VismayHS          (old token AND new token — identical result)
```

`GitHubScraper` itself was working correctly under **both** tokens — the API call,
the profile fetch, the `html_url` field were all fine. So the token was not the
cause. The account was findable; it just wasn't *surviving* into the final result
set. That pointed at merge/dedup logic, not the scraper — confirmed by re-reading
`backend/pipeline/orchestrator.py`'s `_dedup()`.

### 10.2 Root cause: two different tools' hits collide on the same dedup key

`_dedup()` keys `social_account` entities on `(platform, value)` after passing the
scraped platform name through `_PLATFORM_ALIASES` — which includes:

```python
"gist": "github",
"githubgist": "github",
"github gist": "github",
```

For a username seed like `vismayhs`, **two different tools** produce a hit that
canonicalizes to the exact same key, `("github", "vismayhs")`:

1. An enumerator (Maigret/Sherlock) finding `gist.github.com/vismayhs` exists —
   these tools only confirm existence, they don't fetch the real profile page, so
   this hit carries a URL that points at the user's *gists*, not their profile.
2. `GitHubScraper._run_live` calling the real GitHub REST API and getting back the
   actual profile: `https://github.com/VismayHS`, plus real `bio`, `name`,
   `followers`, `location`, etc.

Before this fix, `_dedup()`'s merge rule was "first URL seen wins, metadata just
fills gaps" — and the enumerator tools run **earlier** in `_seed_tool_map()`'s
tool list than `GitHubScraper`. So the gist URL silently won the `source_url` field
purely because of tool-list ordering, an implementation detail with no relationship
to which URL is actually the useful one. The frontend then showed a `github`
account entity linking to a gists page (or, depending on exact timing, no
resolvable profile at all) — which is exactly what "not finding the GitHub
properly" looks like from the outside, despite `GitHubScraper` having found the
correct profile every single time.

### 10.3 The fix

**`backend/ingestion/github_scraper.py`** — `_profile_from_user()`'s metadata gains
a marker identifying this hit as coming from the authoritative source (the real
profile API), not an inferred enumerator guess:

```python
meta = {
    ...
    "_authoritative_url": True,
}
```

**`backend/pipeline/orchestrator.py`** — `_dedup()`'s `social_account` branch now
lets the authoritative hit's URL win regardless of arrival order, while leaving the
existing per-field metadata merge (fill gaps, never clobber a non-empty value)
completely unchanged:

```python
if key in seen_social:
    existing = seen_social[key]
    existing_was_authoritative = bool(existing.metadata.get("_authoritative_url"))
    merged = {**p.metadata}
    for k, v in existing.metadata.items():
        if v:
            merged[k] = v
    existing.metadata = merged
    if p.metadata.get("_authoritative_url") and not existing_was_authoritative:
        existing.source_url = p.source_url
    elif not existing.source_url and p.source_url:
        existing.source_url = p.source_url
```

Same shape whichever order the two hits arrive in: if the authoritative hit is
already present, a later non-authoritative hit can never overwrite its URL; if the
authoritative hit arrives second, it takes over the URL from whatever placeholder
was there first.

### 10.4 Tests — `tests/test_dedup_authoritative_url.py` (4 tests, all passing)

| Test | Verifies |
|---|---|
| `test_authoritative_url_wins_when_it_arrives_second` | real tool-list order (enumerator first, `GitHubScraper` second) — authoritative URL wins |
| `test_authoritative_url_wins_when_it_arrives_first` | reversed order — authoritative URL still wins, never overwritten by the later enumerator hit |
| `test_metadata_still_merges_regardless_of_url_winner` | confirms this fix changed **only** URL selection — the pre-existing metadata fill-gaps merge is untouched |
| `test_two_non_authoritative_hits_keep_first_url_as_before` | regression guard — two ordinary (non-authoritative) hits still use the original first-URL-wins behavior, e.g. Twitter's `twitter.com`/`x.com` alias pair |

The third test initially asserted the metadata merge would *also* start preferring
the authoritative source's fields — that was a wrong assumption written into the
test, not a bug in the fix; corrected once it was clear this change only ever
touches `source_url` selection.

### 10.5 Live re-verification after the fix

Re-ran the exact same investigation that reproduced the bug (`username=vismayhs`,
fresh throwaway database, real `DATA_MODE=live` config):

```text
github entities: 1
  value='vismayhs'  url='https://github.com/VismayHS'  bio='VismayHS has 11 repositories available. Follow their code on GitHub.'
```

One GitHub entity, pointing at the real profile page with real bio/name metadata —
the gist hit merged into it (per §10.3, metadata still fills gaps) rather than
overwriting its URL. `github_scraper.py` itself required no behavior change beyond
the one new metadata flag — confirming the earlier answer to "so no code was
changed for the GitHub part right?": the scraper was never the problem; the bug was
always in how `_dedup()` merged two tools' hits, and this section is that fix.

### 10.6 Full test suite after both fixes

`python -m pytest tests/ -q` → **208 passed, 0 failed** (204 from the LinkedIn work
in §7, plus these 4 new dedup tests).

---

## 11. Status: NOT yet committed

Everything in this document exists only in the working tree of
`c:\Users\LENOVO\Downloads\CIDECODE\evening\VERTEX` on top of the
`vismay-saturday-0015-reiteration` branch (which itself was already pushed to
`github.com/dhanush-sr/VERTEX`). The LinkedIn fix, the relevance filter, the GitHub
dedup fix (§10), and both new test files have **not** been committed or pushed yet.

## 12. Known limits (honest, not hidden)

- The relevance filter (§3.3) is a **heuristic** based on LinkedIn's current title
  format. If LinkedIn changes how it formats search-result titles, the owner-segment
  extraction would need updating — it is not parsing LinkedIn's actual page structure,
  only Google's cached snippet of it via Serper.
- Common names (e.g. "Andrew Ng") correctly return **multiple different real people**
  who share that name — the relevance filter's job is only to exclude people who
  merely *mention* the searched name, not to disambiguate between two different real
  people who share it. That disambiguation is the correlation engine's job (via other
  signals: photo, bio, location, mutual connections, etc.), by design — this filter
  intentionally does not overreach into that territory.
- `num=10` for `site:` queries (vs. the `num=20` other queries get) means slightly
  fewer raw candidates per LinkedIn query than an unrestricted account would return —
  this is the actual ceiling Serper's free tier allows for this query shape, not a
  choice made for any other reason.
