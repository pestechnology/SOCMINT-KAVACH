# VERTEX — Final UI Redesign Spec (for Claude Code)

> **This file is your complete brief. Follow it end to end.** You have access to the
> existing VERTEX codebase. Read this whole spec first, then execute tasks in the
> order given.
>
> **The Repository Safety section immediately below supersedes everything else in
> this spec.** If any instruction later in this file appears to conflict with the
> safety rules, the safety rules win. §1 (Non-Negotiables — Code) breaks the app
> silently if ignored. Breaking the safety rules is worse than not shipping at all.

---

## 🛑 REPOSITORY SAFETY — READ FIRST, SUPERSEDES EVERYTHING BELOW

This spec lives inside a shared team repo with a live `main` branch and a
teammate's ongoing work. The user works on the `dhanush` branch. Whatever you
do must be **undoable by the user with a single `git checkout .` or `git stash`**.
That means: you never commit, push, or touch git plumbing. Ever.

### A. Git operations — FORBIDDEN

You do NOT run any of these commands, in any form, under any justification:

```
git add        git commit     git push       git pull       git fetch
git checkout   git switch     git branch     git merge      git rebase
git reset      git stash      git clean      git restore    git rm
git tag        git remote     git cherry-pick
```

You do NOT modify `.git/`, `.gitignore`, `.gitattributes`, or any git hook file.
You do NOT create new branches, switch branches, or touch `main` or any other
branch. Work only on whatever branch is currently checked out.

You do NOT suggest committing anything, however small. Commit decisions belong
to the user alone. Do not write commit messages, do not stage files, do not
prompt the user to commit "when convenient".

### B. File scope — allowed vs forbidden

**You MAY modify files under `frontend/`** (except `frontend/node_modules/`).

**You MUST NOT modify or delete anything else.** Specifically forbidden:

- `backend/**` — all Python source. Do not touch a single `.py` file.
- `tests/**` — the pytest suite. 101 tests pass right now; keep it that way.
- `scripts/**` — helper scripts (`create_admin.py`, `seed_demo_case.py`, etc.)
- `.env`, `.env.example`, `frontend/.env.local`, `frontend/.env.local.example`
- `requirements.txt`
- `cidecode.db` and any other `*.db` file
- `reports/**` — generated PDFs and artifacts
- Any `.md` file at the repo root (`context.md`, `HANDOFF.md`,
  `LEGAL_VERIFICATION.md`, `SETUP.md`, `README.md`, `DESIGN_AND_UI.md`,
  this spec itself)
- `frontend/next.config.mjs` — do not touch unless a task explicitly requires
  it AND you have asked the user first

You do NOT delete any file without explicit user permission — even files you
created earlier in this session.

### C. Dependency safety

- Do NOT run `npm install <new-package>` or `yarn add`. **No new dependencies.**
- Do NOT modify `frontend/package.json`. Everything this spec needs is either
  already in the project (Next.js, React, Tailwind, sigma.js, vis-timeline)
  or loaded via CDN link tag (Outfit and JetBrains Mono fonts).
- Do NOT update existing dependency versions.
- Do NOT regenerate or hand-edit `frontend/package-lock.json`.
- If a task seems to require a new package, STOP and ask the user before
  doing anything.

### D. Backup discipline (mandatory)

Before you modify an existing file **for the first time in this session**:

```bash
cp path/to/file.js path/to/file.js.pre-redesign
```

This creates a local safety net independent of git. Backups for files you
have already backed up once do not need to be re-created — one backup per
file per session is enough.

After the redesign is verified working, the user will delete these `.pre-redesign`
files. Do NOT stage or commit them. Do NOT delete them yourself.

### E. Verification cadence

- After EVERY file creation or modification, run:
  ```bash
  cd frontend && npm run build
  ```
- If the build fails, IMMEDIATELY revert that change:
  - New file you created: `rm` it.
  - Existing file you modified: `cp file.js.pre-redesign file.js`.
- Do NOT proceed to the next task until `npm run build` passes cleanly.
- Do NOT batch changes hoping they all work together — verify per file.
- If build passes but ESLint or type-check emits warnings, note them for the
  user but do not attempt to "clean them up" by editing files you weren't
  asked to touch.

### F. Environment & secrets safety

- Do NOT print, log, cat, or otherwise output the contents of any `.env` file
  or any file that could contain secrets.
- Do NOT reference or hardcode API keys, JWT secrets, database paths, or any
  credential anywhere.
- Do NOT start the backend, restart `uvicorn`, or modify any running process.
  You only touch the frontend source. If the frontend needs the backend
  running to test, the user will handle that.

### G. If something goes wrong

- STOP immediately. Do not attempt to auto-fix by making more changes.
- Report the exact error, exact file, exact line to the user.
- Wait for user instruction before touching anything else.
- Never "clean up" by deleting files or reverting other unrelated changes
  without explicit permission.
- If you notice a file outside `frontend/` has been modified (by anything —
  by you, by a tool, by a script), STOP and tell the user immediately.

### H. If in doubt

Ask the user. Any decision that could touch backend, tests, config, git, or
external state — ask before doing. It is always better to pause and ask than
to proceed and break something the user relied on.

### Recommended pre-flight (for the user, not for Claude Code)

Before invoking this spec, the user should:

1. `git status` — confirm the working tree is clean (no unstaged/staged changes
   the user cares about).
2. `git branch --show-current` — confirm on `dhanush`, not `main`.
3. Optional: `git stash` any WIP that isn't part of this redesign.

