# VERTEX — Session Context (context4)

Work done in this session, in the clone at `/Users/dhanush/Desktop/vertex_main`
(cloned from `https://github.com/dhanush-sr/VERTEX`, `main`). **Nothing has been pushed.**

---

## 0. Environment notes (important gotchas)

- **Python**: the running backend uses **system framework Python 3.14**
  (`/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`), NOT the `venv` —
  the `venv/` was created but left empty, so `uvicorn` resolved to the system install
  where all deps actually live. `create_admin`, tests, etc. must be run with that same
  interpreter, or the venv must be populated (`venv/bin/pip install -r requirements.txt`).
- **Node/Next**: frontend was upgraded (by the user) from Next **14.2.15 → 16.2.10**
  (`package.json` now `^16.2.10`). Next 16 runs **Turbopack** by default.
- **`.env`** (gitignored) is populated. `DB_PATH` / `BLACKBIRD_PATH` were pointing at a
  different machine (`/Users/ashwinharish/...`); fixed to local paths.
- **DB**: `cidecode.db` at repo root. Admin user created: **`admin` / `vertex2026`**.

---

## 1. Timeline feature integration (frontend)

Ported the account-lifeline **Timeline** feature from the reference working copy
`/Users/dhanush/CLAUDE CODE SUNDAY/VERTEX` into this repo. The reference was a *divergent,
older* branch, so the port was surgical (not a wholesale copy) — `main` is newer elsewhere.

- **New files** (copied verbatim from reference):
  - `frontend/lib/timeline.js`
  - `frontend/components/ui/TimelineModal.jsx`
  - `frontend/components/ui/TimelineGraph.jsx`
- **Wiring** in `frontend/app/cases/[id]/page.js`: import, `showTimelineModal` state, a
  🕒 Timeline header button, and `<TimelineModal entities clusters />` render.
- Purely client-side (consumes existing `entities` + `clusters`); no backend changes.
- Left the existing `Timeline.js` **tab** (posting-hours chart) untouched — different thing.
- Verified: `npm run build` compiles clean.

## 1b. Next.js workspace-root + Turbopack cache

- `frontend/next.config.mjs`: added `turbopack.root` + `outputFileTracingRoot =
  import.meta.dirname` to stop Next inferring the wrong workspace root from a stray
  `/Users/dhanush/package-lock.json` (an unrelated home-dir project — left untouched).
- Turbopack panic (`turbo-tasks-backend ... Every task must have a task type`) = corrupted
  `.next` persistent cache. Fix applied: `rm -rf frontend/.next` + restart `npm run dev`.
  (Known Next-16 Turbopack instability; recurs → clear cache again.)

## 1c. FK constraint error on case creation

