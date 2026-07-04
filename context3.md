# VERTEX — Session Work Log (context3.md)

**Purpose:** Handoff doc for continuing in a new chat. Covers one working session on
`ashwin-sat-11`. Read alongside `context.md` (architecture reference) and `context2.md`
(previous session: query-anchored resolution, seed routing, LLM path, exact-match UX).

**Date:** 2026-07-04.

---

## 0. Where things stand right now (TL;DR)

- **Branch:** `ashwin-sat-11` — everything pushed to `origin`, tip = **`432ff86`**.
- **Tests:** **118 passed, 2 skipped** (`python -m pytest tests/ -q`). NOTE: run against
  `tests/` explicitly — a bare `pytest` also tries to collect `tools/blackbird/tests` (a
  submodule) and errors on import. That's not our code.
- **Frontend:** compiles clean; dev server hot-reloads. The graph was fully rewritten.
- **LLM:** Groq primary (fast), NVIDIA fallback (~80s/call here). Keys in `.env`.
- **NEXT UP (agreed with user, not started):** add an **"agentic browsing" option** to the
  *add-investigation* flow — an AI agent drives a real browser to a user-chosen no-API site
  (e.g. inflact), runs the query, and pipes the result into the pipeline. See **§3** — it
  has the full research + recommended approach so the next chat doesn't re-research.

---

## 1. Commits this session (newest first)

```
432ff86 feat(identity): fake-name resistance + leak-account name propagation
8536ae8 fix(enrich): recover real display name from entity-encoded og:title
e8a116d Revert "feat(recall): rarity-weighted anchor-keyword booster ..."
89e9792 feat(graph): horizontal tree/dendrogram network (OSINT-framework style)
26d76cb feat(recall): rarity-weighted anchor-keyword booster        (REVERTED by e8a116d)
```

---

## 2. What was done this session