After Claude Code finishes, the user reviews with:

- `git status` and `git diff` — should show ONLY changes under `frontend/`.
- If anything outside `frontend/` shows up as modified, revert it with
  `git checkout -- <path>` before committing anything.
- Only the user decides what to commit and when.

---

## 0. Mission

VERTEX is a SOCMINT / OSINT suspect-profiling tool built for CIDECODE 2026 (CID
Karnataka police hackathon). Backend is done, tested, live. **This spec is
about the frontend only.**

The frontend today is a Next.js 14 App Router app (`frontend/`) with a dark
amber-on-black theme. It works but reads like a technical dashboard, not like
something a non-technical constable or a senior CID officer would find friendly
or trustworthy.

The mission of this redesign:

1. **Adopt** the visual system a teammate already designed (cyan/emerald/amber/crimson
   semantic palette, glass panels, JetBrains Mono + Outfit, glow background) —
   documented in §2 below.
2. **Rewrite** every piece of user-facing text into plain investigative English.
   Anything that sounds like a hacker movie ("Deploy Recon", "15 Agents Online",
   "Operation X") gets replaced with boring accurate language. This is the single
   biggest trust-building change.
3. **Restructure** the information architecture so a non-technical user sees the
   answer first (verdict + summary matrix + grouped identity list) and the
   technical view (network graph, hashes, raw signal weights) second.
4. **Preserve** the backend API contract, auth flow, polling loop, and report
   download exactly.

Two audiences to satisfy simultaneously:

- **Junior investigator / non-technical user** — needs to see the answer in
  30 seconds, in words they already know.
- **Senior CID officer or judge** — needs to trust the tool. Trust comes from
  restrained language, visible chain-of-custody, and BSA §63 compliance signaling.

---

## 1. Non-Negotiables (do not break these)

### 1.1 API contract (`lib/api.js`)
- Base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
- JWT lives in `localStorage["vertex_token"]`. Do not move it to cookies or
  sessionStorage.
- Every protected call sends `Authorization: Bearer <jwt>`.
- Keep the existing functions: `api.register`, `api.login`, `api.listCases`,
  `api.createCase`, `api.getCase`, `api.getResults`, `api.downloadReport`.

### 1.2 Results response shape (`GET /cases/{id}/results`)
Consume this exactly, don't invent fields:

```json
{
  "case": {
    "case_id": "...",
    "title": "...",
    "seeds": [{"type":"name|email|phone|username|upi|face|url","value":"..."}],
    "minor_involved": false,
    "status": "pending|running|complete|error",
    "created_at": "..."
  },
  "entities": [
    {
      "entity_id": "...",
      "type": "social_account|email|phone|username|upi|breach|web_mention|phone_intel|url|...",
      "value": "...",
      "platform": "github|linkedin|instagram|hibp|upi|derived|...",
      "confidence": 0-100,
      "metadata": {
        "fullname": "...", "bio": "...", "photo_url": "...", "phone": "...",
        "posting_hours": [12,13,14], "location": "...", "title": "...",
        "breaches": ["Adobe","LinkedIn"], "followers_sample": [...],
        "employer_candidates": [...], "location_candidates": [...],
        "sensitive_source": true|false, ...
      },
      "source_url": "...",
      "sha256": "..."
    }
  ],
  "clusters": [
    {
      "cluster_id": "...",
      "entity_ids": ["...", "..."],
      "confidence_score": 0-100,
      "tier": "HIGH|MEDIUM|LOW|REJECT",
      "explanation": "plain English sentence",
      "signals": {"exact_phone_match": 60, "profile_photo_phash": 35, ...}
    }
  ],
  "forensics": {
    "sentiment": {"label":"POSITIVE","score":0.988},
    "keywords": [...], "hashtags": [...],
    "activity_hours": {...}, "engagement": {...},
    "footprint": {...}
  },
  "status": "pending|running|complete|error"
}
```

### 1.3 Polling loop
While `status ∈ {"pending","running"}`, refetch every **1500 ms**. Stop when
`complete` or `error`. Keep this behavior.

### 1.4 Report download
Uses `api.downloadReport(id)` which does `fetch` with the Authorization header
and pipes the response to a Blob. **Never** use a plain `<a href>` — the auth
header can't ride on link navigation.

### 1.5 Auto-expand behavior
If `status === "complete"` and there are zero multi-member clusters, the
"Not linked" section must be open by default. Currently already correct
(§16.5 in the project context). Preserve.

### 1.6 Stack
Stay on Next.js 14 App Router + React 18 + Tailwind CSS 3.4. Do not migrate
to plain HTML. Do not add Redux, Zustand, tRPC, or any new state library.
Component state + polling is enough.

### 1.7 Semantic tier → color mapping (memorize)
- HIGH tier → **strong** → emerald
- MEDIUM tier → **possible** → amber
- LOW / REJECT / no tier → **weak / not linked** → crimson
- `running`/`pending` status or active/selected item → cyan

This mapping is used everywhere. Every badge, node color, and status pill obeys it.

### 1.8 Preserve the auto-generated PDF wiring
The "Download Evidence Report" button hits `GET /cases/{id}/report`. Do not
rename the button in a way that suggests it does something else. It generates
the BSA-63 court-admissible PDF.

---

## 2. Design System

### 2.1 CSS variables (add to `app/globals.css` inside `:root`)

