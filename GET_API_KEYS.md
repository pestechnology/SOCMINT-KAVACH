# How to get your API keys — step by step

VERTEX needs a few keys to run in **live** mode. This guide walks you through getting each
one. **All the required keys are free** — get every one of them; the project is meant to
run at full capability with all of them set, so don't skip them.

> **In a hurry, or just evaluating?** You can skip every key: set `DATA_MODE=mock` in your
> `.env` and the full demo runs offline (a HIGH-confidence cluster, a rejected red herring,
> and a PDF) with no keys at all. Come back here when you want real, live scraping.

## Before you start

```bash
cp .env.example .env        # make your private copy (never committed)
```
Open `.env` in any text editor. For each key below, paste the value **after the `=`**, with
no spaces and no quotes. Example:
```
SERPER_API_KEY=abc123realkeyhere
```

---

## ✅ Required key 1 of 4 — SERPER (Google search)

What it's for: the widest OSINT source — Google results, dorks, social/paste lookups.

1. Go to **https://serper.dev**
2. Click **Sign up** (you can log in with Google).
3. After signing in you land on the dashboard — it shows your **API Key** near the top.
4. Copy it and paste into `.env`:  `SERPER_API_KEY=...`

Free tier: 2,500 searches. No credit card needed.

---

## ✅ Required key 2 of 4 — GITHUB token

What it's for: reading public GitHub profiles and followers without getting rate-limited.

1. Go to **github.com** and log in.
2. Click your **avatar** (top-right) → **Settings**.
3. Scroll the left menu to the bottom → **Developer settings**.
4. **Personal access tokens** → **Tokens (fine grain)**.
5. **Generate new token** → **Generate new token (fine grain)**.
6. Give it a name (e.g. "vertex"), set an expiry, and **leave all scopes unchecked**
   (VERTEX only reads public data — no permissions needed).
7. Click **Generate token**, then **copy** it immediately (it starts with `github_pat_`
   and is shown only once).
8. Paste into `.env`:  `GITHUB_TOKEN=github_pat_...`

---

## ✅ Required key 3 of 4 — NVIDIA (the LLM)

What it's for: the AI that extracts facts and writes plain-English explanations.

1. Go to **https://build.nvidia.com/**
2. Sign in (create a free NVIDIA account if needed).
3. Open any model (e.g. a Llama model), then click **Get API Key** / **Generate Key**.
4. Copy the key (it starts with `nvapi-`) and paste into `.env`:  `NVIDIA_API_KEY=nvapi-...`

> **Prefer a different LLM?** VERTEX talks to any OpenAI-compatible endpoint, so you're not
> tied to NVIDIA. To use a **local** model (e.g. Ollama), set
> `NVIDIA_BASE_URL=http://localhost:11434/v1` and `NVIDIA_API_KEY=ollama` (any placeholder).
> To use another **cloud** provider, point `NVIDIA_BASE_URL` + `NVIDIA_API_KEY` at its
> endpoint. NVIDIA is only the default because it has a free tier.

---

## ✅ Required key 4 of 4 — NUMVERIFY (phone lookup)

What it's for: validating phone numbers and getting carrier / country / line type — part of
the phone-lookup pipeline.

1. Go to **https://numverify.com**
2. Click **Sign Up Free** and create an account.
3. On your dashboard, copy the **API Access Key**.
4. Paste into `.env`:  `NUMVERIFY_KEY=...`

Free tier. No card needed.

---

## 🔐 Required — JWT secret (generate, don't fetch)

This isn't fetched from a website — you generate a random string that signs login tokens.

Run this in your terminal:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the long output and paste into `.env`:  `JWT_SECRET=...`
**You must change this from the default** — it's the one security-critical value.

---

## Telegram — REQUIRED for the phone-lookup part (its own setup step)

The **Telegram bot is required for the phone-lookup feature to work fully.** It's not a
paste-a-key step like the others — it needs a phone-verified Telegram account plus a
one-time interactive login — so it gets its own steps here.

**Step 1 — get your Telegram API credentials:**
1. Go to **https://my.telegram.org** and log in with your phone number.
2. Click **API development tools**, fill the short form (any app name/URL).
3. It shows **App api_id** and **App api_hash** — copy both into `.env`
   (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`).

**Step 2 — one-time interactive login (creates the session the bot uses):**
- Run the login once and follow the prompts (phone number + the code Telegram texts you):
  ```bash
  # Docker:
  docker compose exec backend python -m scripts.telegram_login
  # Native (venv active):
  python -m scripts.telegram_login
  ```
- Then set `NEWLEAKS_ENABLED=true` in `.env` and restart the backend (`docker compose up -d
  backend`, or just re-run `uvicorn` natively).

Full details (and the safety notes — the session logs into YOUR Telegram account, never
share it) are in `API_KEYS_AND_BOTS.md` and `DOCKER.md`.

---

## Optional extras (the project runs fully without these)

| Key | Free? | Where to get it |
| --- | --- | --- |
| `HIBP_API_KEY` | **Paid (~$4/mo)** | https://haveibeenpwned.com/API/Key → purchase → copy key. **Not needed to run the project** — it only adds extra breach coverage. |
| `BRAVE_API_KEY` | Free tier ($5/mo credit, ≈1,000 queries; card required) | https://api-dashboard.search.brave.com → sign up → copy the API key. **Not needed to run the project** — a second, independent search index run in parallel with Serper; widens coverage since it's not the same underlying index as Google/Bing. |

---

## Finish up

1. Save `.env`.
2. Make sure `DATA_MODE=live` (now that you have keys).
3. Start it:
   ```bash
   docker compose up -d          # or --build the first time
   ```
4. Check it came up: **http://localhost:8000/health** should show `"status":"ok"`.
5. Open the app: **http://localhost:3000**

If a scraper returns nothing, that's by design — a missing/invalid key just disables that
one source. Run `docker compose logs backend` and look for the `[config]` line listing any
keys it thinks are missing.
