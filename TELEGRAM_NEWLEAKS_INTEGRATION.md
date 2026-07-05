# NewLeaks Telegram Bot Integration — Full Journey, Issues & Final Solution

Everything about wiring **@NewleaksOsintBot** into VERTEX as an OSINT data source:
the goal, every credential, every problem hit, everything tried, and the exact final
implementation that works. Written to be read cold by someone who wasn't here.

> Repo: `/Users/dhanush/Desktop/vertex_main` (clone of `github.com/dhanush-sr/VERTEX`).
> **Nothing pushed.** All changes are local.

---

## 1. Goal

Make `@NewleaksOsintBot` behave like any other VERTEX scraper: when a case seed is an
email / phone / name / username, also query the leak-search bot, pull back leaked records
(emails, passwords, phones, addresses, names), and surface them in the UI — while never
breaking the existing pipeline.

---

## 2. Credentials & keys involved (all of them)

| Thing | Value | Where it lives | Purpose |
|---|---|---|---|
| Bot username | `@NewleaksOsintBot` | `.env` → `NEWLEAKS_BOT_USERNAME=NewleaksOsintBot` | the bot we message |
| Bot "API key" (generated in-bot) | `<REDACTED_BOT_KEY>` | `.env` → `NEWLEAKS_API_KEY` | stored; **not actually used to query** (see §4) |
| Telegram **API ID** | `<REDACTED_API_ID>` | `.env` → `TELEGRAM_API_ID` | Telethon app credential (from my.telegram.org) |
| Telegram **API HASH** | `<REDACTED_API_HASH>` | `.env` → `TELEGRAM_API_HASH` | Telethon app credential |
| Telegram **bot token** (pre-existing) | `<REDACTED_BOT_TOKEN>` | `.env` → `TELEGRAM_BOT_TOKEN` | used by the *old* `telethon_scraper.py`; **NOT usable** for this (see §4) |
| Our own Telegram **user id** | `<REDACTED_USER_ID>` | discovered at login | the account whose session does the querying |
| User **session file** | `user_session.session` | repo root (path from `TELEGRAM_USER_SESSION`) | the authenticated user session (a credential; gitignored via `*.session`) |
| Enable flag | `NEWLEAKS_ENABLED=true` | `.env` | master on/off switch |
| Timeout | `NEWLEAKS_TIMEOUT_SECONDS=25` | `.env` | per-bot-reply wait |

**Key realisation about the "API key":** `<REDACTED_BOT_KEY>` *looks* like a Telegram bot
token (`<id>:<secret>`), but the secret half is too short to be one — and the numeric prefix
`<REDACTED_USER_ID>` turned out to be **our own Telegram user id** (confirmed at login). So that key
is tied to the account, not a usable HTTP/bot credential. The actual querying is done by the
**user session**, not this key. It's stored in `.env` in case the bot ever needs an in-chat
auth step, but it is not on the hot path.

