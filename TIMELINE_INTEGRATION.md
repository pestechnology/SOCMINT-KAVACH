# Timeline Feature Integration — Full Journey, Issues & Final Solution

Everything about porting the account-lifeline **Timeline** feature from a reference working
copy into this VERTEX repo: the goal, the discovery process, every problem/decision, and
the exact final wiring that works. Written to be read cold.

> Repo: `/Users/dhanush/Desktop/vertex_main` (clone of `github.com/dhanush-sr/VERTEX`, `main`).
> Reference source: `/Users/dhanush/CLAUDE CODE SUNDAY/VERTEX`.
> **Nothing pushed.** All changes are local.

---

## 1. Goal

Bring the **Timeline** feature (an account-wise lifeline graph — each discovered account's
creation / activity / last-seen / breach events plotted on one shared time axis) from a
reference working copy into the freshly cloned `main`, **without breaking any existing
feature** and without dragging along the rest of the reference's divergence.

---

## 2. Source material & a key trap

The reference existed as **three** near-identical folders in the home dir:
- `/Users/dhanush/CLAUDE CODE SUNDAY` ← **used this one** (user instruction: not the copies)
- `/Users/dhanush/CLAUDE CODE SUNDAY copy`
- `/Users/dhanush/CLAUDE CODE SUNDAY copy 2`

**Verified they were safe to treat as one:** a recursive diff of the three showed they
differed **only in build artifacts** (`frontend/.next/**` webpack cache, `cidecode.db`,
`*.session`, a few scratch `.txt` files) — the **source trees were identical**. So the
choice of folder didn't matter for code; used `CLAUDE CODE SUNDAY` as instructed.

---

## 3. Discovery process (how the feature surface was found)

1. **Literal search for "timeline" was misleading.** Grepping `timeline` across source hit
   almost nothing meaningful — the feature is named by component, not by the word. Early
   counts were inflated by `.next` build files (excluded once `.next` was filtered out).
2. **Real feature files found** in the reference frontend:
   - `frontend/lib/timeline.js`
   - `frontend/components/ui/TimelineModal.jsx`
   - `frontend/components/ui/TimelineGraph.jsx`
   - referenced from `frontend/app/cases/[id]/page.js`
3. **Compared reference vs. cloned `main`** to see what was genuinely new:
   - `TimelineModal.jsx`, `TimelineGraph.jsx`, `lib/timeline.js` → **absent in `main`** (new).
   - `Timeline.js` → **present in both but different** (this is a *different*, older component).

---

## 4. Two critical findings that shaped the approach

### 4.1 The reference is a DIVERGENT, OLDER branch — no wholesale copy
Diffing the backend/frontend source trees showed **`main` is newer in many places** than the
reference. `main` has files the reference lacks, e.g.:
`backend/agentic_browser/smart.py`, `extractor.py`, `intelbase.py`, `supadata.py`,
`backend/analysis/case_chat.py`, `next_actions.py`, `backend/ingestion/derive.py`,
`socid_enrich.py`, `gravatar_scraper.py`, plus frontend `ReiterateBar`, `ThemeToggle`, and a
rewritten `PlatformLogo`. So the reference could **not** be copied over `main` — the timeline
had to be **surgically extracted** and grafted onto the newer `main`.

### 4.2 There are TWO different "Timeline" things — don't confuse them
- **`Timeline.js`** — an existing case-room **tab** (a posting-hours chart). Already in
  `main`, gated on `hasPostingHours`. **Left completely untouched.**
- **`TimelineModal` (+ `TimelineGraph` + `lib/timeline.js`)** — the **new feature**: a modal
  opened by a header button, showing the account-lifeline swimlane graph. **This is what was
  ported.**

Mixing these up would have either duplicated or broken the existing tab. They were kept
strictly separate.

---

## 5. Dependency analysis (what the new files need)

`TimelineModal.jsx` / `TimelineGraph.jsx` import:
- `@/lib/timeline` — **new** (copied in).
- `./PlatformLogo` — **exists in `main`**, called with `platform/width/height/className`.
- `react-dom` `createPortal` (tooltip) — available.
- CSS classes `custom-scrollbar`, `animate-in fade-in duration-200`.

**Decision points resolved:**
- **`PlatformLogo`:** `main` has its **own newer** implementation (alias map, TLD-strip,
  error-count fallback). The reference's version was a *different, older* one. The timeline
  works fine against `main`'s version (same props), so **`main`'s `PlatformLogo` was NOT
  touched** — avoids a cosmetic regression across the whole app.
- **CSS classes:** `custom-scrollbar` / `animate-in` are **not defined in either** repo and
  there's no `tailwindcss-animate` plugin — they were **graceful no-ops** in the reference
  too (the modal worked without them). So no missing CSS dependency; nothing added.
- **Backend:** none. The feature is **purely client-side** — it builds the timeline from the
  case's existing `entities` + `clusters` (already in scope at `page.js:104-105`). No new API,
  no scraper, no DB change.
- **npm packages:** none. `package.json` deps were identical (only a `-p 3000` port flag
  differed).

---

## 6. What the feature actually does (for future readers)