```css
:root {
  --bg-primary: #070a12;
  --bg-secondary: #0f172a;
  --bg-glass: rgba(15, 23, 42, 0.75);
  --bg-glass-hover: rgba(30, 41, 59, 0.85);
  --border-glass: rgba(0, 242, 254, 0.25);
  --border-glow: rgba(0, 242, 254, 0.6);

  --accent-cyan: #00f2fe;
  --accent-purple: #4facfe;
  --accent-emerald: #00ff88;
  --accent-amber: #ffb703;
  --accent-crimson: #ff3366;

  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
}

html, body {
  background: var(--bg-primary);
  color: var(--text-main);
  font-family: 'Outfit', system-ui, sans-serif;
  font-size: 14px;
  color-scheme: dark;
}

.mono, .font-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
```

### 2.2 Fonts (add to `app/layout.js` head)

```jsx
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
<link
  href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap"
  rel="stylesheet"
/>
```

### 2.3 Ambient background layers

Add two divs at the top of `<body>` (in `app/layout.js`):

```jsx
<div className="glow-bg" />
<div className="grid-overlay" />
```

CSS in `globals.css`:

```css
.glow-bg {
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background: radial-gradient(ellipse 60% 40% at 50% 0%,
    rgba(0, 242, 254, 0.15) 0%, transparent 60%);
}
.grid-overlay {
  position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: 0.4;
  background-image:
    linear-gradient(rgba(0, 242, 254, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 242, 254, 0.04) 1px, transparent 1px);
  background-size: 40px 40px;
}
main { position: relative; z-index: 10; }
```

### 2.4 Tailwind config (`tailwind.config.js`)

Extend theme colors so Tailwind classes work alongside the CSS vars:

```js
theme: {
  extend: {
    colors: {
      ink: '#070a12',
      panel: '#0f172a',
      cyan: { 400: '#00f2fe' },
      emerald: { 400: '#00ff88' },
      amber: { 400: '#ffb703' },
      crimson: { 400: '#ff3366' },
    },
    fontFamily: {
      sans: ['Outfit', 'system-ui', 'sans-serif'],
      mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
    },
  },
},
```

### 2.5 Do NOT introduce
- A light theme
- New accent hues (only the 4 semantic colors + cyan for active)
- Border radiuses larger than `rounded-xl` (12px) — this is a forensic tool, not
  a consumer app
- Emoji as decoration. Emoji are allowed only as functional glyphs for section
  headers (e.g. `⚖️` for legal, `🔍` for search, `⚠️` for warning) — sparingly.
- Custom animations beyond the pulse-dot and the hover translate-Y on cards/buttons

---

## 3. Component Library

Build these as React components in `frontend/components/ui/`. **Build all of these
before touching any page** — pages compose them.

### 3.1 `<GlassPanel>` — the base container

```jsx
// components/ui/GlassPanel.jsx
export default function GlassPanel({ className = "", children, ...rest }) {
  return (
    <div
      className={`
        rounded-xl backdrop-blur-md
        bg-[var(--bg-glass)] border border-[var(--border-glass)]
        shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]
        transition-colors duration-300
        hover:border-[rgba(0,242,254,0.4)]
        ${className}
      `}
      {...rest}
    >
      {children}
    </div>
  );
}
```

### 3.2 `<StatusPill>` — investigation status indicator

Props: `status: "running" | "complete" | "error" | "pending"`.

```jsx
// running/pending: cyan + pulse-dot + label "In progress"
// complete: emerald + solid dot + label "Complete"
// error: crimson + solid dot + label "Error"
```

Use uppercase, letter-spaced, `text-[11px]`, `font-mono`. The pulse-dot is 8px
circular with `animation: pulse 1.5s infinite ease-in-out`.

```css
.pulse-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; box-shadow: 0 0 8px currentColor;
  animation: pulse 1.5s infinite ease-in-out;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%      { transform: scale(1.4); opacity: 0.5; }
}
```

### 3.3 `<ConfidenceBadge>` — the tier chip

Props: `tier: "HIGH" | "MEDIUM" | "LOW" | "REJECT"`.

Rendering:
- `HIGH` → emerald tinted, label **"Strong match"**
- `MEDIUM` → amber tinted, label **"Possible match"**
- `LOW` / `REJECT` → crimson tinted, label **"Not linked"**

Note: **do not** show the raw score prominently. If you want to expose it, put
it as `text-xs text-slate-500 font-mono` right after the badge — e.g.
`Strong match · 92/100`.

### 3.4 `<AccountCard>` — a single entity in the identity list

Props: `entity, selected, onClick`.

Structure:
- Row 1: platform icon (12px), platform name mono uppercase, right-aligned
  small `Live` chip if `entity.data_mode === "live"`.
- Row 2: primary display (from `metadata.fullname || value`).
- Row 3: secondary (from `metadata.title || metadata.bio` truncated 80 chars).
- Row 4: `<ConfidenceBadge tier={entity._tier} />` (derive tier from
  `confidence`: >=80 HIGH, 50-79 MEDIUM, <50 LOW).

Base: `rounded-lg`, `bg-slate-900/50`, thin white/8% border, `p-3`.
Hover / selected: `border-cyan-400`, `translateX(4px)`, subtle cyan shadow.

### 3.5 `<PivotPill>` — clickable evidence chip

Small cyan gradient pill for signal chips inside the same-person analysis
panel. Text like `📧 shared email` or `📞 same phone`. On hover fills solid.

### 3.6 `<Button>` — primary and secondary

