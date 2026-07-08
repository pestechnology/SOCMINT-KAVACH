# VERTEX — API Keys & Bots

A reference for the keys and the Telegram bot used by VERTEX. Every variable here matches
one in **`.env.example`** — that file is the single source of truth; this doc explains
what each one is for and how to set it up. For a click-by-click "where do I get this key"
walkthrough, see **`GET_API_KEYS.md`**.

> **Golden rule:** all secrets live in `.env`, which is gitignored and must never be
> committed. `.env.example` is the template — copy it, fill in your own keys, and if any
> key was ever pasted into chat/screenshots/commits, **rotate it** before use.
>
> ```bash
> cp .env.example .env
> # then edit .env with your real values
> ```
>
> VERTEX is **fail-safe by design**: a missing key never crashes the app. It only disables
> the specific tool that needs it — `validate_keys()` in `backend/config.py` prints a
> warning and the pipeline keeps running.
>
> **No keys yet?** Set `DATA_MODE=mock` in `.env` and the whole demo runs offline with none.

---

## 1. Required keys (all free)

Get all of these — the project is meant to run at full capability with them set.

| Variable | What it's for | Where to get it |
| --- | --- | --- |
| `SERPER_API_KEY` | Google-search dorking (the widest OSINT net — filetype/pastebin/social dorks) | https://serper.dev (free tier) |
| `GITHUB_TOKEN` | GitHub profile + followers scraping (raises the rate limit) | GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained** → default (public) permissions → token starts with `github_pat_` |
| `NVIDIA_API_KEY` | The LLM for fact/entity extraction and explanations | https://build.nvidia.com/ → get API key (starts with `nvapi-`) |
| `NUMVERIFY_KEY` | Phone-number validation / carrier / country (phone-lookup pipeline) | https://numverify.com → Sign Up Free → API Access Key |
| `JWT_SECRET` | Signs auth tokens. **Must be changed from the default.** | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |

Related settings (already in `.env.example` with sensible defaults — change only if you know why):

| Variable | Default | Notes |
| --- | --- | --- |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | OpenAI-compatible endpoint. VERTEX works with **any** OpenAI-compatible LLM — point this (and `NVIDIA_API_KEY`) at a local model (Ollama/vLLM) or another cloud provider. NVIDIA is just the free default. |
| `TOKEN_EXPIRY_HOURS` | `8` | Auth token lifetime |

---

## 2. Optional — HIBP (paid)

| Variable | What it's for | Where to get it | Notes |
| --- | --- | --- | --- |
| `HIBP_API_KEY` | Have I Been Pwned breach lookup | https://haveibeenpwned.com/API/Key (paid, ~$4/mo) | **Not needed to run the project** — only adds extra breach coverage. Returns nothing if unset; the pipeline runs identically. |

---

## 3. Telegram — required for the phone-lookup feature

The Telegram bot powers the phone-lookup part. It's not just a pasted key — it needs a
phone-verified Telegram account **plus a one-time interactive login** — so it has its own
setup steps.

**Step 1 — get your Telegram API credentials** (free, at https://my.telegram.org →
*API development tools* → fill the short form):

| Variable | What it's for |
| --- | --- |
| `TELEGRAM_API_ID` | Your Telegram application ID |
| `TELEGRAM_API_HASH` | Your Telegram application hash |

**Step 2 — one-time interactive login** (creates the user session the bot uses). Telegram
forbids bots from messaging other bots, so this drives a **real user account**:

```bash
# Docker:
docker compose exec backend python -m scripts.telegram_login
# Native:
python -m scripts.telegram_login
# It asks for your phone + the code Telegram sends (and your 2FA password if set),
# then writes a user_session.session file (gitignored as *.session).
```

**Step 3 — enable it:** set `NEWLEAKS_ENABLED=true` in `.env` and restart the backend.

| Variable | Default | What it does |
| --- | --- | --- |
| `NEWLEAKS_ENABLED` | `false` | Master switch. The bot is fully inert until this is `true`. |
| `NEWLEAKS_BOT_USERNAME` | `NewleaksOsintBot` | The bot that's queried |
| `NEWLEAKS_API_KEY` | — | Stored for a possible in-chat auth step. The lookup goes through the user session, **not** this key. |
| `NEWLEAKS_TIMEOUT_SECONDS` | `25` | Hard per-query timeout so a slow/silent bot can't hang the pipeline |

**Safety guarantees (from the scraper's own guard):** it returns nothing unless **all** of
— `NEWLEAKS_ENABLED=true`, API ID/hash present, **and** a user `.session` file exists on
disk. It never triggers an interactive login from inside a request, is never used in mock
mode, serializes queries behind a lock, and flags every result as sensitive (replies can
contain passwords/PII).

> The `.session` file **is a credential** — it grants access to YOUR Telegram account. It
> is gitignored (`*.session`) and must never be committed or shared.

---

## 4. Non-secret config & paths (leave as-is unless you know why)

| Variable | Default | Notes |
| --- | --- | --- |
| `DATA_MODE` | `live` | `live` = real scrapes; `mock` = fixed offline test data (no keys needed) |
| `DEMO_FALLBACK_ENABLED` | `True` | |
| `DB_PATH` | `cidecode.db` | SQLite database |
| `REPORT_OUTPUT_DIR` | `reports/` | Generated reports |
| `SYNTHETIC_DATA_PATH` | `data/synthetic_dataset.json` | Mock-mode dataset |

---

## 5. Minimum setup to get running

```bash
cp .env.example .env
```

Then fill in the **required keys** (all free): `SERPER_API_KEY`, `GITHUB_TOKEN`,
`NVIDIA_API_KEY`, `NUMVERIFY_KEY`, and a generated `JWT_SECRET`. Add the Telegram setup
(section 3) for phone lookups. `HIBP_API_KEY` is optional.

For a fully offline run, set `DATA_MODE=mock` and no keys are needed at all.
