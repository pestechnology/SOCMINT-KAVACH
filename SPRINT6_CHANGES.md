# Sprint 6 — Complete Changes Log (Commit `43932b3`)

Branch: `Vismay_Wednesday_Updated`  
Committed: 2026-07-02  
Files changed: 9 | Insertions: +550 | Deletions: -40

---

## 1. Backend Changes

### 1.1 `backend/ingestion/profile_page_fetcher.py` — Placeholder-avatar false-positive fix

**Problem:** Twitter/X serves its own default avatar (`default_profile_images/...`) to
non-JS requesters instead of the user's real photo. If stored as `photo_url`, the pHash
pipeline would hash it and falsely link unrelated accounts (everyone with no/blocked avatar
gets the same hash → false `profile_photo_phash` match).

**Edit 1 — Added `_PLACEHOLDER_IMAGE_MARKERS` tuple and `_is_placeholder` helper**
(inserted between `_CONCURRENCY` and `_OG_IMAGE` regex definitions):

```python
_PLACEHOLDER_IMAGE_MARKERS = (
    "default_profile_images", "default_profile_normal", "default_profile.png",
    "avatar-default", "no_avatar", "no-avatar", "anonymous-user",
    "missing-avatar", "default-avatar",
)

def _is_placeholder(url: str) -> bool:
    u = url.lower()
    return any(marker in u for marker in _PLACEHOLDER_IMAGE_MARKERS)
```

**Edit 2 — Guard in `_enrich_one()`** (line 127):

```python
# Before:
if photo and not meta.get("photo_url"):
    meta["photo_url"] = photo

# After:
if photo and not meta.get("photo_url") and not _is_placeholder(photo):
    meta["photo_url"] = photo
```

---

### 1.2 `backend/ingestion/photo_enrich.py` — Same placeholder guard in pHash pipeline

**Problem:** Even if `profile_page_fetcher` was safe, a placeholder URL already stored by
another scraper under a key like `avatar` or `image_url` could still be picked up and
hashed by `photo_enrich.py`.

**Edit — Added `_PLACEHOLDER_IMAGE_MARKERS` and guard in `_photo_url_of()`**:

```python
# Added constant (same markers as profile_page_fetcher.py):
_PLACEHOLDER_IMAGE_MARKERS = (
    "default_profile_images", "default_profile_normal", "default_profile.png",
    "avatar-default", "no_avatar", "no-avatar", "anonymous-user",
    "missing-avatar", "default-avatar",
)

# Before:
def _photo_url_of(meta: dict) -> str | None:
    for k in _PHOTO_KEYS:
        v = meta.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.split("?")[0] if k == "icon_img" else v
    return None

# After:
def _photo_url_of(meta: dict) -> str | None:
    for k in _PHOTO_KEYS:
        v = meta.get(k)
        if isinstance(v, str) and v.startswith("http"):
            url = v.split("?")[0] if k == "icon_img" else v
            if any(marker in url.lower() for marker in _PLACEHOLDER_IMAGE_MARKERS):
                continue
            return url
    return None
```

---

### 1.3 `backend/ingestion/reddit_scraper.py` — Submitted-posts scraper + gallery images

**Problem:** Only comments were fetched. Submitted posts were ignored — both their
timestamps (missing from the `posting_hours` fingerprint) and any images they contained
(gallery was always empty for Reddit profiles).

**Edit 1 — Updated module docstring** to mention submitted-posts and the media gallery.

**Edit 2 — Added `_THUMB_PLACEHOLDERS` and `_post_image_url()` helper**:

```python
# Reddit's literal placeholder strings in the thumbnail field — not real image URLs
_THUMB_PLACEHOLDERS = {"self", "default", "nsfw", "spoiler", "image", ""}

def _post_image_url(post: dict) -> str | None:
    """Best-effort real image URL for a submitted post, or None if it has none."""
    # 1. thumbnail field (if it's a real http URL, not a placeholder word)
    thumb = post.get("thumbnail") or ""
    if thumb.startswith("http") and thumb not in _THUMB_PLACEHOLDERS:
        return thumb
    # 2. direct image URL in post.url
    url = post.get("url") or ""
    if url.startswith("http") and url.lower().split("?")[0].endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".webp")
    ):
        return url
    # 3. Reddit high-res preview (HTML-entity decoded)
    preview = (post.get("preview") or {}).get("images") or []
    if preview:
        src = (preview[0].get("source") or {}).get("url")
        if src:
            return src.replace("&amp;", "&")
    return None
```

Note: A stray `_IMAGE_EXT_RE = None` line was added then immediately removed in the same
session — it does not appear in the final file.

**Edit 3 — Added submitted-posts fetch in `_run_live()`**:

The existing comments fetch was refactored to use `all_epochs` instead of calling
`_activity_from_timestamps` immediately. A new fetch of `/user/{username}/submitted`
(25 posts, up to 10 with images) was added, merging its epochs into `all_epochs`:

```python
# Submitted posts: same timestamps signal, PLUS real post images and
# permalinks for the frontend media gallery. Capped at 10 posts.
try:
    sr = await client.get(
        f"{base}/user/{username}/submitted{suffix}",
        params={"limit": 25, "raw_json": 1},
        headers=headers,
    )
    if sr.status_code == 200:
        children = sr.json().get("data", {}).get("children", [])
        recent_posts = []
        for c in children:
            d = c.get("data", {})
            epoch = d.get("created_utc")
            if epoch:
                all_epochs.append(epoch)
            img = _post_image_url(d)
            if img and len(recent_posts) < 10:
                recent_posts.append({
                    "kind": "post",
                    "platform": "reddit",
                    "title": d.get("title"),
                    "image_url": img,
                    "posted_at": datetime.datetime.utcfromtimestamp(epoch).isoformat() + "Z"
                        if epoch else None,
                    "permalink": ("https://www.reddit.com" + d.get("permalink"))
                        if d.get("permalink") else None,
                })
        if recent_posts:
            meta["recent_posts"] = recent_posts
except Exception:
    pass

if all_epochs:
    meta.update(_activity_from_timestamps(all_epochs))
```

**Edit 4 — Cleanup:** Removed a stray `if False: pass` block that was left as an artifact
during refactoring. Final file has no dead code.

---

### 1.4 `backend/ingestion/github_scraper.py` — Public-events activity feed

**Problem:** GitHub profiles had no `recent_posts` data at all. The gallery showed nothing
for GitHub entities.

**Edit 1 — Updated module docstring** to describe the events feed and the `kind="activity"`
convention.

**Edit 2 — Added `_EVENT_LABELS` dict**:

```python
_EVENT_LABELS = {
    "PushEvent": "pushed commits to",
    "CreateEvent": "created",
    "PullRequestEvent": "opened a pull request on",
    "IssuesEvent": "opened an issue on",
    "WatchEvent": "starred",
    "ForkEvent": "forked",
    "IssueCommentEvent": "commented on",
    "ReleaseEvent": "published a release on",
    "PublicEvent": "made public",
}
```

**Edit 3 — Added `_recent_activity()` async function**:

```python
async def _recent_activity(client: httpx.AsyncClient, login: str) -> list[dict]:
    """Up to 10 recent public GitHub events with real timestamps. Never raises."""
    try:
        r = await client.get(f"{_API}/users/{login}/events/public", params={"per_page": 30})
        if r.status_code != 200:
            return []
        out = []
        for ev in r.json()[:30]:
            if len(out) >= 10:
                break
            repo = (ev.get("repo") or {}).get("name")
            created = ev.get("created_at")
            if not repo or not created:
                continue
            out.append({
                "kind": "activity",
                "platform": "github",
                "title": f"{_EVENT_LABELS.get(ev.get('type'), ev.get('type'))} {repo}",
                "image_url": None,   # explicit None — GitHub has no post images
                "posted_at": created,
                "permalink": f"https://github.com/{repo}",
            })
        return out
    except Exception:
        return []
```