- `variant="primary"`: cyan→purple gradient background, `text-black`, weight 600,
  `rounded-lg`, `px-5 py-2.5`, subtle cyan glow shadow. Lifts `-2px` on hover.
- `variant="secondary"`: `bg-slate-800/80`, thin white/15% border, hover
  border-cyan-400 and lift `-1px`.
- `variant="success"`: emerald→cyan gradient for the "Download Evidence Report"
  CTA. Same shape as primary.

### 3.7 `<Input>` and `<Label>`

Input: full-width, `bg-slate-900/80`, `border-slate-700`, `rounded-lg`, `px-3 py-2`,
focus ring: `border-cyan-400`, subtle cyan glow.

Label: `text-[11px] font-mono uppercase tracking-wide text-slate-300 mb-1.5`.

### 3.8 `<EmptyState>`

Props: `icon, title, description`. Centered, 48px icon, bold slate-200 title,
tiny muted description. Use in: no cases, no cluster selected, no timeline data,
no forensic data.

### 3.9 `<Tooltip>`

Small hover tooltip. Needed for the "Subject is a minor" checkbox and for
any technical field that needs an explanation.

---

## 4. Page-by-Page Redesign

### 4.1 Login (`app/login/page.js`)

**Layout:** Two columns on `lg`, single column below.
- Left (60%): brand block — big `VERTEX.` wordmark (Outfit 700, 48px, dot in
  cyan). Sub-line: `SOCMINT INTELLIGENCE PLATFORM · CIDECODE 2026` (mono, xs,
  muted). Below that, small feature bullets in a `.mono` list, cyan bullets:
  ```
  ↳ 20-signal correlation engine
  ↳ BSA §63 court-admissible evidence
  ↳ SHA-256 tamper-evident audit chain
  ```
  Bottom-left: fine print (xs, muted): `All sessions are logged.
  Unauthorised access is an offence under Section 43/66, IT Act 2000.`
- Right (40%): centered `<GlassPanel>` `max-w-md`, `p-8`:
  - Small mono label: `SIGN IN TO CONTINUE`
  - Username `<Input>` with `<Label>USERNAME</Label>`
  - Password `<Input type="password">` with `<Label>PASSWORD</Label>`
  - `<Button variant="primary" className="w-full">Sign in</Button>`
  - Small link `No account? Register` toggles the form to registration.

**Copy changes:**
- Button label: `Sign in` (was "AUTHENTICATE"). Register mode: `Create account`.
- Header of form panel: `Sign in to continue` (kept — this is fine).

**Do not** re-render the whole page on toggle — just swap the submit
function and button label.

### 4.2 Registry (`app/cases/page.js`)

Screen title (page-top): `Investigations` (was "INVESTIGATION REGISTRY").
Subtitle beneath: `Your active and completed profiling cases.`

**Top bar** (always visible):
- Left: `VERTEX.` logo → clickable, goes to `/cases`.
- Right: username chip, `Sign out` link, `<Button variant="primary">+ New investigation</Button>`.

**Stats strip** — only render when there is at least one case:
- Three big-numbers cards inside `<GlassPanel className="p-4">`, `grid-cols-3`:
  - `{total}` Total investigations
  - `{running}` In progress (cyan + pulse if > 0)
  - `{complete}` Complete
- If `cases.length === 0`, do not render this strip at all.

**Filter bar:**
- Single `<Input placeholder="Filter by case name..." />` full width.

**Case grid:**
- `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`.
- Each card is a `<GlassPanel className="p-4 cursor-pointer hover:border-cyan-400">`:
  - Top row: case title (font-semibold, base) + `<StatusPill>` right-aligned.
  - Second row: `ID: #{case_id.slice(0,8)}` (mono, xs, muted).
  - Third row: `Discovered: {account_count} accounts` (small, slate-300).
  - Bottom row: `{created_at}` (mono xs muted) on the left, `Open case →`
    button (secondary variant, small) on the right.
- Whole card is clickable, navigates to `/cases/{id}`.

**Empty state** (no cases):
- Centered `<EmptyState>`:
  - icon: 🗂️ (or a subtle cyan svg icon)
  - title: `No investigations yet`
  - description: `Open a new case to begin.`
- Below description: `<Button variant="primary">+ New investigation</Button>`.

**Kill from the current version:**
- The "0 CASES · 0 RUNNING · 0 COMPLETE" strip when everything is zero.
- The word "registry" and any mention of "operations".

### 4.3 New Investigation modal (triggered from Registry)

**Overlay:** `fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4`.

**Modal:** `<GlassPanel className="w-full max-w-lg p-6">`, `max-h-[90vh]
overflow-y-auto`, `✕` close in top-right.

**Content:**
- Header: `New investigation` (h2, font-semibold, base+2). Sub-line:
  `Enter one or more identifiers to profile a subject.` (xs, muted).
- Field 1: `<Label>CASE TITLE</Label>` + `<Input placeholder="e.g. Sushil Kumar - phishing case #24">`
- Field 2: `<Label>REGION</Label>` + native `<select>`: options `India (Indian
  + Global platforms)` (default) and `Global`. Styled same as `<Input>`.
- Field 3: `<Label>IDENTIFIERS</Label>`. Below the label, a compact row:
  - `<select>` for type (Name, Email, Phone, Username, UPI, Face URL) — 30%
  - `<Input placeholder="e.g. Arjun Mehta">` — 60%
  - `<Button variant="secondary">Add</Button>` — 10%
  - Below the row: list of added identifiers as chips (`<PivotPill>`-style),
    each with an `×` to remove. Format: `[NAME] Arjun Mehta ×`.