> Security note: these are live secrets sitting in `.env` (gitignored) and pasted in chat.
> Rotate `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, and the NewLeaks key if this leaves the
> machine. The `user_session.session` file is a full login — treat it like a password.

---

## 3. How the bot expects to be queried (its own help text)

```
📧 mail:      example@gmail.com | example@ | @gmail.com
👤 name/nick: Petrov | Petrov Maxim | ShadowPlayer228
📱 phone:     +79002206090 | 79002206090 | 89002206090
🔑 password:  123qwe
🚗 car / VIN, ✈️ telegram, 📘 facebook, 🌟 vk, 📸 instagram, 📍 IP …
```
It's a Russia-centric leak-search bot (RF car plates, VK, etc.). Free tier: shows **300
random** of the matches, warns about "waste of tokens", pushes a paid subscription.

---

## 4. The core design decision: how do we even talk to it?

Two candidate transports were weighed:

- **Option A — HTTP API** (call a REST endpoint with the token). Cleanest, stateless. But
  there was no documented endpoint, and the "API key" is really a user id (§2). Rejected.
- **Option B — message the bot over Telegram and scrape the reply.** Chosen.

**Critical constraint that shaped everything:** the existing `telethon_scraper.py` logs in
with a **bot token** (`TELEGRAM_BOT_TOKEN`). **Telegram forbids bots from messaging other
bots.** So a bot-token client *cannot* talk to `@NewleaksOsintBot`. We therefore need a
**user session** — a real user account, authenticated once via phone + login code — which
sends the query as a normal chat message and reads the reply.

User picked **Telegram messaging** for transport; seed types **email, phone, name, username**.

---

## 5. Chronological log of every issue faced & what was tried

### Issue 5.1 — Bot-to-bot is impossible → need a user session
- **Tried:** reusing the existing bot-token Telethon client.
- **Failed because:** bots can't DM bots.
- **Fix:** new **user session**. Added `scripts/telegram_login.py` (interactive: prompts for
  phone + the code Telegram texts you) which creates `user_session.session`. The pipeline
  itself never prompts — it only uses the session file if it already exists.
- **Result:** user ran it, logged in as **Dhanush**, user id **<REDACTED_USER_ID>**. ✅

### Issue 5.2 — First reply is a summary header, not the data
- Sending `test@example.com` returned **two** messages:
  - **MSG 0 (header):**
    ```
    🔎Request: test@example.com
    💦The number of leaks: 66
    🚧You are shown 300 random of them.
    🆓︎... free version ... /shop ... 🪞 Mirror: @ofjdhfk_bot
    ```
  - **MSG 1+ (data):**
    ```
    **👽Alien TxtBase**
    <description paragraph>
    **📩Email: ** `test@example.com`
    **🔑Password: ** `123456 `
    **🔗Link: ** pocketbase.io
    ...
    ```
- **Tried first:** a generic parser (regex-grab emails/phones from all text).
- **Problem:** it treated the header (which echoes the query email) as a "hit", and missed
  the real structure (source-DB names + labelled record rows).
- **Fix:** rewrote `_parse_reply()` to understand the real shape — extract the leak **count**
  from the header, the **source database** names from bold `**Title**` lines, and the
  **records** from labelled rows.

### Issue 5.3 — Bot's "notice" line was mis-read as a database name
- Large results include a bold line: `**Some data did not fit this message! Download the
  document to see them.**` — the parser was adding this as a "database" (garbage in the
  breach/timeline fields).
- **Fix:** `_looks_like_db_title()` now rejects bold lines that are sentence-like / contain
  notice words (`download`, `document`, `did not fit`, …) or are too long. Unit-tested:
  notice filtered, real names (`Alien TxtBase`, `Bureau van Dijk`) kept.

### Issue 5.4 — Phone searches returned "empty" (looked broken)
- User tried a phone; nothing came back.
- **Diagnosis (captured the raw reply):** the bot literally answers
  `🤷 No results found` for numbers not present in any leak. Phone data is far sparser than
  email. So `[]` was **correct behaviour**, not a bug. `_EMPTY_MARKERS` catches "no results".

### Issue 5.5 — Phone format (+91 vs verbatim)
- First added `+91` normalization (bare `9876543210` → `+919876543210`, foreign `+1…`
  preserved, emails/names untouched). Unit-tested and working.
- **User then decided:** send the bot **exactly what was typed**, no normalization.
- **Fix:** reverted — `await conv.send_message(identifier)` sends the seed verbatim.

### Issue 5.6 — Bot was queried with permutations, not the exact input
- User typed username `ash29_03`; the bot was actually queried with **`ash2903`**.
- **Cause:** VERTEX's username **permutation engine** (`orchestrator.py:463`) + email/cascade/
  pivot derivation generate variant identifiers, and NewLeaks was firing on all of them
  (also wasting free-tier tokens).
- **Fix:** `_scrape_seed()` gained an `allow_newleaks` flag; the main fan-out passes it
  `True` only when the value is an **original typed seed** (checked against
  `original_seed_values`). Every derived/permuted/cascade/pivot path drops the NewLeaks
  scraper. Verified: `ash29_03` → fires; `ash2903` → skipped.
- **Note:** this also excludes re-iterate/**pivot** targets (can be extended if wanted).

### Issue 5.7 — LLM classification came back empty (rate limits)
- The plan: an LLM call sorts the raw leak text into canonical fields (name / location /
  address / region / …) with leftovers in a separate tab.
- **Problem observed on real data:** `leak_classified` was empty. Logs showed
  `groq 429 Too Many Requests` → `nvidia read timed out`. During a live run the shared LLM
  is saturated by the pipeline's other calls, so classification got rate-limited to nothing.
- **Fix:** since the bot's output is **fully labelled**, made the classifier **LLM-primary +
  always-on deterministic fallback** (same discipline as `fact_enrich.py`). A deterministic
  label parser always runs (free, reliable); the LLM result is overlaid when it succeeds.
- **Verified on a real phone response** (`<REDACTED_PHONE>`, source `HiTeckGroop.in`):
  - `full_name` → M Madhavan, H S Rama Chandra Setty
  - `address` → the full Bangalore/Karnataka addresses (with pincodes)
  - `region` → AIRTEL KARNATKA, JIO KARNATKA
  - `phone` → all 4 numbers
  - `Father's name` → leftover ("Other information")
  Worked even while the LLM 429'd.