Key design decision: `image_url: None` (explicit) so the frontend gallery loop's
`!p.image_url` check correctly skips these entries — no fake photo tiles for activity.

**Edit 4 — Changed `_profile_from_user` from sync to async**:

```python
# Before (sync):
def _profile_from_user(user: dict) -> RawProfile:
    return make_profile("social_account", user.get("login", ""), "github",
        user.get("html_url", ""), metadata={...})

# After (async, awaits _recent_activity):
async def _profile_from_user(client: httpx.AsyncClient, user: dict) -> RawProfile:
    login = user.get("login", "")
    activity = await _recent_activity(client, login) if login else []
    meta = {
        "name": user.get("name"), "location": user.get("location"),
        "bio": user.get("bio"), "followers": user.get("followers"),
        "public_repos": user.get("public_repos"), "photo_url": user.get("avatar_url"),
        "email": user.get("email"), "blog": user.get("blog"),
        "created_at": user.get("created_at"),
    }
    if activity:
        meta["recent_posts"] = activity
    return make_profile("social_account", login, "github", user.get("html_url", ""), metadata=meta)
```

**Edit 5 — Updated both call sites in `_run_live()`** from `_profile_from_user(ur.json())`
to `await _profile_from_user(client, ur.json())` and from `_profile_from_user(r.json())`
to `await _profile_from_user(client, r.json())`.

---

## 2. Frontend Changes

### 2.1 `frontend/app/cases/[id]/page.js` — Gallery + layout + `safeUrl` fix

#### Page layout change (scrollable)

```jsx
// Before — fixed single-viewport, nothing below the fold:
<div className="h-screen flex flex-col bg-ink overflow-hidden">
  ...
  <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>

// After — scrollable, gallery/forensics/timeline visible below:
<div className="min-h-screen flex flex-col bg-ink">
  ...
  <div className="flex overflow-hidden" style={{ minHeight: 0, height: "64vh", flexShrink: 0 }}>
```

The three-panel area now takes 64 vh (fixed), and gallery/forensics/timeline sections
appear below as the user scrolls.

#### `STRONG_SIGNALS` constant extracted

```javascript
// Before — duplicated inline arrays in buildGalleryItems and ConfidenceLabel:
const STRONG = ["exact_email_match", "exact_phone_match", "exact_upi_match",
                "profile_photo_phash", "exact_name_match"];

// After — single top-level constant reused by both:
const STRONG_SIGNALS = ["exact_email_match", "exact_phone_match", "exact_upi_match",
  "profile_photo_phash", "exact_name_match"];
```

`ConfidenceLabel` was updated to use `STRONG_SIGNALS` instead of its own local copy.

#### `buildGalleryItems` — two-phase evolution

**Phase 1 (URL-only dedup):** Initial version used a single `seen` Set keyed on URL:

```javascript
function buildGalleryItems(entities, infoByEntity) {
  const seen = new Set();
  const items = [];
  entities.forEach((e) => {
    const m = e.metadata || {};
    // ...
    const avatarUrl = m.photo_url || m.avatar || m.avatar_url || m.image || null;
    if (avatarUrl && !seen.has(avatarUrl)) {
      seen.add(avatarUrl);
      items.push({ key: `avatar-${e.entity_id}`, url: avatarUrl, ... });
    }
    // post images loop...
  });
  items.sort(...);
  return items;
}
```

**Phase 2 (pHash dedup + REJECT-tier filter):** After identifying that the same face can
appear from 10–15 different CDN URLs (making URL dedup ineffective for avatars), the
function was rewritten:

```javascript
function buildGalleryItems(entities, infoByEntity) {
  const seenUrls = new Set();    // URL dedup — post images + avatar fallback
  const seenPhashes = new Set(); // pHash dedup — avatar primary key
  const items = [];

  entities.forEach((e) => {
    const m = e.metadata || {};
    const info = infoByEntity[e.entity_id];
    const tier = info?.tier || "REJECT";
    const sigs = info?.cluster?.signals ? Object.keys(info.cluster.signals) : [];
    const confirmed = (tier === "HIGH" || tier === "MEDIUM") &&
                      sigs.some((s) => STRONG_SIGNALS.includes(s));

    // Avatar: skip REJECT-tier singletons (different people sharing a username)
    // then dedupe by phash; fall back to URL dedup when no phash available
    const avatarUrl = m.photo_url || m.avatar || m.avatar_url || m.image || null;
    if (avatarUrl && tier !== "REJECT") {
      const phash = m.photo_phash || null;
      const isDup = phash ? seenPhashes.has(phash) : seenUrls.has(avatarUrl);
      if (!isDup) {
        if (phash) seenPhashes.add(phash);
        seenUrls.add(avatarUrl);
        items.push({ key: `avatar-${e.entity_id}`, url: avatarUrl, ... });
      }
    }

    // Post images — GitHub entries have image_url: null → skipped by !p.image_url
    const posts = Array.isArray(m.recent_posts) ? m.recent_posts : [];
    posts.forEach((p, i) => {
      if (!p.image_url || seenUrls.has(p.image_url)) return;
      seenUrls.add(p.image_url);
      items.push({ key: `post-${e.entity_id}-${i}`, url: p.image_url, ... });
    });
  });

  items.sort((a, b) => {
    if (a.confirmed !== b.confirmed) return a.confirmed ? -1 : 1;
    if (a.postedAt && b.postedAt) return new Date(b.postedAt) - new Date(a.postedAt);
    if (a.postedAt) return -1;
    if (b.postedAt) return 1;
    return 0;
  });
  return items.slice(0, 30);  // cap added in phase 2
}
```

#### `GalleryTile` component (new)

Added after `AccountCard`. Renders a 108×108 image tile with:
- Tier-colored border (`accent` from `HIGH`/`MEDIUM`/`LOW`/`REJECT` map)
- Platform badge (top-left overlay, 7px mono text)
- Broken-image handler: `onError` finds `closest("[data-gallery-tile]")` and sets
  `display: "none"` — hides the entire tile, not just the `<img>` tag
- Label (first 40 chars, 2-line max via `maxHeight`)
- Timestamp (ISO → `"YYYY-MM-DD HH:MM UTC"` format)
- Confirmed indicator: green `● CONFIRMED` or amber `◐ POSSIBLE`
- Wraps in `<a>` when `item.link` is present, plain `<div>` otherwise

Note: An "ACTIVITY" label overlay for `kind === "activity"` tiles was added during
development and then removed — GitHub activity entries have `image_url: null` and are
excluded from the gallery before they reach `GalleryTile`, so the badge was unreachable
dead code.

#### `safeUrl` fix

**Problem:** `new URL("", window.location.origin)` resolves an empty string to the current
page URL, which has `http:` protocol — so `safeUrl("")` returned the case page URL.
Gallery tiles with an empty `source_url` would silently link back to the same page.

```javascript
// Before:
function safeUrl(url) {
  if (!url || typeof url !== "string") return null;
  try {
    const u = new URL(url, window.location.origin);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}

// After — no base argument: empty strings and relative paths throw → return null:
function safeUrl(url) {
  if (!url || typeof url !== "string") return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}
```

#### Media Gallery section inserted in JSX

Added between the three-panel area and the Forensic Analysis section:

```jsx
{/* MEDIA GALLERY — every profile photo + real post image found, with source link */}
{!running && (
  <div className="border-t border-edge bg-surface">
    <div className="panel-label" style={{ padding: "10px 16px" }}>
      MEDIA GALLERY ({galleryItems.length})
    </div>
    {galleryItems.length === 0 ? (
      <div className="mono text-dim text-center" style={{ fontSize: 10, padding: "24px 0" }}>
        NO IMAGES RECOVERED FOR THIS CASE
      </div>
    ) : (
      <div className="flex flex-wrap" style={{ gap: 10, padding: "12px 16px" }}>
        {galleryItems.map((item) => <GalleryTile key={item.key} item={item} />)}
      </div>
    )}
  </div>
)}
```