### 2.1 Graph rewritten → horizontal tree/dendrogram (commit 89e9792)
Replaced the force-directed sigma.js blob with an **OSINT-Framework-style horizontal tree**
in `frontend/components/Graph.js` (structure taken from a screenshot the user shared;
content is VERTEX's own hierarchy). Left→right: **Target(seed) → category → account leaf**.
- Categories: **one "Identity" branch per multi-member cluster** (so linkage is visible),
  a pinned **"Exact match"** branch for the anchor(s), and an **"Unlinked leads"** bucket.
- Curved bezier links, hollow ring nodes, category labels on the left / account labels on
  the right, tier colors preserved (HIGH emerald / MEDIUM amber / LOW-REJECT crimson /
  anchor-selected cyan) so the existing legend still applies.
- Interactions: search box dims non-matches, wheel-zoom + drag-pan (1:1 via SVG
  `getScreenCTM`), click a branch to collapse/expand, click an account → `onSelect`
  (same contract as before; side panel still works), selected node highlights its path.
- `page.js` passes a new `seed` prop (root label) = `kase.seeds[0].value`.
- Self-contained SVG/React — no new deps. `sigma`/`graphology` remain in package.json but
  are now unused by this component.

### 2.2 Reverted the anchor-keyword booster (commit e8a116d)
User asked to undo the rarity-weighted anchor-keyword recall booster (`26d76cb`, already
pushed) while keeping the graph. Done via a proper **revert** (not history rewrite, since it
was pushed): deleted `backend/analysis/anchor_keywords.py` + `tests/test_anchor_keywords.py`
and restored `reranker.py` to its pre-booster state. Verified reranker has zero references
to it. **The booster is gone; its idea is NOT in the codebase anymore.**

### 2.3 Name extraction fix — "Ashwin Harish" was never captured (commit 8536ae8)
**Root cause of the user's "it doesn't get the real name" complaint.** For a `username`
search, the anchor's profile page (Instagram/Threads) DOES carry the display name in
`og:title` — but **HTML-entity-encoded**: `Ashwin Harish (&#064;ash29_03) &#x2022; Instagram
photos and videos` (`&#064;`=`@`, `&#x2022;`=`•`). The name-shape regexes matched a literal
`@`/`•`, so the encoded title never matched → name dropped. Fix in
`backend/ingestion/profile_page_fetcher.py`: **HTML-unescape the title (and bio) before
parsing** (param is named `html`, shadows stdlib → imported as `_htmllib`). Also fixed a
2nd latent bug: `_clean_name` was rejecting multi-token names whose letters collapse to the
handle (`vismay_hs` ⇐ "Vismay H S") — now only single-token echoes are rejected. Verified
live: `ash29_03` → **"Ashwin Harish"** on Instagram + Threads. +6 offline regression tests
(`tests/test_profile_name_extract.py`).

### 2.4 Fake-name resistance + leak-account pivot (commit 432ff86)
User's problem: **suspects use fake/gibberish names.** New module
`backend/analysis/name_intel.py` (stdlib-only, deterministic, fail-open):
- **`is_plausible_name`** — gibberish/placeholder detector (vowel ratio, consonant-run
  length, digit reject, placeholder denylist; **non-Latin scripts accepted**; single-letter
  initials neutral). **DISPLAY-NAME field ONLY — usernames exempt** (a gibberish *handle* is
  a strong unique selector; penalizing it would hurt the exact case we care about). Wired
  into `identity_agent._looks_like_real_name` (Names panel) and
  `profile_page_fetcher._clean_name` (page extraction) → fake names never shown as a real
  name.
- **`is_generic_name`** — placeholder ("John Doe") or lone common first name ("Ashwin").
  Wired into `correlation_engine`: demotes `exact_name_match` **35→8** / `fuzzy_name_match`
  **20→6** for generic names so two unrelated "Ashwin"/"John Doe" accounts can't link on the
  name alone. Distinctive names ("Ashwin Harish") keep full 35 (verified).
- **`resolve_cluster_identity`** (leak pivot / feature #2) — lifts the best plausible,
  non-generic real name found on ANY cluster member up to label the whole persona (suspect
  hides their name on the main account but leaks it on an old/careless one tied in by hard
  signals). `case_service.get_results` attaches it as `cluster.identity =
  {name, source_platform, support, from_anchor}`. Shown as the **graph branch label** and on
  the **cluster header** (`👤 name`, tooltip = source platform).
- +10 tests (`tests/test_name_intel.py`).

**IMPORTANT:** 2.3 + 2.4 are **collection-time** improvements — old cached cases in
`cidecode.db` still have empty/old names. Must **run a fresh investigation** (and restart
the backend to load new modules) to see them.

---

## 3. NEXT UP — Agentic browsing option in "add investigation" (agreed, NOT started)

> **Full corrected architecture: see `agentic_browser_design.md`** (fixes anti-bot realism,
> pipeline integration, model keys = Gemini Flash for navigation + Groq for extraction /
> never NVIDIA, drops WhatsMyName, adds determinism caching + timeouts + failure UX). The
> summary below is the short version.

**Goal (user's words):** in the add-investigation form, add **one more option** = agentic
browsing. User gives a query + a target site (e.g. `ash29_03` on inflact); an AI agent opens
a real browser, navigates to the site, runs the query, scrapes the result, streams it back
to the UI. Purpose: use the many OSINT tools that have **no API**.

**This is the same architectural slot as a new discovery source** — the agent's scraped
output should normalize into a `RawProfile` and feed the EXISTING correlate → score →
adjudicate pipeline. The reasoning layer (linking / fake-name / attribution / report) stays;
this only widens *collection*.

### Research done this session (so the next chat can skip it)

**Agent/driver options:**
- **browser-use** (Python, ~50k★, agent-first NL-goal loop, 89% WebVoyager) — **best fit:
  Python matches the backend, uses existing LLM keys.** Fastest path to a working demo.
- **Playwright MCP** (Microsoft; accessibility-tree, no vision model; runs in the
  Claude tool-loop) — good "stay Claude-native", cheaper/faster than vision.
- **Stagehand** (TS; deterministic Playwright + `act/extract/observe`; v3 caches → ~0 cost
  on repeat runs). **Skyvern** (vision, best for weird/legacy sites + forms).

**Browser runtime:** **Steel.dev** (open-source, self-host via Docker, built-in stealth) —
best OSS fit. Browserbase = managed alternative.

**The hard part = anti-bot, not the agent.** inflact/picuki-type sites are heavily
Cloudflare-protected (Turnstile, TLS fingerprinting, per-customer ML, "AI Labyrinth").
LLM/computer-use agents are *fragile* against it (every CAPTCHA burns model time). Real
bypass needs **stealth browser** (Nodriver / Camoufox) + **residential/mobile proxies**
(+ sometimes a CAPTCHA solver). That's an arms race + cost, NOT weekend polish. Plus:
agent-per-step is **slow** (10s–2min/query) and non-deterministic (hard to hit the 95% bar).

### Recommended approach (agreed direction)
1. **Don't LLM-drive every step for known sites.** For a specific site (inflact), a
   deterministic Playwright script (or Stagehand w/ caching) is ~10× faster/cheaper/steadier.
   Reserve the full LLM agent for the "user picks an *arbitrary* site" case. Best hybrid:
   LLM learns the flow **once** → cache/replay deterministically.
2. **Ship it as a scoped, ISOLATED option** (as the user said — a separate add-investigation
   choice) so it can't break the core flow. Make it an **async job** streaming status into
   the existing live-feed UI (it's slow). **Curate 1–3 target sites** for the demo; don't
   promise "any site" (will flake live). Headed browser-use hitting a couple of
   not-brutally-protected sites demos the wow-factor without staking the submission on
   defeating Cloudflare live.
3. **Output → `RawProfile` → existing pipeline** (correlation already dedups across sources).

**My lean:** build the scoped **browser-use** demo (or Playwright MCP), isolated, don't chase
production anti-bot yet. It's a great *demo differentiator* but ADDITIVE scope — it does
nothing for the accuracy layer (that's where the real points are).

### UI wiring sketch (where it goes)
- `frontend/app/cases/page.js` — the add-investigation form. Add a mode/option (alongside
  the existing seed-type dropdown) like **"Agentic site query"** that reveals two fields:
  **query** + **target site/URL**.
- Backend: a new endpoint/job kind that launches the agent async, logs steps via the same
  `log_action` mechanism the pipeline uses (so the live feed shows progress), and on
  completion normalizes results into `RawProfile`s persisted as entities on the case.

---

## 4. Known gaps / next steps

1. **Agentic browsing** (§3) — the main agreed next feature.
2. **Fresh run needed** to see the name work (§2.3/2.4) — old DB cases won't retroactively
   gain names/identity.
3. `sigma`/`graphology` deps are now unused (graph rewritten) — could be removed from
   `frontend/package.json` for cleanliness (low priority).
4. Carryover from context2 still open: anchor enrichment thin on obscure-only handles
   (consider GitHub/GitLab API for anchors); runtime is 3–7 min/username run; auth/session
   review never done.

---

## 5. Files changed this session

**Backend**
- `backend/analysis/name_intel.py` — **NEW**: plausibility / genericness / cluster identity.
- `backend/ingestion/profile_page_fetcher.py` — HTML-unescape title+bio; relaxed handle-echo
  reject; gibberish display-name reject.
- `backend/analysis/identity_agent.py` — gibberish reject in `_looks_like_real_name`.
- `backend/correlation/correlation_engine.py` — demote name signal for generic names.
- `backend/cases/case_service.py` — attach `cluster.identity` (leak pivot).

**Frontend**
- `frontend/components/Graph.js` — **rewritten** as horizontal tree/dendrogram.
- `frontend/app/cases/[id]/page.js` — pass `seed` to graph; show `cluster.identity.name`
  (👤) on the cluster header.

**Tests (new):** `tests/test_profile_name_extract.py`, `tests/test_name_intel.py`.
**Removed (revert):** `backend/analysis/anchor_keywords.py`, `tests/test_anchor_keywords.py`.

---

## 6. How to run

```bash
# backend (terminal 1)
cd /Users/ashwinharish/Desktop/vertex2 && source venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# frontend (terminal 2)
cd /Users/ashwinharish/Desktop/vertex2/frontend
npm run dev
```
Open http://localhost:3000. Search a **username** (dropdown defaults to it). Live run ~3–7 min.
Restart the backend before testing the name work (§2.3/2.4 load new modules).

**Git note:** pushes use `git -c credential.helper='!gh auth git-credential' push origin
ashwin-sat-11` (osxkeychain not available non-interactively). Stage files EXPLICITLY —
exclude `.serena/`, `tools/`, and the stray scraper-output `*.txt` files at repo root
(`git add <specific files>`, never `git add -A`).
