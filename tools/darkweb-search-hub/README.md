# Darkweb Search Hub

A small standalone search UI over three dark-web OSINT sources — **not** wired into
VERTEX's main investigation pipeline (same spirit as `tools/onionsearch-sandbox/`, but a
plain process instead of a Docker sandbox, since these sources don't need the same hard
network isolation OnionSearch does).

## Sources

1. **Ahmia** — Darkdump's `ahmia` engine. Clearnet-queryable (`ahmia.fi/search/?q=`), Tor
   Project-endorsed, filtered against Ahmia's own abuse/CSAM blacklist. Works with **no
   Tor running**. Default source, safest to leave always-on.
2. **Darkdump — other 5 engines** (vendored `backend/darkdump_vendor.py`, from
   [josh0xA/darkdump](https://github.com/josh0xA/darkdump), MIT): `notevil`, `tor66`,
   `onionland`, `excavator` are Tor-only; `tordex` works clearnet too. **`tordex`,
   `tor66`, `onionland`, `excavator` are UNFILTERED per upstream** — the API refuses to
   query them unless the caller passes `confirm_unfiltered=true` (the UI shows an
   explicit warning + checkbox for this, mirroring darkdump's own CLI confirmation
   prompt). Do not remove this gate.
3. **DeepDarkCTI** — not a live query. A curated list
   ([fastfire/deepdarkCTI](https://github.com/fastfire/deepdarkCTI)) of known dark-web
   forums/marketplaces/leak-sites/Telegram channels, cloned locally into
   `backend/deepdarkCTI/`. "Search" here is keyword matching over that static list.
   Refresh it periodically (community-curated, updates via `git pull`) — either hit
   `POST /api/deepdarkcti/refresh` or click "↻ refresh list" in the UI.

## Setup

Own venv, deliberately separate from VERTEX's main one (darkdump pins slightly different
dependency versions):

```bash
cd tools/darkweb-search-hub
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -c "import nltk; [nltk.download(p, quiet=True) for p in ('punkt','punkt_tab','stopwords')]"
```

**For full coverage (all 6 Darkdump engines, not just Ahmia):**
```bash
sudo apt install -y tor
systemctl is-active tor   # confirm it's running on 127.0.0.1:9050
```
Without Tor, the 4 Tor-only engines just show as unavailable in the UI — everything else
still works.

## Run

```bash
cd backend
source ../venv/bin/activate
uvicorn main:app --port 8010
```

Open **http://localhost:8010**.

## API

- `GET /api/health` — Tor status, per-engine availability/filtered flag, DeepDarkCTI category list.
- `GET /api/search?q=...&sources=ahmia,darkdump,deepdarkcti&darkdump_engines=tordex,tor66&confirm_unfiltered=false&amount=20`
- `POST /api/deepdarkcti/refresh` — `git pull` (or re-clone) the curated list.

## Notes / known sharp edges

- **Ahmia's search endpoint can take 10-15s** for broad queries (observed 14.7s for
  "hacking", 2.4MB response) — the vendored `darkdump_vendor.py` had this at a 15s
  timeout (tighter than every other engine's 20-30s in the same file); bumped to 30s
  locally. If you re-vendor from upstream, re-apply this fix.
- Individual engines (especially `tordex`) can return non-200 if the upstream site
  changed its URL structure — dark-web search engines rotate/disappear often. The API
  surfaces the real HTTP error rather than hiding it; that's expected, not a bug here.
- `backend/darkdump_vendor.py` + `backend/headers/` + `backend/banner/` are vendored
  (not pip-installable — darkdump ships as a script, not a package). MIT licensed,
  unmodified except the timeout fix above (see the inline comment at that line).
