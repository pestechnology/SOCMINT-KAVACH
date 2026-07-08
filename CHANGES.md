# Changes log

A running record of local changes made while preparing VERTEX for open-source release
and Docker. **Nothing has been committed or pushed** — these are working-tree changes only.

## Documentation

- **`README.md`** — added a "Quick start → Option A: Docker (recommended)" section at the
  top of Quick start (the old native steps became "Option B"), pointing to `DOCKER.md` and
  `GET_API_KEYS.md`. Previously the README never mentioned Docker, so a new user couldn't
  discover the Docker path.

- **Added `API_KEYS_AND_BOTS.md`** — a complete reference for every environment variable
  the code reads, where to get each key, and how the two Telegram bots (bot-token username
  lookup + NewLeaks user-session add-on) work. Notes that the LLM is provider-agnostic
  (any OpenAI-compatible endpoint — local model or any cloud service; NVIDIA is just the
  free-tier default, https://build.nvidia.com/).

## `.env.example`

- **Removed** the paid-API block: `DEHASHED_EMAIL`, `DEHASHED_API_KEY`, `LEAKCHECK_API_KEY`.
- `HIBP_API_KEY` was briefly removed, then **restored** (kept, documented as the one paid
  optional key). Reddit OAuth vars (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`) were
  removed from the template — the code still reads them if set directly in `.env`.
- **Rewrote it to be self-documenting** — a "GET IT:" comment above each key with the exact
  site + click path, grouped into Required vs Optional, and a note that
  `DATA_MODE=mock` runs with zero keys.
- **Added `GET_API_KEYS.md`** — a click-by-click walkthrough for obtaining every key.
- **Elevated the key tiers (docs only, no config.py change):**
  - **Required (all free):** Serper, GitHub, NVIDIA, **Numverify** (promoted from optional),
    plus the generated JWT secret. Framed as "get all of them; the project is meant to run
    at full capability."
  - **Telegram bot:** marked **REQUIRED for the phone-lookup feature** (its own setup step:
    my.telegram.org creds + one-time interactive `telegram_login`).
  - **HIBP:** kept clearly **optional & paid** — "the project runs fine without it."
  - Gravatar/EmailRep remain removed.
- **Rewrote `API_KEYS_AND_BOTS.md` to match `.env.example` exactly** — removed every
  variable NOT in the template (Groq/Gemini/CHAT_*/INDIC_*/LLM_*_MODEL LLM sections, the
  `TELEGRAM_BOT_TOKEN` username-lookup path, `TARGET_GROUP_NAME`, `BLACKBIRD_PATH`, and the
  old "Section 7: known gap" list). Kept the Telegram **session-setup steps** (my.telegram.org
  creds → one-time `telegram_login` → `NEWLEAKS_ENABLED=true`) since those are needed for the
  phone-lookup bot. Verified: every key named in both docs now exists in `.env.example`.

## Code

- **`backend/ingestion/phone_scrapers.py`** — `PhoneInfogaScraper` now reads a
  `PHONEINFOGA_URL` env var (falling back to `http://localhost:5000`), so a containerized
  backend can reach the PhoneInfoga service by name. Native runs are unchanged.

## Docker (new files)

- **`Dockerfile.backend`** — Python 3.11 backend image. Installs `requirements.docker.txt`,
  bakes in the CLI OSINT tools (Blackbird in its own isolated venv + PATH wrapper, ignorant,
  maigret/sherlock/holehe/socialscan), downloads the face-matching models (non-fatal), and
  runs via the entrypoint. Agentic browser gated behind `--build-arg WITH_AGENTIC_BROWSER=true`.
- **`frontend/Dockerfile`** — Next.js 14 image; `NEXT_PUBLIC_API_URL` as a build-arg
  (default `http://localhost:8000`).
- **`docker-compose.yml`** — three services (`backend`, `frontend`, `phoneinfoga`), a
  persistent `vertex-data` volume for `/data` (DB, reports, telegram session), and `.env`
  as `env_file`. Validated with `docker compose config`. PhoneInfoga pinned to
  `platform: linux/amd64` (upstream image is amd64-only; runs under emulation on Apple
  Silicon) with `command: serve --no-client` (the `--no-open` flag doesn't exist in the
  current image and crash-looped the container; fixed). Backend + frontend images build
  cleanly (~2 min).

## Cleanup of older docs (README.md, SETUP.md)

- Removed all mention of the trimmed services (**Gravatar, EmailRep, Reddit, DeHashed,
  LeakCheck**) from `README.md` and `SETUP.md` so nothing points to keys not in
  `.env.example`. Updated SETUP's key list to the new required tier (Serper, GitHub,
  NVIDIA, Numverify, JWT + Telegram for phone lookup; HIBP optional/paid). Softened the
  README structure line "NVIDIA/Groq client" → "LLM client (OpenAI-compatible)". Verified:
  no `gravatar/emailrep/dehashed/leakcheck/reddit/groq/gemini` left in any user-facing doc.

## Beginner-friendliness

- **`DOCKER.md` troubleshooting** — added the two errors a first-timer actually hits (both
  seen during this session's testing): `no configuration file provided` (wrong folder → `cd
  KAVACH`) and `failed to connect to the docker API` (Docker Desktop not started).

## Cross-platform

- **Added `.gitattributes`** — forces LF line endings on `*.sh` (and `docker/entrypoint.sh`
  explicitly) so the container entrypoint doesn't break when the repo is cloned on Windows
  (CRLF would corrupt the shebang and crash the backend container).

## Verified end-to-end (mock + live, local)

Live mode also verified with real keys: real GitHub profile data (Linus Torvalds, 310k
followers), 163 entities across 40+ platforms, correlation, and a 12-page BSA-63 PDF.

## Verified end-to-end (mock mode, local)

Ran `DATA_MODE=mock docker compose up -d` and confirmed:
- backend `/health` → `{"status":"ok","data_mode":"mock"}`
- `/auth/login` (admin/vertex2026) → returns a JWT
- frontend → HTTP 200
- all three containers stay `Up`; backend reaches `http://phoneinfoga:5000` (service DNS works)
- **`docker/entrypoint.sh`** — prepares `/data`, initializes the DB + admin user
  (idempotent), then execs uvicorn on `0.0.0.0:8000`.
- **`requirements.docker.txt`** — core deps for the image (requirements.txt minus the
  agentic-browser stack).
- **`requirements-agentic.txt`** — the optional agentic-browser deps, installed only when
  `WITH_AGENTIC_BROWSER=true`.
- **`.dockerignore`** (root) and **`frontend/.dockerignore`** — keep build contexts small
  and secret-free (`.env`, `*.session`, `venv/`, `node_modules/`, etc. excluded).
- **`DOCKER.md`** — how to build/run the stack, enable the agentic browser, set the API
  URL, and create the NewLeaks Telegram session.

## Notes / decisions

- Agentic browser is **excluded by default** (kept easy to re-enable via one build flag).
- All CLI OSINT tools are **baked into the backend image**; PhoneInfoga runs as its **own
  service**.
- `requirements.txt` (full, including agentic deps) is **left untouched** for native local
  dev; the Docker image uses the split `requirements.docker.txt` / `requirements-agentic.txt`.
