# TRANSFER & SETUP CHECKLIST

> Read this first if you received VERTEX as a **zip**. A zip includes machine-specific
> and secret files that git normally ignores — they will **not work on your machine**
> (the virtualenv has absolute paths) and **must never be pushed to GitHub**. This file
> tells you exactly what to delete, what to regenerate, and what to change.

---

## 0. Delete these immediately after unzipping
These are machine-specific, regenerable, or secret. They bloat the zip and break on a new
machine. Delete them before doing anything else (you'll recreate them in the steps below).

| Path | Why delete |
|------|-----------|
| `venv/` (and any `.venv/`) | virtualenv has **absolute paths to the original machine** — it cannot work elsewhere |
| `frontend/node_modules/` | platform-specific binaries; reinstall with `npm install` |
| `frontend/.next/` | Next.js build cache |
| `cidecode.db`, `*.db`, `*.db-wal`, `*.db-shm` | the SQLite database — regenerate it |
| `reports/` | generated PDFs + scraper artifacts |
| `anon.session`, `*.session` | **Telegram login session = a credential**, do not keep/share |
| `__pycache__/`, `*.pyc`, `.pytest_cache/` | Python caches |
| `.claude/`, `scratchpad/` | local tooling scratch |

**Windows (PowerShell), from the project root:**
```powershell
Remove-Item -Recurse -Force venv, frontend\node_modules, frontend\.next, reports, __pycache__ -ErrorAction SilentlyContinue
Remove-Item -Force *.db, *.db-wal, *.db-shm, *.session, *.session-journal -ErrorAction SilentlyContinue
```
**macOS / Linux:**
```bash
rm -rf venv .venv frontend/node_modules frontend/.next reports __pycache__
rm -f *.db *.db-wal *.db-shm *.session *.session-journal
```

> Good news: `.gitignore` already excludes all of the above, so even if you forget to
> delete them, `git add .` will skip them. **Never use `git add -f` on these.**

---

## 1. Backend — recreate the virtualenv (Python 3.10+)

Python 3.10 or later works (tested on 3.10 and 3.13). Do NOT reuse the zipped venv.

```bash
# Windows:
py -3.10 -m venv venv          # or: python -m venv venv  (if 3.10+ is the default)
venv\Scripts\activate
# macOS / Linux:
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt        # includes maigret, sherlock-project, holehe, socialscan, truststore, vaderSentiment
pip install pytest pytest-asyncio      # test deps (NOT in requirements.txt)

# ignorant (phone registration checker — pip-packaged):
pip install ignorant

# Blackbird (username/email enumerator — must be cloned, NOT pip-packaged):
git clone https://github.com/p1ngul1n0/blackbird C:\path\to\blackbird
pip install -r C:\path\to\blackbird\requirements.txt
# Add to .env:  BLACKBIRD_PATH=C:\path\to\blackbird
# resolve_tool() finds venv/Scripts/blackbird.bat automatically; the scraper creates it.
```

`requirements.txt` already pulls the core OSINT tools (maigret, sherlock, holehe, socialscan,
waybackpy, telethon). `ignorant` and Blackbird require separate steps above (both are
fail-safe — the app returns `[]` from those scrapers if they're absent).
PhoneInfoga: `docker pull sundowndev/phoneinfoga` then run its REST server on :5000.

---

## 2. Secrets — create your own `.env` (CHANGE THESE)
The zipped `.env` contains the original team's API keys **and a JWT secret** — treat them
as compromised once shared. Create a fresh one:

```bash
cp .env.example .env          # Windows: copy .env.example .env
```
Then edit `.env`:
- **`JWT_SECRET`** — generate a new random value (anyone with the old one can forge logins):
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- **API keys** — put in your own: `SERPER_API_KEY`, `GITHUB_TOKEN`, `NVIDIA_API_KEY`
  (and optional `HIBP_API_KEY`, `NUMVERIFY_KEY`, `TELEGRAM_*`). Breach lookups also work
  **without** a key via the built-in XposedOrNot source.
- **`DATA_MODE`** — `live` for real scraping, `mock` for offline demo/tests.
- **(Optional) Reddit** — set `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` (free "script" app
  at reddit.com/prefs/apps) so Reddit activity analysis works on any network; otherwise
  Reddit may return 403 from datacenter/VPN IPs.

> If the original keys were ever shared more widely than your team, **rotate them** in each
> provider's console.

---

## 3. Frontend — reinstall + env
```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local   # there is no .env.local.example
```

---

## 4. Initialize the database + admin
```bash
python -m backend.database         # creates/upgrades cidecode.db (6 tables + chain_hash)
python -m scripts.create_admin     # creates admin / vertex2026  -> CHANGE this password
```

---

## 5. Run
```bash
# backend (from project root, venv active)
uvicorn backend.main:app --reload --port 8000      # http://localhost:8000/docs
# frontend (separate terminal)
cd frontend && npm run dev                          # http://localhost:3000 (3001 if 3000 busy)
# tests
python -m pytest tests/ -q                          # 71 tests
```

---

## 6. BEFORE you push to GitHub — final checklist
- [ ] Deleted everything in Step 0 (especially `venv/`, `.env`, `*.session`, `*.db`, `node_modules/`).
- [ ] `git status` shows **no** `.env`, `venv/`, `*.db`, `*.session`, `node_modules/`, `reports/`. (They're gitignored — confirm they don't appear.)
- [ ] You **regenerated `JWT_SECRET`** and are using your own API keys (Step 2).
- [ ] You did **not** `git add -f` any ignored file.
- [ ] `.env.example` (the template, no real secrets) **is** committed — that's intended.
- [ ] If this repo's git history is from the original, confirm no secret was ever committed:
      `git log --all -- .env` should be **empty** (it was never tracked in the original).
- [ ] Run `python -m pytest tests/ -q` → 71 passing before you push.

> Quick secret scan before pushing:
> ```bash
> git ls-files | grep -E "\.env$|\.session$|\.db$"   # must print NOTHING
> ```

---

## 7. Notes / gotchas
- **Python must be 3.10.** Other versions may break pinned deps.
- **CLI tools resolve via `resolve_tool()`** (PATH + the venv's Scripts/bin) — searches `.exe`,
  `.bat`, and `.cmd` on Windows, so maigret/sherlock/holehe/ignorant/blackbird all work even if the
  venv isn't "activated", as long as the installs ran into that venv.
- **`truststore`** makes outbound TLS use the OS cert store — this is what lets scrapers and the
  LLM work behind corporate TLS-inspection proxies. Keep it installed.
- **Default admin** `admin` / `vertex2026` is a demo credential — change it before real use.
- **Blackbird needs `BLACKBIRD_PATH` in `.env`** — set it to wherever you cloned the repo (e.g. `C:\tools\blackbird`). The scraper also needs a `venv\Scripts\blackbird.bat` wrapper; create it manually (details in `SETUP.md` §3).
- **Name searches (seed type `name`)** use three Serper dorks (`site:linkedin.com/in`, `site:instagram.com`, `site:twitter.com`). LinkedIn/Instagram/Twitter handles are now extracted from the result URL paths, so correlation works correctly without needing Maigret/Sherlock on top.
- **False-positive filter** runs a hex control-username against Maigret, Sherlock, and Blackbird in parallel; broken-detector sites are excluded from real results and cached for 6 h in `reports/false_positive_sites.json`. This directory is created automatically.
- **Full engineering detail:** see `context.md` (read Sections 11–17 for the complete current state; §17 is a from-scratch setup walk-through).