- Field 4: Checkbox `Subject is a minor` — next to it a `<Tooltip>` `(?)`.
  Tooltip content: `Enables POCSO Act protections. Identifying details will
  be redacted in the evidence report.`
- Footer buttons right-aligned: `<Button variant="secondary">Cancel</Button>`
  `<Button variant="primary">Start investigation</Button>`.

**Behavior:**
- `Start investigation` calls `api.createCase(title, seeds, minor_involved)`
  then navigates to `/cases/{case_id}`.
- Disable the button and show `Starting...` while the request is inflight.

**Kill from current version:**
- "INITIATE INVESTIGATION" title. "OPERATION TITLE". "SEEDS" as a section label.
  All jargon.

### 4.4 Results dashboard (`app/cases/[id]/page.js`) — THE BIG ONE

This is the page that decides whether the judge trusts the tool. It gets the
most detailed spec.

#### 4.4.1 Top verdict band (full width, always visible)

Inside a `<GlassPanel className="p-4">`:

- Row 1:
  - Left: `← All investigations` link.
  - Center-left: case title (font-semibold text-lg), then case ID `#{case_id.slice(0,8)}` in muted mono.
  - Center-right: `<StatusPill status={status}>` — "In progress" during
    polling, "Complete" on success, "Error" on failure.
  - Right: `<Button variant="success" onClick={downloadReport}>Download
    Evidence Report (BSA-63)</Button>` — disabled if `status !== "complete"`.
- Row 2 (the **verdict line** — the single most important row on the page):
  - Read `clusters` and `entities`. Compute:
    - `strong = clusters.filter(c => c.tier === "HIGH" && c.entity_ids.length >= 2).length`
    - `possible = clusters.filter(c => c.tier === "MEDIUM" && c.entity_ids.length >= 2).length`
    - `total = entities.length`
  - Render (Outfit, semibold, base):
    - `Found {strong} strong {strong===1?"match":"matches"} · {possible} possible · {total} accounts discovered`
  - Numbers get colored: strong in emerald, possible in amber, total in slate-200.
  - Sub-line beneath, xs muted mono: `Audit chain verified · SHA-256 · BSA §63 compliant`
- Row 3 (small stats strip, `grid-cols-4 gap-3 pt-3 border-t border-slate-800`):
  - `{total}` Accounts found
  - `{strong}` Strong matches
  - `{possible}` Possible matches
  - `{clusters.length}` Identity groups

**Kill:**
- "HIGH LINKS", "CLUSTERS", "TOP SCORE", "CHAIN" — all the jargon labels.
- "VERIFIED ✓" as a stat pretending to be a number.

#### 4.4.2 Main body — 3-column layout at `lg`

`grid-cols-1 lg:grid-cols-12 gap-4`.

- **Left (`lg:col-span-3`): Identity list** (§4.4.3)
- **Center (`lg:col-span-6`): Main view with tabs** (§4.4.4)
- **Right (`lg:col-span-3`): Same-person analysis** (§4.4.5)

#### 4.4.3 Left — Identity list

Inside a `<GlassPanel className="p-4 max-h-[720px] overflow-y-auto">`.

Header: mono uppercase xs `DISCOVERED ACCOUNTS ({total})`, then a sub-line
`Click any account to inspect.` (xs muted).

Sections (in this order), each with a mono uppercase section header + count:

1. **Strong matches ({N})** — emerald text-[11px] header. Members: all
   entities belonging to clusters where `tier === "HIGH"` AND
   `entity_ids.length >= 2`. Sub-grouped by cluster: each cluster gets a
   nested header (small, slate-300, `Identity group A · {n} accounts`) and
   its members below.
2. **Possible matches ({N})** — amber. Same grouping, `tier === "MEDIUM"`,
   `entity_ids.length >= 2`.
3. **Not linked ({N})** — crimson. All singleton clusters and everything else.
   Collapsed by default UNLESS `strong + possible === 0` (in which case
   auto-expand — this preserves the existing §16.5 fix).

Each entity is a `<AccountCard>`. Selecting a card sets a `selectedEntityId`
in state and populates the right-hand panel.

Cluster group headers are clickable to select the *whole* cluster (highlights
all its members in the graph and populates the analysis panel with the
cluster explanation).

#### 4.4.4 Center — tabbed main view

Tabs (mono uppercase, letter-spaced, tab bar `border-b border-slate-800`):
1. **Summary** (default) — §4.4.4.1
2. **Network** — §4.4.4.2
3. **Timeline** — §4.4.4.3 (hidden when no data)
4. **Writing & Activity** — §4.4.4.4 (hidden when forensics is empty)

Active tab: `text-cyan-400 border-b-2 border-cyan-400`.

##### 4.4.4.1 Summary tab (default)

This is the **matrix pattern** — the single strongest UX idea from the friend's
prototype. Do not remove it. Structure:

Inside the tab, `grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3`, four small
`<GlassPanel className="p-4">` cards:

1. **Profile pictures** — icon 🖼️ + count in top-right chip. Body: horizontal
   scroll of `photo_url`s (extract from `metadata.photo_url` across all
   entities, dedupe by URL). Each photo `w-14 h-14 rounded-md` + platform code
   overlaid bottom-left. Empty state: "No profile pictures found."
