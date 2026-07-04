# VERTEX — Session Work Log (context2.md)

**Purpose:** Handoff doc for continuing this work under a different account. Everything
below was done in one working session on the `ashwin-fri` → `ashwin-sat-11` branches.
Read this alongside the original `context.md` (the long-standing architecture reference).

---

## 0. Where things stand right now (TL;DR)

- **Branch to continue on:** `ashwin-sat-11` (pushed to `origin`, tip = commit `c004c92`).
  It contains everything from `ashwin-fri` plus the anchor-resolution work.
- **Tests:** 101 passed, 2 skipped (`python -m pytest tests/ -q`).
- **Frontend build:** clean (`cd frontend && npm run build`).
- **Servers:** run locally — backend on :8000, frontend on :3000 (see §6 to run).
- **LLM:** Groq is the working provider (fast). NVIDIA works but is ~80s/call on this
  network, so it's a fallback only. Keys are in `.env` (NVIDIA + Groq updated this session).

---

## 1. Commits this session (newest first)

```
c004c92 feat(anchor): query-anchored resolution — mirror dedup, anchor enrichment, name/location
adec51f feat(reranker): rank exact query-seed matches to #1
d3136d8 fix(ux): cap pinned exact-match section, prioritize major platforms
271b706 feat(ranking+ux): surface exact query-match at top; fix evidence quick-link filter
891d730 fix(routing): single-token seeds hit username enumeration; stop instant-empty investigations
55c9d88 fix(accuracy+reliability): correlation, identifier collection, LLM path, and evidence UI
```

Branches: `ashwin-fri` (up to `d3136d8`... actually `891d730` era) and **`ashwin-sat-11`**
(current, has all of the above). Use `ashwin-sat-11`.

---

## 2. The big bugs found & fixed (in order they were discovered)

### 2.1 Scoring bypass — false-positive merges (commit 55c9d88)
`scoring_engine.py` had a "seed-match" escape hatch (added in an earlier Thursday hotfix,
`cd9ac0b`) that force-merged any account whose handle merely *contained a fragment* of the
seed into a fake 100%/HIGH "primary target" cluster — bypassing the 20-signal correlation
and the red-herring rule. Reproduced live: searching `ash29_03` glued two random strangers
(`ash`, `290`) to the target at 100% confidence. **Removed it.** Seed matches now only
affect ranking, never confidence/tier.

### 2.2 Silent result-killing filters (commit 55c9d88)
`orchestrator._is_legitimate_and_target_country` used to drop ~75% of real results (a
hardcoded India-location filter that deleted the target's *own* account, plus an
"empty-metadata" filter that killed 100% of Sherlock hits). Neutralised — now returns
`True` (see its docstring for the full rationale). Live `torvalds`: ~30 → ~140 accounts.

### 2.3 LLM path was dead on every call (commit 55c9d88)
`llm_client.py` tried NVIDIA first with a short timeout on every call. NVIDIA is ~80s/call
on this network (measured — a GET to `/v1/models` returns in 0.1s but chat POST hangs).
Fixes:
- **Groq is now primary** (fast ~0.2s), NVIDIA is a fallback.
- **Process-wide shared circuit breaker** (`LLMClient._nvidia_down` is class-level): the
  pipeline builds ~5 `LLMClient` instances per run; without sharing, each re-paid NVIDIA's
  timeout (~5×45s dead wait). Now the first NVIDIA failure trips it for all.
- **Fast-degrade under 429**: one short retry, then fall to deterministic fallbacks
  (regex entities / template explanations / frequency keywords) instead of long backoff.
- **Reranker is Groq-only** and call volume trimmed (fact_enrich 15→6, entity-extract
  10→6, promotion checks 15→6) so a run doesn't saturate Groq's per-minute limit.