- Symptom: `POST /cases` → `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
- Cause: empty `users` table + a stale JWT (same default `JWT_SECRET` as a prior run) →
  token's `user_id` didn't exist in this DB. NOT a code bug.
- Fix: ran `create_admin` (system Python 3.14) → admin exists; user must log out / clear
  `localStorage` and log back in as `admin` / `vertex2026` so the token carries a real id.

---

## 2. NewLeaks OSINT Telegram bot — new scraper (backend)

Added `@NewleaksOsintBot` as an **optional, additive, fail-safe** data source, modeled on
the existing scrapers. Queried by **messaging the bot over a Telethon USER session** (bots
can't message other bots, so a user session is required — not a bot token).

- **New files**:
  - `backend/ingestion/newleaks_scraper.py` — `NewLeaksScraper(BaseDataSource)`.
  - `scripts/telegram_login.py` — one-time interactive user-session login helper.
- **Edits**:
  - `backend/config.py`: `NEWLEAKS_ENABLED`, `NEWLEAKS_BOT_USERNAME`, `NEWLEAKS_API_KEY`,
    `NEWLEAKS_TIMEOUT_SECONDS`, `TELEGRAM_USER_SESSION`.
  - `backend/pipeline/orchestrator.py`: import + registered `NewLeaksScraper()` in the
    **email / phone / name / username** seed lists.
  - `.env` / `.env.example`: the `NEWLEAKS_*` keys.

- **Safety**: `_run_live()` returns `[]` instantly unless `NEWLEAKS_ENABLED=true` **and**
  `TELEGRAM_API_ID/HASH` set **and** a user `.session` file exists. Never runs in mock mode.
- **Output**: a `breach`-type `RawProfile` (same shape as dehashed), `sensitive_source:
  True`, with parsed `databases` / `emails` / `phones` / `passwords` / `links` / `raw_text`.
- **Reply parsing**: the bot returns a summary header (`💦The number of leaks: N`) then
  data messages with `**<Source DB>**` titles + labelled records
  (`📩Email:` / `🔑Password:` / `🏘️Adres:` / `🗺️ Region:` / `📞Telephone:` /
  `👤Full name:` / `👨The name of the father:`). Parser extracts DB names + records and
  filters the bot's "Some data did not fit… Download the document" notice (was being
  mis-read as a DB name).

### Activation (both done this session)
1. `python -m scripts.telegram_login` → created `user_session.session`. ✅
2. `.env` → `NEWLEAKS_ENABLED=true`. ✅ (Logged in as user id `<REDACTED_USER_ID>`.)

### Known limitation (not yet done)
- **Large result sets come as a downloadable UTF-8 file attachment**; the scraper only
  reads text messages, so it captures the summary + partial records, not the file's bulk.
  Reading the attachment is a pending enhancement (offered, awaiting go-ahead).

---

## 3. LLM classification of leak data → "Leak Data" tab

Sorts NewLeaks raw output into canonical identity fields + a leftover bucket. **Display-only
and NewLeaks-only** — never fed to correlation/scoring (chosen for zero risk).

- **New files**:
  - `backend/ingestion/leak_classify.py` — `enrich_leak_classification(profiles)`.
  - `frontend/components/ui/LeakDataPanel.jsx` — the tab UI.
- **Edits**:
  - `backend/llm/llm_client.py`: `classify_leak_data(text)` → `{fields, leftover}` via
    `_chat_with_failover`, fail-safe (`{}` on error). Canonical keys include `region`.
  - `backend/pipeline/orchestrator.py`: additive fail-safe call in the enrichment stage
    (after `fact_enrichment`).
  - `frontend/app/cases/[id]/page.js`: `hasLeakData` gate + conditional `🔓 Leak Data` tab
    + `<LeakDataPanel entities />` render.
- Writes `metadata.leak_classified` + `metadata.leak_leftover`.

### Key design decision — LLM + deterministic fallback
The bot's output is **fully labelled**, and the shared LLM (Groq/NVIDIA) is frequently
**rate-limited (429)** during a live run, which left classification empty. So
`leak_classify.py` **always** runs a deterministic label-parser (free, reliable) and
**overlays** the LLM result when it succeeds. Result: Region / Address / Location / Full
name always land in their fields; Father's name / documents go to "Other information".
Verified on real data (Bangalore/Karnataka addresses, regions, names).

---

## 4. NewLeaks behavioral refinements

- **Send exactly what's typed**: an earlier `+91` phone-normalization was **reverted** per
  request — `conv.send_message(identifier)` sends the seed verbatim (no format changes).
- **Only exact-typed seeds hit the bot**: the username permutation engine + email/cascade/
  pivot derivation were causing NewLeaks to fire on machine-generated variants (e.g. typed
  `ash29_03` → bot queried `ash2903`). Fixed in `orchestrator.py`: `_scrape_seed` now takes
  `allow_newleaks` and drops `NewLeaksScraper` unless the value is an **original typed
  seed** (checked against `original_seed_values`). Also conserves the bot's free-tier
  tokens. NOTE: this also excludes re-iterate/**pivot** targets — extend if desired.

---

## 5. Event-loop bug fix (critical)

- Symptom: 1st investigation worked, 2nd failed with
  `The asyncio event loop must not change after connection`.
- Cause: a module-level **cached Telethon client** bound to the first investigation's event
  loop; each investigation runs on its own loop.
- Fix (`newleaks_scraper.py`): removed the cache. The session is loaded **once into memory
  as a `StringSession`**; every query builds a **fresh** client from it on the current loop
  and disconnects in a `finally`. This also eliminates the secondary `database is locked`
  error (no repeated `.session` file access).
- Verified: 4 back-to-back investigations across 4 separate event loops all succeed.

---

## Files changed this session (summary)

**New**
- `frontend/lib/timeline.js`, `frontend/components/ui/TimelineModal.jsx`,
  `frontend/components/ui/TimelineGraph.jsx`, `frontend/components/ui/LeakDataPanel.jsx`
- `backend/ingestion/newleaks_scraper.py`, `backend/ingestion/leak_classify.py`,
  `scripts/telegram_login.py`

**Edited**
- `frontend/app/cases/[id]/page.js`, `frontend/next.config.mjs`
- `backend/config.py`, `backend/pipeline/orchestrator.py`, `backend/llm/llm_client.py`
- `.env` (gitignored), `.env.example`

Runtime-only churn (not source): root `*.txt` OSINT dumps + `cidecode.db` (pipeline output);
`frontend/package.json` + `package-lock.json` (the user's Next 14→16 upgrade).

---

## Run / restart

- Backend: `uvicorn backend.main:app --reload --port 8000` (restart once after `.env`
  flag flips; `.py` edits auto-reload). Login: `admin` / `vertex2026`.
- Frontend: `cd frontend && npm run dev` (hot-reloads; `rm -rf .next` if Turbopack panics).

## Open / pending
- Read NewLeaks **file attachments** for large result sets (enhancement).
- Decide whether NewLeaks should also fire on **pivot** targets.
- Optionally populate the `venv` so the backend isn't relying on system Python 3.14.
- Existing cases won't retroactively get `leak_classified`; new/re-run cases will.