- **`lib/timeline.js`** — the data model. Turns raw entities (+ their cluster confidence
  tier) into per-account "lifelines" built **only from real, source-provided dates**:
  account creation (`created_at` / `created_utc`), activity (`recent_posts[].posted_at`),
  last-seen (Wayback `archived_at`), breach exposure (`breach_details[].date`). Accounts with
  no genuine date are surfaced honestly as "undated", never stamped with a fake time. Exposes
  helpers: `buildTimeline`, `groupByTier`, `personSummary`, `creationBins`, `yearTicks`,
  date parsers/formatters, and the `TIER_STYLE` palette.
- **`TimelineModal.jsx`** — the modal shell with two coordinated views over the same model:
  **Graph** (swimlanes) and **By account** (cards with per-event chronology). Has a
  hide-breaches toggle.
- **`TimelineGraph.jsx`** — the swimlane graph: person-summary stat pills, an account-creation
  density strip, a shared year axis, confidence-banded lanes (Strong / Possible / Not linked),
  a separate "Data exposure" breach band, and a `createPortal` tooltip anchored to each dot.
  Positioned purely by % of the time domain (fully responsive).

---

## 7. Issues faced & what was tried

The timeline port itself was clean (the hard part was the *analysis*, not the edit). The
issues were mostly in the surrounding frontend runtime:

### 7.1 The three-folder trap
- **Risk:** picking the wrong reference copy, or assuming they differed.
- **Handled:** diffed all three, proved source-identical, used `CLAUDE CODE SUNDAY`.

### 7.2 "timeline" keyword search was noise
- Literal grep found little in source and lots in `.next`. **Handled** by excluding
  `node_modules` / `.next` and searching by component name instead.

### 7.3 Divergent branch → could not copy wholesale (see §4.1)
- **Handled** by extracting only the 3 files + minimal wiring, preserving all of `main`'s
  newer features.

### 7.4 No `node_modules` in the fresh clone
- Build check needed deps. Ran `npm install` (deterministic via the lockfile) before building.

### 7.5 Next.js **workspace-root** warning
- After the port, `npm run dev` warned it inferred the workspace root from a stray
  `/Users/dhanush/package-lock.json` (an **unrelated home-dir project** — axios/express/vite,
  left untouched).
- **Fix:** `frontend/next.config.mjs` → added `turbopack.root` + `outputFileTracingRoot =
  import.meta.dirname` to pin the root to the frontend folder.
- Also discovered here that Next was **16.2.10**, not the repo's pinned 14.2.15 (the user had
  upgraded 14→16; Next 16 runs Turbopack by default).

### 7.6 Turbopack **panic** (corrupted cache)
- `thread 'tokio-runtime-worker' panicked … turbo-tasks-backend … Every task must have a task
  type` — a Turbopack internal panic from a **corrupted `.next` persistent cache** (a known
  Next-16 instability), **not** from the timeline code.
- **Fix:** stop the dev server, `rm -rf frontend/.next`, restart `npm run dev` (cache
  regenerates). Confirmed this does **not** affect the backend or any running investigation
  (separate process on port 8000).

---

## 8. Final implementation

### 8.1 New files (copied byte-for-byte from the reference)
- `frontend/lib/timeline.js`
- `frontend/components/ui/TimelineModal.jsx`
- `frontend/components/ui/TimelineGraph.jsx`

### 8.2 Wiring — 4 additive edits to `frontend/app/cases/[id]/page.js`
1. Import: `import TimelineModal from "@/components/ui/TimelineModal";`
2. State: `const [showTimelineModal, setShowTimelineModal] = useState(false);`
3. Header button (next to "Briefing"): a 🕒 **Timeline** `<button>` that
   `setShowTimelineModal(true)`.
4. Render (next to `<ExecutiveSummaryModal>`):
   ```jsx
   <TimelineModal
     isOpen={showTimelineModal}
     onClose={() => setShowTimelineModal(false)}
     entities={entities}
     clusters={clusters}
   />
   ```

### 8.3 Config edit (frontend runtime, from §7.5)
- `frontend/next.config.mjs` → `turbopack.root` + `outputFileTracingRoot`.

### 8.4 Explicitly NOT changed (to avoid breakage)
- `main`'s existing `Timeline.js` **tab** and its `hasPostingHours` gating.
- `main`'s newer `PlatformLogo.jsx`.
- Any backend file (the feature is client-side only).

---

## 9. Verification
- `npm install` → clean.
- `npm run build` → **✓ Compiled successfully**, `/cases/[id]` route builds, **no** timeline
  warnings.
- `git status` showed exactly the intended changes; `.env` confirmed gitignored.
- The 🕒 Timeline button appears in the case room and opens the modal; it reads the case's
  existing `entities` + `clusters`, so breach events (incl. from the NewLeaks source) also
  render on the axis via the shared `breaches` field.

---

## 10. Current status & notes
- **WORKING.** Additive, client-side only, no existing feature touched.
- The 🕒 Timeline **button is always shown** (matches the reference). If you'd prefer it
  hidden when there's nothing datable to plot, a guard can be added.
- Runtime reminders: `npm run dev` hot-reloads UI changes; if Turbopack panics again,
  `rm -rf frontend/.next` and restart. Restarting the frontend never affects a running
  investigation (backend is a separate process).