### 2.4 Seed routing — "completes instantly / retrieves nothing" (commit 891d730)
**This was the "it's not retrieving anything" bug.** The new-investigation dropdown
defaulted to **"Name"**, so typing a plain handle (`ash29_03`, `torvalds`) ran the *name*
path (a few `site:` Google-dorks) → finds nothing → completes in ~1s. Fixes:
- Frontend dropdown default → **"username"**.
- Backend auto-correction (`orchestrator.py` step 1): any **single-token** "name" seed
  (no spaces) → routed to **username** enumeration. Multi-token stays "name".
- Verified live: `octocat` went from instant-empty → 255 accounts.

### 2.5 Exact-match buried + quick-link filter broken (commits 271b706, d3136d8, adec51f)
- **Exact match buried:** the account literally matching the query, when it didn't
  correlate, fell into "not linked" and sank. Now `orchestrator` flags
  `metadata.exact_seed_match` (strict equality — `ash29_03` matches, variant `ash2903`
  does NOT), the UI pins these to a **🎯 Exact match to your search** section at the top
  (capped at 12, major platforms first), and `AccountCard` shows a **★ Exact** badge.
  `reranker.py` also sorts exact matches to relevance rank #1.
- **Quick-link filter showed nothing:** pills were counted from ALL ≥2-member clusters
  (any tier) but the filter only searched HIGH/MEDIUM — so a pill for a 2-account link
  capped at LOW matched nothing. Now the signal filter searches **every** multi-member
  cluster and renders them under a "🔗 Linked by [evidence]" view.

### 2.6 White screen (not a code bug)
Was a **hung Next.js dev server**, not code. Killing stale processes + clean rebuild fixed
it. If it recurs: `pkill -f next; rm -rf frontend/.next; npm run build`.

---

## 3. Query-anchored resolution (commit c004c92) — the current architecture direction

**User's insight (correct):** the exact-match account is the *known target* and should be
the reference everything else is linked to — and its photo/name/location should fill the
case identity. The engine was treating all accounts as equal peers, so a rich *variant*
(`ash290`) out-clustered the actual target (`ash29_03`).

**User's chosen approach (via AskUserQuestion):**
1. Anchor persona with a **2nd-signal gate** (merge exact matches only if they share a
   signal beyond the handle — this is already how the red-herring rule works).
2. **Fetch anchor pages** for real name/photo/location.
3. **Dedupe mirrors + tighten** false photo/face evidence.

**Key realization:** enriching the anchor is ~90% of the work — once the anchor has a real
name/photo/face/location, the *existing* pairwise correlation + red-herring rule handles
merging and linking. No risky new clustering path needed.

**What was built:**
- `orchestrator._canonical_platform` + `_PLATFORM_ALIASES`: collapse mirror platforms
  (`steamcommunity`→`steam`, `hub`→`docker hub`, `youtube user/user2`→`youtube`,
  `githubgist`→`github`, `x`→`twitter`) in `_dedup`. **Verified**: 5 accounts → 3, and the
  bogus "steam + steamcommunity same face" cluster is gone.
- `profile_page_fetcher.enrich_anchors()`: deep-fetches exact-match accounts FIRST (before
  photo/face enrichment + correlation). Extracts **name** (OG/JSON-LD, only trusts
  "Name (@handle)" / "handle (Real Name)" shapes — bare titles rejected to avoid garbage),
  **location** (JSON-LD address + safe bio cues; the noisy "from X" cue was removed after
  it mislabeled "See photos from Ashwin" as a location), **photo**, **bio**. Prioritised by
  platform (instagram/github/gitlab/threads first), bounded to 12, fail-safe.
- Generic `enrich_profiles_from_page` now also fills name/location for non-anchors.
- Frontend Names panel reads `fullname || name`, anchor names sorted first.

**Verified live (`ash29_03`, 381 accounts):** mirror dedup clean (no leftovers); names
extracted (`Ash`, plus variant names); locations extracted (`PUNE, India`, `Toronto`).

---

## 4. KNOWN GAPS / NEXT STEPS (start here)