2. **Platforms** — icon 🌐 + count. Body: list of platforms with counts.
   Group `entities` by `platform`, sort by count desc, top 10 shown. Each row:
   `<platform icon> Platform name  <count chip>`.
3. **Names & aliases** — icon 👤 + count. Body: unique
   `metadata.fullname` values across entities. Each row shows the name and
   an "ALIAS" chip (`text-[10px]` uppercase, cyan). Deduplicate normalized.
4. **Locations & context** — icon 📍. Body: unique
   `metadata.location`, employer candidates, city candidates. Small chips.

Beneath the 4 cards: **Evidence quick-links** — a `<GlassPanel className="p-4">`
that shows a horizontal wrap of `<PivotPill>`s: one for each unique signal
type that fired across all clusters. Format: `📧 Shared email (3 groups)`,
`📞 Same phone (1 group)`. Click a pill to filter the identity list to
clusters where that signal fired.

##### 4.4.4.2 Network tab

The sigma.js / vis-network graph, contained in a `<GlassPanel className="p-2
h-[560px]">` with `#network-graph` inside.

Node colors: apply the semantic mapping from §1.7. HIGH = emerald,
MEDIUM = amber, LOW/REJECT = crimson, selected = cyan border.

Edge color: translucent cyan `rgba(0, 242, 254, 0.4)`; highlight edges on
selected node in emerald.

**Fix the hairball:** when `total > 30`, initially render only the entities
that belong to clusters (multi-member OR singleton where tier != REJECT).
Add a small "Show all {total} nodes" toggle top-right of the graph card.
Default off. This is the difference between "hairball" and "readable network".

Legend under the graph (mono, xs): emerald = strong · amber = possible ·
crimson = not linked · cyan = selected.

##### 4.4.4.3 Timeline tab

Vis-timeline strip. If `forensics.activity_hours` is empty AND no entity
has `posting_hours`, HIDE the tab entirely. Do not render an "insufficient
temporal data" message anywhere; a hidden tab is a better experience.

##### 4.4.4.4 Writing & Activity tab

Only render if `forensics` has at least one populated field. If every field
is empty/missing, hide the tab. Do NOT render dashes in place of missing
values.

Content, when data exists:
- Tone strip: colored bar with label. Positive → emerald; Neutral → slate;
  Negative → crimson. **Do not show the raw numeric score** unless it's
  meaningful. Show `Tone: Positive` or `Tone: Positive (high confidence)`.
- Active hours: small bar chart of `activity_hours` (24 bars).
- Top keywords: chips, max 8 shown, then "+N more" behind a click.
- Top hashtags: chips, max 8 shown, then "+N more" behind a click.
- Engagement: only show fields that are populated.

