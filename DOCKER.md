# VERTEX — Running with Docker

A local, single-machine Docker stack: **backend** (FastAPI), **frontend** (Next.js),
and **PhoneInfoga** (phone OSINT), wired together with `docker compose`.

## Quick start

```bash
cp .env.example .env      # fill in SERPER_API_KEY, GITHUB_TOKEN, NVIDIA_API_KEY, JWT_SECRET
docker compose up --build
```

- **UI:** http://localhost:3000
- **API / Swagger:** http://localhost:8000/docs
- Default admin (created on first boot): `admin` / `vertex2026` — **change it before any real use.**
- Optional extra search source: `BRAVE_API_KEY` (see `API_KEYS_AND_BOTS.md`).
- `[llm] ... 410` in `docker compose logs backend`: an NVIDIA model id was retired — check
  `curl -H "Authorization: Bearer $NVIDIA_API_KEY" https://integrate.api.nvidia.com/v1/models`
  and override `LLM_EXTRACT_MODEL` / `LLM_EXPLAIN_MODEL` / `CHAT_LLM_MODEL` in `.env`, then
  `docker compose up -d backend`.

To stop: `docker compose down`. Your data (DB, reports) is kept in the `vertex-data`
volume and survives restarts. To wipe it: `docker compose down -v`.

## What's in the stack

| Service | Image / build | Port | Notes |
| --- | --- | --- | --- |
| `backend` | `Dockerfile.backend` | 8000 | FastAPI + all CLI OSINT tools (Blackbird, ignorant, maigret, sherlock, holehe, socialscan) |
| `frontend` | `frontend/Dockerfile` | 3000 | Next.js dashboard |
| `phoneinfoga` | `sundowndev/phoneinfoga` | 5000 (internal) | Reached by the backend at `http://phoneinfoga:5000` |

## Configuration

- **Secrets** come from `.env` (via `env_file` in compose) — never baked into the image.
  `.env` must exist; copy it from `.env.example`.
- **Data** (SQLite DB, generated reports, Telegram session) lives in the `vertex-data`
  volume mounted at `/data`. `DB_PATH`, `REPORT_OUTPUT_DIR`, and `TELEGRAM_USER_SESSION`
  already point there.
- **Face-matching models** (~37 MB) are downloaded during the image build. If that
  download fails, face matching is silently disabled and everything else still works.

## The agentic browser is OFF by default

The Playwright/browser-use agentic browser is **excluded** from the default image (it adds
a full headless Chromium — a much larger, slower build). Everything else runs without it.

To turn it on later, no code changes needed — rebuild the backend with the flag:

```bash
docker compose build --build-arg WITH_AGENTIC_BROWSER=true backend
docker compose up -d backend
```

That installs `requirements-agentic.txt` plus the Chromium runtime. (You can also set the
arg permanently in `docker-compose.yml` under `backend.build.args`.)

## Frontend → backend URL (important)

`NEXT_PUBLIC_API_URL` is inlined into the frontend **at build time**, and the call is made
by the **browser**, so it must be a URL your browser can reach — `http://localhost:8000`
by default. If you deploy behind a domain, rebuild the frontend with your real API URL:

```bash
docker compose build --build-arg NEXT_PUBLIC_API_URL=https://api.your-domain.com frontend
```

## Optional: NewLeaks Telegram bot

The NewLeaks add-on needs an interactive Telegram **user session**, which can't be created
during a build. Create it on the host once, then it's picked up via the `/data` volume:

```bash
# Docker (stack running):
docker compose exec backend python -m scripts.telegram_login   # prompts for phone + code
# Native (venv active):
python -m scripts.telegram_login
# then set NEWLEAKS_ENABLED=true in .env and restart: docker compose up -d backend
```

See `API_KEYS_AND_BOTS.md` for the full bot/key reference.

## Standalone side-tool: dark-web search

`tools/onionsearch-sandbox/` — separate `docker compose` stack, not started by this one.
See its own `README.md`.

## Troubleshooting

- **`no configuration file provided: not found`** — you're in the wrong folder. All the
  commands must be run from **inside this repo's root folder** (where `docker-compose.yml`
  lives). Check with `ls docker-compose.yml` — it should print the filename.
- **`failed to connect to the docker API ... is the daemon running?`** — Docker Desktop
  isn't started. Open **Docker Desktop** (Mac: `open -a Docker`), wait ~30–60s until the
  whale icon is steady, then confirm with `docker info` and retry.
- **`env file .env not found`** — run `cp .env.example .env` first.
- **A scraper returns nothing** — VERTEX is fail-safe: a missing key/tool just disables
  that one source. Check `docker compose logs backend` for the `[config]` key warnings.
- **Rebuild after dependency changes** — `docker compose build --no-cache backend`.