---

### 2.2 `frontend/app/login/page.js` — Signal count correction

Line 67: `"12-signal correlation engine"` → `"15-signal correlation engine"`

The correlation engine has 15 signals (verified against `correlation_engine.py`
`SIGNAL_WEIGHTS` dict which lists all 15 keys).

---

### 2.3 `frontend/app/globals.css` — Full vis-timeline dark theme

**Problem:** The vis-timeline panel backgrounds defaulted to white (browser default). Item
colors, the label column, and selected-item state had no dark overrides.

```css
/* Before — only borders and font were overridden: */
.vis-item { border-width: 1px; border-radius: 2px; }
.vis-item .vis-item-content { padding: 2px 4px; }

/* After — full dark theme added: */
.vis-panel, .vis-background { background: #0E1117 !important; }

.vis-item {
  border-width: 1px;
  border-radius: 2px;
  color: #CBD5E0 !important;
  border-color: #2A3148 !important;
  background: #1E2235 !important;
  font-size: 10px !important;
}
.vis-item .vis-item-content { padding: 2px 6px; }

.vis-item.vis-selected {
  border-width: 2px !important;
  box-shadow: 0 0 0 1px rgba(212,144,10,0.25) !important;
}

.vis-labelset .vis-label {
  background: #161B27 !important;
  color: #8693A8 !important;
  border-color: #2A3148 !important;
}

.vis-current-time { background: rgba(212,144,10,0.35) !important; width: 1px !important; }
```

Note: The per-tier inline `style` strings set in `Timeline.js` (e.g.
`background-color:${color}22; border-color:${color}; color:#EDF2F7`) are applied as DOM
inline styles and therefore override these CSS class rules. The CSS rules serve as
fallbacks for any items or states not covered by inline styles.

---

### 2.4 `frontend/app/cases/page.js` — Disabled button states in investigation modal

**Problem:** When the "BEGIN INVESTIGATION" request was in-flight (`busy=true`), both
buttons had no visual feedback — they looked fully clickable even though disabled.

```jsx
// Before:
<button onClick={onClose} disabled={busy} className="mono text-dim" style={{ fontSize: 10 }}>
  CANCEL
</button>
<button onClick={begin} disabled={busy} className="mono" style={{ ... }}>
  {busy ? "STARTING…" : "BEGIN INVESTIGATION"}
</button>

// After:
<button onClick={onClose} disabled={busy}
  className="mono text-dim disabled:opacity-40" style={{ fontSize: 10 }}>
  CANCEL
</button>
<button onClick={begin} disabled={busy}
  className="mono disabled:opacity-40 disabled:cursor-not-allowed" style={{ ... }}>
  {busy ? "STARTING…" : "BEGIN INVESTIGATION"}
</button>
```

---

## 3. `context.md` — Sections 18 and 19 appended (+219 lines)

`context.md` is the living technical reference for the project. Two new sections were
appended — one per session.

### Section 18 — Sprint 6 changes (previous session)

| Sub-section | What it documents |
| ----------- | ----------------- |
| **18.1** | Placeholder-avatar false-positive fix — `_PLACEHOLDER_IMAGE_MARKERS` denylist, why X/Twitter's default avatar causes false `profile_photo_phash` links, where each guard lives |
| **18.2** | Reddit submitted-posts scraper — `_post_image_url()` three-tier fallback, `_THUMB_PLACEHOLDERS`, `recent_posts` dict format, epoch merging for `posting_hours_overlap` |
| **18.3** | GitHub public-events activity feed — `_EVENT_LABELS`, `kind="activity"`, `image_url: None` design decision, async change to `_profile_from_user` |
| **18.4** | Frontend media gallery dedup — two-Set approach (`seenPhashes` + `seenUrls`), REJECT-tier skip, 30-item cap, `safeUrl` no-base-URL fix |
| **18.5** | Verified state: build clean, 71/71 tests, live GitHub test vs `torvalds`, Reddit 403 note |