Section header: `Writing & Activity Patterns` (was "LINGUISTIC & BEHAVIOURAL
FORENSICS" — kill that).

#### 4.4.5 Right — Same-person analysis

Inside a `<GlassPanel className="p-4 max-h-[720px] overflow-y-auto sticky top-4">`.

Header: mono uppercase xs `SAME-PERSON ANALYSIS`.

Body has two states:

**State A — nothing selected:**
`<EmptyState>` with icon 🔍, title `Select an account or group`, description
`Click any item on the left to see why we linked (or didn't link) these
accounts.`

**State B — cluster selected:**
- Top: cluster title (`Identity group A`) + `<ConfidenceBadge tier>`.
- One-sentence explanation from `cluster.explanation` — this is the plain
  English the LLM (or fallback template) produced. Keep it prominent.
- Below: `Matching evidence` (mono uppercase xs section header). List each
  fired signal as a row: `<icon> <human label>` on the left, `+{points}`
  on the right (small mono muted). Human labels come from §6 (SIGNAL_LABELS).
- Below: `Total score: {confidence_score}/100` (mono, small, muted).
- Bottom: `<details>` (native `<details>` element) titled `Technical details`.
  When expanded, shows the raw signal names, weights, and — for each
  member entity — the `sha256`. Default closed. This is where the trust
  proof lives without cluttering the primary view.

**State C — single account selected (not part of a multi-member cluster):**
- Show the account metadata: name, bio, platform, URL, photo.
- If it has a non-zero `confidence` field, show `<ConfidenceBadge>`.
- Show a note: `Not linked to other accounts. VERTEX refused to link because
  fewer than 2 corroborating signals were found.` (This surfaces your
  red-herring discipline as a feature, not silence.)

#### 4.4.6 Running-state UX

While `status ∈ {"pending","running"}`:
- Verdict band shows `<StatusPill status="running">` with pulse dot and
  label "In progress".
- Verdict line shows current count of entities streamed so far:
  `Discovering accounts... {total} found so far`.
- The identity list on the left populates as accounts stream in.
- Report button disabled with tooltip "Available when investigation completes".
- Center tabs are usable but the graph may re-render on each poll — that's
  fine.

---

## 5. Microcopy Discipline

**This is the change that most builds trust with a CID audience. Every string
in the app gets a pass.** Table of what to replace and what to keep.

### 5.1 Global vocabulary swap

| Currently says | Change to |
|---|---|
| INVESTIGATION REGISTRY | Investigations |
| INITIATE INVESTIGATION | New investigation |
| OPERATION TITLE | Case title |
| SEEDS | Identifiers |
| DEPLOY / RECON / RECONNAISSANCE | (never use — say "Start", "Investigation") |
| SUSPECT | Subject |
| OFFICER / BADGE | Username |
| AGENTS ONLINE | Data sources connected |
| CLUSTER | Identity group |
| ENTITY | Account (or "trace" for non-account items) |
| SIGNAL | Matching evidence |
| CLUSTER ANALYSIS | Same-person analysis |
| HIGH LINKS | Strong matches |
| TOP SCORE | Best match confidence |
| CHAIN (as stat) | Audit chain verified |
| RED HERRING | Not linked (with tooltip "Insufficient evidence to link") |
| CONFIRMED (on account cards) | Linked |
| POSSIBLE (on account cards) | Possible link |
| LINGUISTIC & BEHAVIOURAL FORENSICS | Writing & Activity Patterns |
| INSUFFICIENT TEMPORAL DATA | (hide the section instead) |
| CRYPTO-VERIFIED INTACT | Audit chain verified |
| SYSTEM v2.X // LIVE RECON | (delete — no version chip in top bar) |
| 15 RECON AGENTS ONLINE | (delete — never invent capability) |

### 5.2 Casing rules

- **Section labels** (headers of panels, e.g. `DISCOVERED ACCOUNTS`,
  `SAME-PERSON ANALYSIS`): mono, uppercase, letter-spaced, xs. This *is* the
  tool feel — keep.
- **Everything else** (buttons, body text, cluster explanations, tooltips):
  sentence case. Never all-caps.
- **Field labels above inputs**: mono uppercase xs — OK. This visually
  distinguishes them.

### 5.3 Numbers

- Never show a decimal beyond 2 places in the UI. `0.988` → `0.99` or better,
  `high confidence`.
- Never show percentages with more than 1 decimal.
- Confidence 0–100 stays whole numbers.
- Small counts get commas or spelled out ("1 match", "2 matches", not "1 hits").

### 5.4 Empty states

Every panel that could be empty must have an `<EmptyState>` — never a bare
dash or `null`. See §3.8.

If a whole tab is empty (Timeline with no data, Writing & Activity with no
forensics), **hide the tab**. Don't render an empty view.

### 5.5 Do not invent

- No fake stat like "15 agents". No fake version like "v2.6". No trust badges
  the backend didn't actually produce.
- Every stat on screen must correspond to a real backend value.

---

## 6. SIGNAL_LABELS — the plain-English mapping (paste this constant)

Create `frontend/lib/signalLabels.js` with the following exact content. Every
place the frontend displays a signal name, it must go through `labelFor(name)`
from this module. This is your one-shot mechanical fix that makes signal
displays readable everywhere.

```js
// frontend/lib/signalLabels.js
// Plain-English labels for every correlation signal produced by the backend.
// Backed by SIGNAL_WEIGHTS in backend/correlation/correlation_engine.py.
// Icons are optional visual glyphs; use them in the analysis panel.

export const SIGNAL_LABELS = {
  // Hard anchors (strongest evidence)
  exact_phone_match:      { label: "Same phone number",        icon: "📞", tier: "hard" },
  exact_email_match:      { label: "Same email address",       icon: "📧", tier: "hard" },
  exact_upi_match:        { label: "Same UPI ID",              icon: "🏦", tier: "hard" },
  profile_photo_phash:    { label: "Matching profile photo",   icon: "🖼️", tier: "hard" },
  face_match:             { label: "Same face (biometric)",    icon: "🧑", tier: "hard" },
  bio_url_match:          { label: "Bio links match",          icon: "🔗", tier: "hard" },
  breach_co_occurrence:   { label: "Appears in same breaches", icon: "🛡️", tier: "hard" },

  // Identity signals
  username_exact_match:    { label: "Username: exact match",         icon: "🆔", tier: "identity" },
  username_substring_match:{ label: "Username: partial match",       icon: "🆔", tier: "identity" },
  username_fuzzy_match:    { label: "Username: similar spelling",    icon: "🆔", tier: "identity" },
  exact_name_match:        { label: "Same full name",                icon: "👤", tier: "identity" },
  fuzzy_name_match:        { label: "Similar name spelling",         icon: "👤", tier: "identity" },

  // Context / corroborating signals
  location_overlap:      { label: "Same declared location",     icon: "📍", tier: "context" },
  city_match:            { label: "Same city (in bio)",         icon: "🏙️", tier: "context" },
  employer_overlap:      { label: "Same employer or school",    icon: "🏢", tier: "context" },
  posting_hours_overlap: { label: "Active in same hours",       icon: "🕒", tier: "context" },
  stylometry_cosine:     { label: "Similar writing style",      icon: "✍️", tier: "context" },
  bio_keyword_overlap:   { label: "Shared bio keywords",        icon: "🏷️", tier: "context" },
  mutual_connections:    { label: "Shared connections",         icon: "👥", tier: "context" },
  reciprocal_mention:    { label: "Mention each other",         icon: "↔️", tier: "context" },
};

export function labelFor(signalName) {
  return SIGNAL_LABELS[signalName]?.label
    ?? signalName.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export function iconFor(signalName) {
  return SIGNAL_LABELS[signalName]?.icon ?? "•";
}

export function tierFor(signalName) {
  return SIGNAL_LABELS[signalName]?.tier ?? "context";
}
```

**Use `labelFor()` in:**
- The same-person analysis panel's "Matching evidence" list
- The evidence quick-links pills on the Summary tab
- Anywhere `cluster.signals` keys are rendered

---

## 7. Verification Checklist

After each task, verify:

### After foundation (§2, §3)
- [ ] `npm run build` still passes
- [ ] Fonts load (Outfit and JetBrains Mono visible in devtools Network tab)
- [ ] `.glass-panel`, `.pulse-dot`, CSS vars all resolve when inspected
- [ ] The glow + grid background layers render without breaking layout
- [ ] No console errors on any page

### After login rebuild
- [ ] Can sign in with existing admin/vertex2026 credentials
- [ ] Register mode creates a new user and auto-signs in
- [ ] JWT written to `localStorage["vertex_token"]` (unchanged)
- [ ] Login errors show human message (not raw fetch error)

### After registry rebuild
- [ ] Empty state renders when zero cases
- [ ] Cases stream in when created
- [ ] "New investigation" modal opens, submits, navigates to `/cases/{id}`
- [ ] Filter input filters case list client-side

### After results dashboard rebuild
- [ ] Polling still refetches every 1500ms while running
- [ ] Verdict line numbers match: strong = count of HIGH clusters with >=2
      members, possible = count of MEDIUM clusters with >=2 members, total =
      entities.length
- [ ] Selecting an entity on the left highlights it on the graph and populates
      the analysis panel
- [ ] Selecting a cluster header populates the analysis panel with the
      cluster's explanation and signals
- [ ] The Summary matrix populates from entity metadata (photos, platforms,
      names, locations)
- [ ] The Network tab renders the graph; the "Show all N nodes" toggle works
- [ ] The Timeline tab is hidden when no timeline data exists
- [ ] The Writing & Activity tab is hidden when forensics is empty
- [ ] The "Download Evidence Report" button downloads a PDF (test with a
      completed case). Auth header must be attached.
- [ ] SIGNAL_LABELS mapping is used everywhere a signal name is displayed —
      no raw `exact_phone_match` visible in the UI

### Final end-to-end
- [ ] Fresh browser: register → new investigation with a real seed → wait
      through running → open a cluster → download the PDF. All in one flow,
      no errors.
- [ ] Run in `DATA_MODE=mock` — verify the demo mock case still renders correctly
- [ ] Test on 1440×900 laptop (typical demo projector). No horizontal scroll,
      no cramped panels.

### Repository safety re-check (do this BEFORE handing back to the user)
- [ ] `git status` shows changes ONLY under `frontend/`. No `backend/`,
      `tests/`, `scripts/`, `.env*`, `.md`, or `requirements.txt` in the diff.
- [ ] No `git add`, `git commit`, `git push`, or any other git plumbing
      command was run at any point during this session.
- [ ] `git branch --show-current` still shows the same branch it did at
      session start. No branches were created, switched, or deleted.
- [ ] `frontend/package.json` diff is empty (no new dependencies added).
- [ ] `.pre-redesign` backup files exist for every modified file and are NOT
      staged.
- [ ] Backend was never started or restarted by any command run in this
      session.
- [ ] All 101 backend tests would still pass — because you did not touch
      `backend/` or `tests/`.

---

## 8. Order of execution

Do the work in this order. Each step is independently testable.

1. **Foundation** — §2 (globals.css, layout.js, tailwind.config.js). Verify
   fonts + background layers work by loading any existing page.
2. **Component library** — §3 (all ui/ components). Build them, then in
   isolation write one dummy page importing all of them just to eyeball.
3. **SIGNAL_LABELS constant** — §6 (`lib/signalLabels.js`). No visible change
   yet.
4. **Login rebuild** — §4.1.
5. **Registry rebuild** — §4.2 + New Investigation modal §4.3.
6. **Results dashboard rebuild** — §4.4. This is the big one. Do it in
   sub-order:
   - 6a. Top verdict band (§4.4.1)
   - 6b. Left identity list with grouping (§4.4.3)
   - 6c. Right same-person analysis panel (§4.4.5)
   - 6d. Center Summary tab (§4.4.4.1) — matrix
   - 6e. Center Network tab (§4.4.4.2) — graph with sane defaults
   - 6f. Center Timeline + Writing & Activity tabs (§4.4.4.3, §4.4.4.4)
7. **Microcopy pass** — §5. Grep the whole `frontend/` tree for the strings
   in the vocabulary swap table and replace them everywhere they still appear.
8. **End-to-end verification** — §7 final section.

**If you run out of time, stop at step 6c.** A dashboard with the new verdict
band, grouped left panel, and same-person analysis on the right (Summary +
Network tabs) already delivers 80% of the redesign's value. Timeline and
Writing tabs can be hidden without loss.

---

## 9. Design principles to hold onto while you build

If a decision comes up that this spec doesn't cover, decide by these
principles, in order:

1. **Answer first.** The user should see the *what* (are these accounts the
   same person? yes/no/maybe) before the *how* (which signals fired, at
   what weights).
2. **Words over pixels.** A crisp label saves more confusion than a prettier
   card. When in doubt, sharpen the copy.
3. **Restraint reads as trust.** No fake stats, no theatrical language, no
   invented capabilities. Every claim on screen must correspond to a real
   backend value.
4. **Progressive disclosure.** Technical details (SHA-256, raw signal weights,
   platform-specific metadata) live behind a "Technical details" toggle,
   not on the primary view. They exist for the judge who wants to verify;
   they distract the constable who wants to act.
5. **Hide, don't dash.** Empty fields get hidden, not filled with `—`. A
   panel of dashes reads as broken.
6. **One semantic color per meaning, forever.** Emerald = strong. Amber =
   possible. Crimson = not linked/error. Cyan = active/selected. Break this
   once and the whole visual language falls apart.

---

*End of spec. Execute in the order given in §8.*