### Issue 5.8 — "event loop must not change" on the 2nd investigation (the big one)
- **Symptom (user):** first investigation after restarting the port works; the **second**
  fails with:
  `[newleaks] query failed: The asyncio event loop must not change after connection`.
- **Cause:** I had cached one Telethon client at **module level**. Telethon binds a client to
  the event loop it connected on, and VERTEX runs **each investigation on its own event
  loop** — so the client from run 1 rejected run 2's loop.
- **Tried (fix attempt 1):** create a **fresh client per query** on the current loop,
  disconnect after. This fixed the loop error — but exposed a second error:
  `[newleaks] failed: database is locked` (the `.session` is a SQLite file, and reopening it
  on rapid reconnects / alongside another process locks it).
- **Final fix:** load the session **once into memory as a `StringSession`**, then build a
  **fresh client per query from that in-memory string** (never re-touching the SQLite file)
  and disconnect in a `finally`. Eliminates **both** the loop binding and the file lock.
- **Verified:** 4 back-to-back investigations across 4 separate event loops → all succeed.

---

## 6. Final working implementation

### 6.1 Files
**New**
- `backend/ingestion/newleaks_scraper.py` — the scraper (`NewLeaksScraper(BaseDataSource)`).
- `backend/ingestion/leak_classify.py` — LLM+deterministic classification enrichment step.
- `scripts/telegram_login.py` — one-time user-session login helper.
- `frontend/components/ui/LeakDataPanel.jsx` — the "🔓 Leak Data" tab UI.

**Edited**
- `backend/config.py` — the `NEWLEAKS_*` + `TELEGRAM_USER_SESSION` settings.
- `backend/pipeline/orchestrator.py` — registered scraper on 4 seed types; `allow_newleaks`
  gate; additive fail-safe `enrich_leak_classification` call.
- `backend/llm/llm_client.py` — `classify_leak_data()` (canonical keys incl. `region`).
- `frontend/app/cases/[id]/page.js` — import + `hasLeakData` gate + tab + render.
- `.env` (secrets) and `.env.example` (placeholders).

### 6.2 How a query actually flows (final)
1. Case seed (email/phone/name/username) is an **original typed value** → `_scrape_seed`
   includes `NewLeaksScraper` (`allow_newleaks=True`).
2. `_run_live(identifier)` returns `[]` immediately unless: `NEWLEAKS_ENABLED=true` **and**
   `TELEGRAM_API_ID/HASH` present **and** `user_session.session` exists on disk. Never runs
   in mock mode.