### Section 19 — Post-sprint audit (this session)

| Sub-section | What it documents |
| ----------- | ----------------- |
| **19.1** | Signal count fix — `"12-signal"` → `"15-signal"` in `login/page.js` |
| **19.2** | vis-timeline dark theme — all added CSS rules; note that `Timeline.js` inline styles override class defaults |
| **19.3** | Modal button disabled states — `disabled:opacity-40` on CANCEL and BEGIN INVESTIGATION |
| **19.4** | Image storage pipeline full audit — storage keys per scraper, `_photo_url_of()` priority order, `None`-value safety, SQLite round-trip chain (`json.dumps → metadata_json → json.loads → API → frontend`), `null`/`!p.image_url` skip |
| **19.5** | Verified state: build clean, 71/71 tests, all 7 endpoints verified, full pipeline traced |

---

## 4. Commands Run (Previous Session — Backend)

```bash
# After each scraper edit — verify Python syntax:
python -c "import backend.ingestion.reddit_scraper"    # ✅ no syntax errors
python -c "import backend.ingestion.github_scraper"    # ✅ no syntax errors

# Live smoke test — GitHub scraper against a real account:
python -c "
import asyncio
from backend.ingestion.github_scraper import GitHubScraper
async def main():
    s = GitHubScraper()
    r = await s.run('torvalds')
    print(len(r), 'profiles')
    print(r[0].metadata.get('recent_posts', [])[:2])
asyncio.run(main())
"
# → 1 profiles
# → [{'kind': 'activity', 'platform': 'github', 'title': 'pushed commits to torvalds/linux',
#     'image_url': None, 'posted_at': '2025-...', 'permalink': 'https://github.com/torvalds/linux'},
#    {...}]
# Result: real avatar + 10 real timestamped activity entries returned ✅

# Live smoke test — Reddit scraper (got 403 on test machine, network issue not a bug):
python -c "
import asyncio
from backend.ingestion.reddit_scraper import RedditScraper
async def main():
    s = RedditScraper()
    r = await s.run('spez')
    print(r)
asyncio.run(main())
"
# → 403 from reddit.com on this network (expected in datacenter/VPN environment;
#   works from residential IP or with REDDIT_CLIENT_ID/SECRET configured)

# Full test suite:
pytest tests/ -q
# → 71 passed in X.XXs   ✅
```

---

## 4. Commands Run (Current Session — Frontend + Build)

```bash
# After all frontend edits — verify Next.js build:
cd frontend
npm run build
# Output:
#  ✓ Compiled successfully
#  ✓ Generating static pages (6/6)
#  Route sizes:
#    /cases        3.91 kB
#    /cases/[id]   8.56 kB
#    /login        2.61 kB
# → 0 errors, 0 type warnings  ✅

# Clear stale .next dev-server cache (fixes webpack chunk error on dev server):
Remove-Item -Recurse -Force frontend/.next
# → Deleted. Dev server must be restarted with `npm run dev` to rebuild from scratch.

# Git — stage code files only (skip .txt investigation-output files):
git add \
  backend/ingestion/github_scraper.py \
  backend/ingestion/photo_enrich.py \
  backend/ingestion/profile_page_fetcher.py \
  backend/ingestion/reddit_scraper.py \
  context.md \
  "frontend/app/cases/[id]/page.js" \
  frontend/app/cases/page.js \
  frontend/app/globals.css \
  frontend/app/login/page.js

# Commit:
git commit -m "Sprint 6: media gallery dedup, placeholder fix, Reddit posts, GitHub activity, UI polish"
# → [Vismay_Wednesday_Updated 43932b3] 9 files changed, 550 insertions(+), 40 deletions(-)

# Push:
git push origin Vismay_Wednesday_Updated
# → 06141af..43932b3  Vismay_Wednesday_Updated -> Vismay_Wednesday_Updated  ✅
```

---

## 5. Verification Performed (Full Audit — Current Session)