1. **Anchor enrichment under-delivers on obscure handles.** `ash29_03` had 19 exact-match
   anchors, mostly obscure platforms (op.gg, ixbt, bulbagarden…) that have no
   "Name (@handle)" page title, so they yield no name. The platform-priority sort (added in
   `c004c92`) helps by fetching instagram/github/gitlab/threads first — but if the target
   isn't on those major platforms, names stay thin. **Next:** consider GitHub/GitLab *API*
   calls for anchors on those platforms (richer than OG tags — real name, location, bio),
   and maybe an LLM name-extraction pass over the anchor bios when Groq has quota.
2. **`'Closed User'` name noise.** One garbage name ("Closed User") slipped into the Names
   panel from some platform's page title matching the paren pattern. Tighten `_clean_name`
   or add a small denylist ("Closed User", "Deleted User", "Private Account").
3. **Evidence quick-links quality.** Mirror dedup removed the worst noise, but review the
   quick-links again on a fresh run — the user felt the algo was "bad". The pills now come
   from all ≥2-member clusters; verify counts read sensibly ("N groups · M accounts").
4. **Runtime is slow.** A username run is 3–7 min (variant expansion re-runs enumerators on
   each variant). `ash29_03` = ~280–437s. Fine for a demo if you start early, but a
   candidate for optimization (cap variant count, parallelize better).
5. **NVIDIA on venue network.** If it's reachable + fast there, it may serve; if not, Groq
   carries everything. Don't rely on NVIDIA.
6. **The user's big "code review" dump** (auth/SQL-injection/etc.) was mostly inaccurate
   (bcrypt IS used, queries ARE parameterized, secrets ARE gitignored). The one area worth
   a real look is auth/session handling — not yet done.

---

## 5. Files changed this session

**Backend**
- `backend/scoring/scoring_engine.py` — removed seed-match bypass (§2.1).
- `backend/pipeline/orchestrator.py` — neutralized kill-filters (§2.2), seed auto-correct
  routing (§2.4), exact-match flagging early (§2.5), mirror dedup `_canonical_platform`
  (§3), wired `enrich_anchors` before correlation.
- `backend/llm/llm_client.py` — Groq-primary, shared circuit breaker, fast-degrade (§2.3).
- `backend/analysis/reranker.py` — Groq-only; exact matches → rank #1.
- `backend/ingestion/fact_enrich.py` — call-volume cap 15→6.
- `backend/ingestion/profile_page_fetcher.py` — name/location extraction + `enrich_anchors`.
- `backend/cases/case_service.py` — strip `_`-prefixed relevance metadata out of
  `signals_json`; expose `relevance` separately (so it stops leaking into evidence lists).

**Frontend**
- `frontend/app/cases/[id]/page.js` — exact-match pinned section; quick-link filter across
  all tiers; confidence + platform filters; Names panel reads name/fullname; empty-states.
- `frontend/app/cases/page.js` — seed-type dropdown default → "username".
- `frontend/components/ui/AccountCard.jsx` — "★ Exact" badge from `metadata.exact_seed_match`.

**Tests:** `tests/test_scoring.py`, `tests/test_reranker_precision.py` (regressions kept green).

---

## 6. How to run

```bash
# backend (terminal 1)
cd /Users/ashwinharish/Desktop/vertex2 && source venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# frontend (terminal 2)
cd /Users/ashwinharish/Desktop/vertex2/frontend
npm run dev            # or: npm run build && npm start
```
Open http://localhost:3000, log in `admin` / `vertex2026`.
Search a **username** (dropdown now defaults to it). Expect 3–7 min for a live run.

**Git note:** pushes use `git -c credential.helper='!gh auth git-credential' push` because
the osxkeychain credential isn't always available in a non-interactive shell. Exclude from
commits: `.serena/`, `tools/blackbird` (a 29M submodule that breaks clones), and the stray
scraper-output `*.txt` files at repo root.