3. Under a module-level `asyncio.Lock` (serialize one bot query at a time):
   - `_session_string()` — load the `.session` → **in-memory `StringSession`** (cached once).
   - `_get_client()` — build a **fresh** `TelegramClient(StringSession(...))`, `connect()`,
     verify `is_user_authorized()` (else `[]`).
   - `client.conversation(bot, timeout)` → `send_message(identifier)` **verbatim** → collect
     the reply message(s) with a hard timeout.
   - `finally:` `client.disconnect()` — nothing stays bound to the loop.
4. `_parse_reply()` → a `breach`-type `RawProfile` with metadata:
   `source="newleaks_bot"`, `sensitive_source=True`, `databases`, `emails`, `phones`,
   `passwords`, `links`, `leaks_count`, `raw_text`.
5. Enrichment stage → `enrich_leak_classification()` runs the **deterministic label parser**
   (always) + **LLM overlay** (when not rate-limited) → writes `metadata.leak_classified`
   and `metadata.leak_leftover`.
6. Frontend: `hasLeakData` shows the **🔓 Leak Data** tab (`LeakDataPanel`) — classified
   canonical fields on one side, leftover ("Other information") on the other; falls back to
   raw records if the LLM/deterministic produced nothing.

### 6.3 Reply → field mapping (deterministic, in `leak_classify.py`)
Bot label → canonical field:
`Full name→full_name`, `Adres→address`, `Region→region`, `Telephone/Phone→phone`,
`Email→email`, `Password→password`, `City→city`, `Location→location`, `Country→country`,
`Username/Login/Nick→username`, `Date of birth→date_of_birth`, `IP→ip`.
Routed to **leftover**: `Name of the father→"Father's name"`, `Aadhaar/Passport/Document`,
`Link`. Header/menu lines (`Request`, `Number of leaks`, `Search time`, `Mirror`, `/shop`)
are skipped. The LLM overlay refines these and captures anything unlabelled.

### 6.4 Safety properties (why it can't break the pipeline)
- `BaseDataSource.resolve()` wraps every call fail-safe → any error returns `[]`.
- Default **OFF** — inert unless explicitly enabled + session present. Never in mock mode.
- Serialized behind a lock; hard per-reply timeout so a silent bot can't hang a run.
- Classification is **display-only** — `leak_classified` / `leak_leftover` are read only by
  the UI tab; **never** fed to correlation or scoring, so it cannot shift a match tier or
  trip the red-herring rule.

---

## 7. Current status
- **WORKING.** Fires for email / phone / name / username on exact typed seeds; sends the
  identifier verbatim; classifies Region/Address/Location/Name reliably; survives multiple
  back-to-back investigations. Enabled (`NEWLEAKS_ENABLED=true`), session present.

## 8. Known limitations / open items
- **Large result sets arrive as a downloadable UTF-8 file**; the scraper reads only text
  messages, so it captures the summary + partial records, not the file's full contents.
  Reading the attachment is a pending enhancement.
- NewLeaks does **not** fire on re-iterate/**pivot** targets (only original typed seeds).
- Free-tier: 300-random cap + token budget; heavy use returns `[]` once exhausted.
- **Sensitive data**: plaintext passwords + PII now enter case data (flagged
  `sensitive_source=True`). Intended for the authorised LE/court-report use case.

## 9. Quick setup recap (to reproduce on another machine)
```bash
# 1) .env: TELEGRAM_API_ID / TELEGRAM_API_HASH set; NEWLEAKS_BOT_USERNAME=NewleaksOsintBot
# 2) one-time user login (interactive: phone + code) -> creates user_session.session
python -m scripts.telegram_login
# 3) enable it
#    .env -> NEWLEAKS_ENABLED=true
# 4) restart backend
uvicorn backend.main:app --reload --port 8000
```
