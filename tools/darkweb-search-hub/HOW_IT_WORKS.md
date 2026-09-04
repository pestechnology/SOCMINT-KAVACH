# How each source actually works

Mechanics of the three sources behind `backend/main.py`'s `/api/search` — what happens on
the wire for each one, not just what the API returns.

---

## 1. Ahmia

**What it is:** a real, standalone dark-web search engine (`ahmia.fi`), Tor
Project-endorsed since 2014. It crawls `.onion` sites itself and keeps its own index —
we're not scraping arbitrary onion pages, we're querying *its* search index.

**How `_fetch_ahmia()` actually queries it** (`backend/darkdump_vendor.py`):
1. `GET https://ahmia.fi/` (clearnet — no Tor needed for this or step 2; Ahmia mirrors
   its own index to a clearnet endpoint specifically so it's reachable without Tor).
2. Ahmia's search form carries a **hidden CSRF nonce** (`<input type="hidden" name="dd6a52" value="...">`,
   the field name itself is randomised) — parsed out of the homepage HTML with BeautifulSoup.
3. `GET https://ahmia.fi/search/?q={query}&{nonce_name}={nonce_value}` — the nonce must be
   fresh per request or Ahmia rejects the search.
4. Results come back as `<li class="result">` elements, each with a `<cite>` (the onion
   URL), `<a>` (title), `<p>` (description) — parsed into `{title, description, site_url}`.
5. **Every result is checked against Ahmia's own MD5-hashed abuse blacklist**
   (`GET https://ahmia.fi/blacklist/banned/`, cached 1h) before being returned —
   `Darkdump._filter_blacklisted()`. This is Ahmia's actual production CSAM/abuse filter,
   not something bolted on here.
6. **Known sharp edge:** the search request (step 3) can take 10-15s for a broad query —
   observed 14.7s / 2.4MB response for "hacking". Timeout bumped to 30s locally (see the
   comment at that line in `darkdump_vendor.py`).

**Net effect:** the one source here that's both safe to query with no setup (no Tor) and
actively content-filtered by the operator. Best default.

---

## 2. Darkdump's other 5 engines

Same vendored file, five more `_fetch_*` methods — each one hand-parses a different
site's HTML because none of these expose a real API:

| Engine | Reached via | Filtered? | Notes |
|---|---|---|---|
| `notevil` | Tor-only (`.onion`) | Yes (partial) | An Ahmia fork with a broader, less-curated index; click-count ranking. Tries several known search-path variants (`/search?q=`, `/?q=`, `/index.php?q=`) since the site has changed its path before. |
| `tordex` | Clearnet (`tordex.cc`) or `.onion` if Tor is on | **No** | Uncensored index. **Its clearnet endpoint returned HTTP 404 during testing** — dark-web search sites rotate/restructure often; the API surfaces that error as-is rather than hiding it. |
| `tor66` | Tor-only | **No** | Crawled index with category directories; results are parsed from `<b>` tags after the page's first `<hr>` — a fragile, layout-dependent parse. |
| `onionland` | Tor-only | Minimal | Indexes Tor, I2P, *and* clearnet sites from one interface; result links are redirect-wrapped and get decoded before returning. |
| `excavator` | Tor-only | **No** | Least documented of the six; parsed from `<div class="result">`. |

**Why 4 of these need Tor and Ahmia doesn't:** those four only exist as `.onion`
services with no clearnet mirror — reaching them at all requires a SOCKS5 proxy through a
running Tor daemon (`socks5h://localhost:9050`, the standard local Tor SOCKS port).
`backend/main.py`'s `_tor_is_up()` just tries a raw TCP connect to `127.0.0.1:9050` before
bothering to call the fetcher, so a Tor-down environment fails fast with a clear message
instead of hanging on a dead proxy.

**Why the unfiltered ones are gated:** "unfiltered" here means literally that — no abuse
blacklist, no CSAM filtering, nothing. `/api/search` refuses to call `tordex`/`tor66`/
`onionland`/`excavator` unless the request explicitly sets `confirm_unfiltered=true`, and
the frontend shows a warning + checkbox before it'll send that flag. This mirrors
Darkdump's own CLI, which stops and asks `Continue with {engine}? [y/N]` before running
any `filtered: False` engine.

---

## 3. DeepDarkCTI

**Not a search engine at all** — it's a community-curated *reference list*
(github.com/fastfire/deepdarkCTI), maintained by CTI researchers proposing sources
through a private Telegram group, and periodically merged into the repo as plain
Markdown tables — one file per category (`ransomware_gang.md`, `forum.md`,
`telegram_threat_actors.md`, `markets.md`, `phishing.md`, 19 categories total).

**How "search" works here** (`backend/deepdark_search.py`):
1. The repo is `git clone --depth 1`'d once into `backend/deepdarkCTI/` — this is a
   **snapshot**, not a live query. Staleness is only fixed by re-pulling
   (`POST /api/deepdarkcti/refresh`, or the "↻ refresh list" button).
2. Every category file is a markdown table, but **two different styles are used across
   files** — most are `|[Name](url)|STATUS|...|`, but some (e.g.
   `telegram_threat_actors.md`) are `|url|STATUS|Name|Type|` with no markdown link syntax
   at all. `_parse_table_row()` handles both: it splits each `|`-delimited row into
   cells, and per cell checks (in order) — is it a `[name](url)` link? does it look like a
   bare URL/`.onion` address? is it a known status word (`ONLINE`/`OFFLINE`/`EXPIRED`/…)?
   — whatever's left becomes the name.
3. A query is just a case-insensitive substring match against the raw line text, before
   parsing — so it matches on name, URL, or category content, whichever contains the term.
4. Each matching row returns `{category, name, url, status}` — `status` reflects whatever
   the maintainers last recorded (these lists go stale between refreshes; a `.onion`
   marked `ONLINE` may not be reachable *right now*).

**Net effect:** this source answers "what dark-web venues are *known* to exist for X,"
not "what's live right now" — it's a target list to seed further investigation with, not
a live signal. Re-run the refresh periodically if you're relying on current status.