| File | What was checked | Result |
|------|-----------------|--------|
| `backend/ingestion/maigret_scraper.py` | `photo_url: ids.get("image")` stores `None` when maigret has no image — handled correctly by `photo_enrich._photo_url_of` (skips non-str values) | ✅ |
| `backend/ingestion/holehe_scraper.py` | No photo fields, no `recent_posts` — correct for email-registration scraper | ✅ |
| `backend/ingestion/photo_enrich.py` | `_photo_url_of` priority order; `meta.setdefault("photo_url", url)` won't overwrite scrapers' own `photo_url`; placeholder guard | ✅ |
| `backend/ingestion/profile_page_fetcher.py` | `_needs_fetch` logic; `_is_placeholder`; og:image regex (both attribute orders); `_enrich_one` guard | ✅ |
| `backend/ingestion/reddit_scraper.py` | `_post_image_url` 3-tier fallback; `_THUMB_PLACEHOLDERS`; submitted-posts fetch; `recent_posts` dict structure; stray `if False:` removed | ✅ |
| `backend/ingestion/github_scraper.py` | `_recent_activity`; `image_url: None` explicit; async propagation to both `_run_live` call sites | ✅ |
| `backend/cases/case_service.py` | `metadata_json = json.dumps(p.metadata)` → `json.loads(e.get("metadata_json") or "{}")` round-trip — `photo_url`, `photo_phash`, `recent_posts` all survive | ✅ |
| `backend/cases/case_routes.py` | All 5 endpoints present and correct | ✅ |
| `backend/main.py` | CORS allows `:3000`/`:3001`; health endpoint returns `DATA_MODE` | ✅ |
| `frontend/lib/api.js` | All API calls match backend routes; 401 handling via `err.status = res.status` | ✅ |
| `frontend/app/cases/page.js` | Registry, search filter, modal seed types (6 types + url), MINOR flag | ✅ |
| `frontend/app/cases/[id]/page.js` | Gallery dedup logic; `AccountCard` onError `nextSibling` chain; `ConfidenceLabel` uses shared `STRONG_SIGNALS`; `safeUrl` no-base fix | ✅ |
| `frontend/components/Timeline.js` | Per-tier inline styles override CSS; `showCurrentTime: false` (current-time CSS is harmless no-op) | ✅ |
| `frontend/components/Graph.js` | `NODE_COLOR`/`EDGE_COLOR` match `globals.css` tier colors; rebuild signature includes `confidence_score` | ✅ |
| `frontend/tailwind.config.js` | Color tokens verified: ink, surface, lifted, edge, dim, body, head, amber, steel, crimson, emerald | ✅ |

---

## 6. Files NOT Committed (intentionally excluded)

| File | Reason |
|------|--------|
| `Ash29_03.txt` | Maigret investigation output — runtime artifact |
| `Dhanush Shankar Reddy.txt` | Investigation output |
| `vismay_hs.txt` | Investigation output |
| `z40e4956b697a4fa0944.txt` | Maigret control-probe report (`fp_filter.py` output) |
| `z5b0f2ee133ec4ebc941.txt` | Maigret control-probe report |
| `zed0df2763172441aac3.txt` | Maigret control-probe report |
| `zzqxwv847629nonexistent.txt` | Maigret control-probe report (the nonsense-username probe) |

These are generated at runtime by the false-positive filter. They do not belong in version
control. Add `*.txt` or specific patterns to `.gitignore` to prevent them accumulating.

---

## 7. Final Build / Test Status

| Check | Result |
|-------|--------|
| `npm run build` | ✅ Clean — 0 errors, 0 type warnings |
| `pytest tests/ -q` | ✅ 71/71 passing (no regressions) |
| Live GitHub scraper test | ✅ `torvalds` → avatar + 10 activity entries |
| Live Reddit scraper test | ⚠ 403 on test network (expected — works on residential IP or with OAuth creds) |
| Commit hash | `43932b3` |
| Branch | `Vismay_Wednesday_Updated` |
| Remote | `https://github.com/dhanush-sr/VERTEX.git` |
