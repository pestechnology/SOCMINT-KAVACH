/* app/cases/page.js
   REDESIGN §4.2 + §4.3 — "Investigations" registry (glass card grid, stats strip,
   plain-English copy) + "New investigation" modal. Killed: "REGISTRY", "OPERATION
   TITLE", "SEEDS", "INITIATE INVESTIGATION", the all-zero stats strip.
   PRESERVED: auth guard, api.listCases().cases, 401->login, signOut, vertex_user,
   and api.createCase(title, seeds, country_filter) -> res.case_id (§1.1, §0.4).
   ADDED: "Agentic web" mode — an AI agent browses a chosen no-API OSINT site, extracts
   real data (never fabricated), and the result flows through the correlation pipeline. */
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "@/lib/api";
import { notify, permission, requestPermission } from "@/lib/notify";
import GlassPanel from "@/components/ui/GlassPanel";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Label from "@/components/ui/Label";
import StatusPill from "@/components/ui/StatusPill";
import EmptyState from "@/components/ui/EmptyState";
import PivotPill from "@/components/ui/PivotPill";
import Tooltip from "@/components/ui/Tooltip";
import ThemeToggle from "@/components/ui/ThemeToggle";

// §4.3 identifier types — Name, Email, Phone, Username, UPI, Face URL (spec order).
const SEED_TYPES = [
  { value: "name", label: "Name", placeholder: "e.g. Arjun Mehta" },
  { value: "email", label: "Email", placeholder: "e.g. subject@mail.com" },
  { value: "phone", label: "Phone", placeholder: "e.g. +91 98765 43210" },
  { value: "username", label: "Username", placeholder: "e.g. ghost_rider99" },
  { value: "upi", label: "UPI", placeholder: "e.g. subject@oksbi" },
  // Profile URL: the backend's URLScraper pulls the handle, the platform's own id
  // (Facebook numeric / YouTube channel / X numeric) and any name in the URL slug,
  // then cascades those back through the normal pipeline. See url_scraper.py.
  { value: "url", label: "Profile URL", placeholder: "e.g. https://instagram.com/ghost_rider99" },
  { value: "face", label: "Face URL", placeholder: "e.g. https://…/photo.jpg" },
];

// Region maps onto the backend's country_filter (preserved from pre-redesign).
// Both modes include worldwide platforms (Instagram, GitHub, ...) on purpose — a
// stricter "India platforms only" filter was tried before and silently dropped the
// investigator's own literal search target for having a foreign-looking location
// (see country_filter.py's docstring). "India" here means noise-reduced (foreign
// regional networks like VK/Weibo/Naver excluded); "Global" means fully unfiltered.
const REGIONS = [
  { value: "INDIA", label: "India (focused — excludes foreign-regional noise)" },
  { value: "ALL", label: "Global (unfiltered)" },
];

// Case-level triage priority — a single fixed-color classification per case (distinct
// from the per-account red/orange/yellow annotation flags used inside a case's results).
// Click a dot on a card to set/clear it; click a chip in the bar to filter the grid to
// just that bucket. Order is severity-descending, matching how they read left-to-right.
const PRIORITY = [
  { value: "red", label: "High priority", dot: "#ff3366" },
  { value: "orange", label: "Medium priority", dot: "#ffb703" },
  { value: "green", label: "Normal priority", dot: "#00ff88" },
];
const PRIORITY_BY_VALUE = Object.fromEntries(PRIORITY.map((p) => [p.value, p]));

const SELECT_CLS =
  "w-full rounded-lg bg-slate-900/80 border border-slate-700 px-3 py-2 " +
  "text-sm text-slate-100 outline-none transition-colors duration-200 " +
  "focus:border-cyan-400 cursor-pointer";

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function Cases() {
  const router = useRouter();
  const [cases, setCases] = useState([]);
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [username, setUsername] = useState("");
  // Collections (named folders/watchlists) + membership map {case_id: [collection_id]}.
  const [collections, setCollections] = useState([]);
  const [memberships, setMemberships] = useState({});
  const [activeCollection, setActiveCollection] = useState("all"); // "all" | "none" | id
  const [pickerCase, setPickerCase] = useState(null); // case_id whose folder picker is open
  // Case triage priority: "all" | "unflagged" | "red" | "orange" | "green".
  const [activePriority, setActivePriority] = useState("all");
  // Completion notifications (bulk + single runs).
  const [banner, setBanner] = useState("");     // in-page fallback when desktop toasts are off
  const statusRef = useRef(new Map());          // case_id -> last seen status
  const seededRef = useRef(false);              // first load only records, never notifies

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    try { setUsername(localStorage.getItem("vertex_user") || "investigator"); } catch (_) {}
    refresh();
    refreshCollections();
  }, [router]);

  // Live refresh while anything is running. /cases already returns each case's status,
  // so completion needs no new endpoint — poll, diff, announce. The interval clears
  // itself once nothing is in flight, so an idle tab does no work.
  useEffect(() => {
    const busy = cases.some((c) => c.status === "running" || c.status === "pending");
    if (!busy) return;
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [cases]);

  function announceCompletions(list) {
    const prev = statusRef.current;
    const done = seededRef.current
      ? list.filter((c) => c.status === "complete" && prev.get(c.case_id)
                           && prev.get(c.case_id) !== "complete")
      : [];
    statusRef.current = new Map(list.map((c) => [c.case_id, c.status]));
    seededRef.current = true;
    if (!done.length) return;

    const shown = done.every((c) =>
      notify("Investigation complete", {
        body: `${c.title} \u00b7 ${c.account_count ?? 0} accounts`,
        tag: c.case_id,
        onClick: () => router.push(`/cases/${c.case_id}`),
      })
    );
    if (!shown) {
      setBanner(done.length === 1
        ? `Investigation complete: ${done[0].title}`
        : `${done.length} investigations complete.`);
    }
  }

  async function refresh() {
    try {
      const list = (await api.listCases()).cases;
      setCases(list);
      announceCompletions(list);
    } catch (e) { if (e.status === 401) { clearToken(); router.replace("/login"); } }
  }

  async function refreshCollections() {
    try {
      const d = await api.getCollections();
      setCollections(d.collections || []);
      setMemberships(d.memberships || {});
    } catch (_) { /* non-fatal overlay */ }
  }

  async function createCollection(name) {
    const n = (name || "").trim();
    if (!n) return null;
    try {
      const col = await api.createCollection(n);
      await refreshCollections();
      return col;
    } catch (_) { return null; }
  }

  async function toggleCaseCollection(caseId, collectionId) {
    const current = memberships[caseId] || [];
    const next = current.includes(collectionId)
      ? current.filter((c) => c !== collectionId)
      : [...current, collectionId];
    // optimistic
    setMemberships((m) => ({ ...m, [caseId]: next }));
    try {
      await api.setCaseCollections(caseId, next);
      await refreshCollections();
    } catch (_) { refreshCollections(); }
  }

  async function setPriority(caseId, flag) {
    const prev = cases.find((c) => c.case_id === caseId)?.priority_flag || "";
    const next = prev === flag ? "" : flag; // clicking the active colour again clears it
    // optimistic
    setCases((cs) => cs.map((c) => (c.case_id === caseId ? { ...c, priority_flag: next } : c)));
    try {
      await api.setCasePriority(caseId, next);
    } catch (_) {
      // revert on failure
      setCases((cs) => cs.map((c) => (c.case_id === caseId ? { ...c, priority_flag: prev } : c)));
    }
  }

  async function removeCollection(collectionId) {
    try {
      await api.deleteCollection(collectionId);
      if (activeCollection === collectionId) setActiveCollection("all");
      await refreshCollections();
    } catch (_) {}
  }

  function signOut() {
    clearToken();
    try { localStorage.removeItem("vertex_user"); } catch (_) {}
    router.replace("/login");
  }

  const filtered = cases.filter((c) => {
    if (!(c.title || "").toLowerCase().includes(search.toLowerCase())) return false;
    if (activeCollection !== "all") {
      const mine = memberships[c.case_id] || [];
      if (activeCollection === "none") { if (mine.length !== 0) return false; }   // "Unfiled"
      else if (!mine.includes(activeCollection)) return false;
    }
    if (activePriority !== "all") {
      const p = c.priority_flag || "";
      if (activePriority === "unflagged") { if (p !== "") return false; }
      else if (p !== activePriority) return false;
    }
    return true;
  });
  const nTotal = cases.length;
  const nRunning = cases.filter((c) => c.status === "running" || c.status === "pending").length;
  const nComplete = cases.filter((c) => c.status === "complete").length;
  const priorityCounts = Object.fromEntries(
    PRIORITY.map((p) => [p.value, cases.filter((c) => (c.priority_flag || "") === p.value).length])
  );
  const nUnflagged = cases.filter((c) => !(c.priority_flag || "")).length;

  return (
    <div className="min-h-screen">
      {/* TOP BAR (always visible) */}
      <nav className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <button
          type="button"
          onClick={() => router.push("/cases")}
          className="font-display font-semibold text-slate-100"
          style={{ fontSize: 20 }}
        >
          VERTEX<span className="text-cyan-400">.</span>
        </button>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <span className="rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-[11px] font-mono text-slate-300">
            {username}
          </span>
          <button onClick={signOut} className="text-[12px] text-slate-400 hover:text-slate-200">
            Sign out
          </button>
          <Button variant="primary" onClick={() => setShowNew(true)} className="text-sm px-4 py-2">
            + New investigation
          </Button>
        </div>
      </nav>

      {/* BODY — Finder-style layout: a left sidebar (Priority buckets + shortcuts,
          always visible/sticky like Finder's Favourites pane) beside the scrolling
          case grid. Sidebar only FILTERS/NAVIGATES — same activePriority state and
          same api calls as before, nothing about what it does has changed. */}
      <div className="flex items-start">
        <Sidebar
          activePriority={activePriority}
          onPickPriority={setActivePriority}
          priorityCounts={priorityCounts}
          unflaggedCount={nUnflagged}
          nTotal={nTotal}
          router={router}
        />

        <main className="flex-1 min-w-0 px-6 py-8">
        <div className="mx-auto max-w-6xl">
        {/* PAGE TITLE */}
        <h1 className="text-2xl font-semibold text-slate-100">Investigations</h1>
        <p className="mt-1 text-sm text-slate-500">Your active and completed profiling cases.</p>

        {/* Completion banner — the fallback when desktop notifications are unavailable
            or the officer declined them. Same information, in the page. */}
        {!!banner && (
          <div
            role="status"
            className="mt-6 flex items-center justify-between gap-3 rounded-lg border border-[rgba(0,255,136,0.35)] bg-[rgba(0,255,136,0.07)] px-4 py-2.5 text-sm text-slate-200"
          >
            <span>{banner}</span>
            <button
              type="button"
              onClick={() => setBanner("")}
              className="text-slate-400 hover:text-slate-200 text-lg leading-none"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )}

        {/* STATS STRIP — only when there is at least one case (§4.2) */}
        {nTotal > 0 && (
          <GlassPanel className="p-4 mt-6">
            <div className="grid grid-cols-3 gap-4">
              <StatCard n={nTotal} label="Total investigations" />
              <StatCard n={nRunning} label="In progress" color="var(--tone-cyan)" pulse={nRunning > 0} />
              <StatCard n={nComplete} label="Complete" color="var(--tone-emerald)" />
            </div>
          </GlassPanel>
        )}

        {/* FILTER BAR */}
        <div className="mt-6">
          <Input
            placeholder="Filter by case name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* COLLECTION FILTER CHIPS — sort/browse cases by saved folder. (Priority
            filtering moved to the left sidebar — see <Sidebar> above.) */}
        {nTotal > 0 && (
          <CollectionBar
            collections={collections}
            active={activeCollection}
            onPick={setActiveCollection}
            onCreate={createCollection}
            onDelete={removeCollection}
            unfiledCount={cases.filter((c) => !(memberships[c.case_id] || []).length).length}
          />
        )}

        {/* CASE GRID / EMPTY STATE */}
        {nTotal === 0 ? (
          <div className="mt-10">
            <EmptyState
              icon="🗂️"
              title="No investigations yet"
              description="Open a new case to begin."
            >
              <Button variant="primary" onClick={() => setShowNew(true)}>
                + New investigation
              </Button>
            </EmptyState>
          </div>
        ) : filtered.length === 0 ? (
          <div className="mt-10">
            <EmptyState
              icon="🔍"
              title="No matching cases"
              description="No case name matches your filter."
            />
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((c) => (
              <GlassPanel
                key={c.case_id}
                onClick={() => router.push(`/cases/${c.case_id}`)}
                className="p-4 cursor-pointer hover:border-cyan-400"
                style={
                  c.priority_flag
                    ? { borderLeft: `3px solid ${PRIORITY_BY_VALUE[c.priority_flag]?.dot || "transparent"}` }
                    : undefined
                }
              >
                {/* Top row: title + status */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-100 truncate">{c.title}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <PriorityPicker
                      value={c.priority_flag || ""}
                      onPick={(flag) => setPriority(c.case_id, flag)}
                    />
                    <CasePicker
                      caseId={c.case_id}
                      collections={collections}
                      memberIds={memberships[c.case_id] || []}
                      open={pickerCase === c.case_id}
                      onOpen={(e) => { e.stopPropagation(); setPickerCase(pickerCase === c.case_id ? null : c.case_id); }}
                      onClose={() => setPickerCase(null)}
                      onToggle={(cid) => toggleCaseCollection(c.case_id, cid)}
                      onCreate={async (name) => { const col = await createCollection(name); if (col) toggleCaseCollection(c.case_id, col.collection_id); }}
                    />
                    <StatusPill status={c.status} className="shrink-0" />
                  </div>
                </div>

                {/* Collection chips this case is filed under */}
                {(memberships[c.case_id] || []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(memberships[c.case_id] || []).map((cid) => {
                      const col = collections.find((x) => x.collection_id === cid);
                      if (!col) return null;
                      return (
                        <span key={cid}
                          className="inline-flex items-center gap-1 text-[10px] font-mono rounded px-1.5 py-0.5 border"
                          style={{
                            color: col.color || "var(--tone-cyan-bright, #00f2fe)",
                            borderColor: (col.color || "#00f2fe") + "66",
                            background: (col.color || "#00f2fe") + "14",
                          }}>
                          🗂 {col.name}
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Officer-supplied case type/context, when given */}
                {!!(c.case_context || "").trim() && (
                  <div className="mt-1 text-xs text-slate-400 italic truncate" title={c.case_context}>
                    {c.case_context}
                  </div>
                )}

                {/* ID */}
                <div className="mt-2 text-xs font-mono text-slate-500">
                  ID: #{(c.case_id || "").slice(0, 8)}
                </div>

                {/* Discovered accounts */}
                <div className="mt-1 text-sm text-slate-300">
                  Discovered: {c.account_count ?? 0} accounts
                </div>

                {/* Bottom row: created_at + Open case */}
                <div className="mt-3 flex items-center justify-between">
                  <span
                    className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[12.5px] font-mono text-slate-200"
                    title={`Opened ${fmtTime(c.created_at)}`}
                  >
                    <span aria-hidden="true" className="text-slate-400">🗓</span>
                    {fmtTime(c.created_at)}
                  </span>
                  <Button variant="secondary" className="text-xs px-3 py-1.5">
                    Open case →
                  </Button>
                </div>
              </GlassPanel>
            ))}
          </div>
        )}
        </div>
        </main>
      </div>

      {showNew && (
        <NewInvestigation
          onClose={() => setShowNew(false)}
          onCreated={(id) => router.push(`/cases/${id}`)}
          onBulkCreated={(n) => {
            setShowNew(false);
            setBanner(`${n} investigation${n === 1 ? "" : "s"} started. `
                      + "You'll be notified as each one finishes.");
            refresh();
          }}
        />
      )}
    </div>
  );
}

// Finder-style left sidebar — a "Favourites"-like pane that never scrolls away, sat
// beside the case grid the way Finder's sidebar sits beside a folder's contents.
// Pure UI relocation: same activePriority state, same onPickPriority(setActivePriority)
// call, same toggle-off-on-repeat-click semantics the old chip bar used — just laid out
// as clickable rows instead of a horizontal chip row, and grouped with a "Flagged
// accounts" shortcut (a plain navigation, not a filter — no state of its own here).
function Sidebar({ activePriority, onPickPriority, priorityCounts, unflaggedCount, nTotal, router }) {
  const Row = ({ selected, dot, icon, label, count, onClick }) => (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-left transition-colors hover:bg-white/5 ${
        selected ? "" : "text-slate-400 hover:text-slate-200"}`}
      style={selected ? { background: `${dot}1f`, color: dot } : undefined}
    >
      {dot ? (
        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: dot }} />
      ) : (
        <span className="text-[13px] leading-none shrink-0 w-2.5 text-center">{icon}</span>
      )}
      <span className="flex-1 truncate">{label}</span>
      {count != null && <span className="text-[11px] font-mono opacity-60 shrink-0">{count}</span>}
    </button>
  );

  return (
    <aside className="hidden md:flex md:flex-col w-56 shrink-0 border-r border-slate-800 bg-slate-950/30 px-3 py-6 self-stretch">
      <div className="text-[10px] font-mono uppercase tracking-wide text-slate-600 px-2.5 mb-1.5">
        Priority
      </div>
      <div className="space-y-0.5">
        <Row
          selected={activePriority === "all"} dot="#22d3ee" icon="🗂"
          label="All cases" count={nTotal}
          onClick={() => onPickPriority("all")}
        />
        {PRIORITY.map((p) => (
          <Row
            key={p.value}
            selected={activePriority === p.value} dot={p.dot}
            label={p.label} count={priorityCounts[p.value] || 0}
            onClick={() => onPickPriority(activePriority === p.value ? "all" : p.value)}
          />
        ))}
        {unflaggedCount > 0 && (
          <Row
            selected={activePriority === "unflagged"} dot="#64748b"
            label="Unflagged" count={unflaggedCount}
            onClick={() => onPickPriority(activePriority === "unflagged" ? "all" : "unflagged")}
          />
        )}
      </div>

      <div className="text-[10px] font-mono uppercase tracking-wide text-slate-600 px-2.5 mb-1.5 mt-6">
        Shortcuts
      </div>
      <div className="space-y-0.5">
        <Row
          selected={false} dot={null} icon="🚩"
          label="Flagged accounts"
          onClick={() => router.push("/flagged")}
        />
      </div>
    </aside>
  );
}

// Small traffic-light dot picker on a case card: click a dot to set that priority,
// click the already-active dot again to clear it. Stops click propagation so it never
// opens the case underneath. Sized up from the original 12px — these are a real click
// target, not just a status indicator, and were fiddly to hit at the old size.
function PriorityPicker({ value, onPick }) {
  return (
    <span className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()} title="Set priority">
      {PRIORITY.map((p) => {
        const on = value === p.value;
        return (
          <button
            key={p.value}
            onClick={() => onPick(p.value)}
            title={p.label}
            aria-label={p.label}
            className="w-5 h-5 rounded-full transition-transform hover:scale-125"
            style={{
              background: on ? p.dot : "transparent",
              border: `2px solid ${p.dot}`,
              boxShadow: on ? `0 0 6px ${p.dot}` : "none",
            }}
          />
        );
      })}
    </span>
  );
}

// Row of collection filter chips: All / each collection (with count) / Unfiled, plus an
// inline "new collection" control. Clicking a chip filters the case grid to that folder.
function CollectionBar({ collections, active, onPick, onCreate, onDelete, unfiledCount }) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const chip = (key, label, on, extra = null) => (
    <button
      key={key}
      onClick={() => onPick(key)}
      className={`group inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-mono border transition-all ${
        on ? "border-cyan-400 bg-cyan-400/10 text-cyan-300"
           : "border-slate-700 bg-slate-900/50 text-slate-400 hover:border-slate-500"}`}
    >
      {label}
      {extra}
    </button>
  );
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {chip("all", "All cases", active === "all")}
      {collections.map((c) =>
        chip(
          c.collection_id,
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: c.color || "#00f2fe" }} />
            {c.name}
            <span className="text-slate-500">({c.case_count})</span>
          </span>,
          active === c.collection_id,
          <span
            role="button"
            title="Delete collection"
            onClick={(e) => { e.stopPropagation(); if (confirm(`Delete collection "${c.name}"? Cases are not deleted.`)) onDelete(c.collection_id); }}
            className="ml-0.5 text-slate-600 hover:text-rose-400 opacity-0 group-hover:opacity-100"
          >×</span>
        )
      )}
      {unfiledCount > 0 && chip("none",
        <span>Unfiled <span className="text-slate-500">({unfiledCount})</span></span>,
        active === "none")}

      {adding ? (
        <span className="inline-flex items-center gap-1">
          <input
            autoFocus value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={async (e) => {
              if (e.key === "Enter") { await onCreate(name); setName(""); setAdding(false); }
              if (e.key === "Escape") { setName(""); setAdding(false); }
            }}
            placeholder="Collection name…"
            className="w-40 rounded-full bg-slate-900 border border-cyan-500/50 px-3 py-1 text-xs text-slate-100 outline-none"
          />
          <button onClick={async () => { await onCreate(name); setName(""); setAdding(false); }}
            className="text-xs text-cyan-400 hover:text-cyan-300">add</button>
        </span>
      ) : (
        <button onClick={() => setAdding(true)}
          className="rounded-full px-3 py-1 text-xs font-mono border border-dashed border-slate-600 text-slate-400 hover:border-cyan-400 hover:text-cyan-300">
          + New collection
        </button>
      )}
    </div>
  );
}

// Small folder button on a case card that opens a checkbox picker of collections
// (plus inline create). Stops click propagation so it never opens the case.
function CasePicker({ caseId, collections, memberIds, open, onOpen, onClose, onToggle, onCreate }) {
  const [name, setName] = useState("");
  const filed = memberIds.length;
  return (
    <span className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={onOpen}
        title="Save to collection"
        className={`text-[15px] leading-none transition-transform hover:scale-110 ${
          filed ? "text-cyan-300" : "text-slate-500 hover:text-slate-300"}`}
      >
        🗂{filed > 0 ? "" : "︎"}
      </button>
      {open && (
        <>
          {/* click-away backdrop */}
          <span className="fixed inset-0 z-20" onClick={onClose} />
          <div className="absolute right-0 top-6 z-30 w-56 rounded-lg border border-slate-700 bg-slate-900 shadow-xl p-2">
            <div className="text-[10px] font-mono uppercase tracking-wide text-slate-500 px-1 pb-1">
              Save to collection
            </div>
            <div className="max-h-48 overflow-y-auto">
              {collections.length === 0 && (
                <div className="text-xs text-slate-500 px-1 py-2">No collections yet.</div>
              )}
              {collections.map((c) => {
                const on = memberIds.includes(c.collection_id);
                return (
                  <label key={c.collection_id}
                    className="flex items-center gap-2 px-1 py-1 rounded hover:bg-slate-800 cursor-pointer">
                    <input type="checkbox" checked={on}
                      onChange={() => onToggle(c.collection_id)} className="accent-cyan-400" />
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: c.color || "#00f2fe" }} />
                    <span className="text-xs text-slate-200 truncate">{c.name}</span>
                  </label>
                );
              })}
            </div>
            <div className="border-t border-slate-800 mt-1 pt-1.5 flex items-center gap-1">
              <input value={name} onChange={(e) => setName(e.target.value)}
                onKeyDown={async (e) => { if (e.key === "Enter" && name.trim()) { await onCreate(name); setName(""); } }}
                placeholder="New collection…"
                className="flex-1 min-w-0 rounded bg-slate-950 border border-slate-700 px-2 py-1 text-xs text-slate-100 outline-none focus:border-cyan-500" />
              <button onClick={async () => { if (name.trim()) { await onCreate(name); setName(""); } }}
                className="text-xs text-cyan-400 hover:text-cyan-300 px-1">+</button>
            </div>
          </div>
        </>
      )}
    </span>
  );
}

function StatCard({ n, label, color = "var(--stat-num-strong)", pulse = false }) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="text-3xl font-semibold" style={{ color }}>{n}</span>
        {pulse && <span className="pulse-dot" style={{ color }} />}
      </div>
      <div className="mt-1 text-[11px] font-mono uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

const STEP_COLOR = {
  info: "#94a3b8", success: "#00ff88", warning: "#ffb703", error: "#ff3366",
};

function NewInvestigation({ onClose, onCreated, onBulkCreated }) {
  const [mode, setMode] = useState("standard"); // "standard" | "bulk" | "agentic"
  const [title, setTitle] = useState("");
  const [caseContext, setCaseContext] = useState(""); // optional "what kind of case is this?"
  const [region, setRegion] = useState("INDIA");
  const [seeds, setSeeds] = useState([]);
  // Default to "username" — best-tested, highest-recall path (see prior note).
  const [draftType, setDraftType] = useState("username");
  const [draftValue, setDraftValue] = useState("");
  const [captureEvidence, setCaptureEvidence] = useState(false); // court-grade evidence capture
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // ── Bulk .docx mode ──
  // Preview first, run second: parsing costs nothing, but confirming spawns one full
  // investigation per subject. Mirrors the pivot flow's suggest-then-run split.
  const [bulkFile, setBulkFile] = useState(null);
  const [bulkPreview, setBulkPreview] = useState(null);   // {subjects, total_seeds}
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef(null);
  // dragenter/dragleave also fire when the pointer crosses CHILD elements, so a plain
  // boolean flickers the highlight off while still inside the zone. Counting enters
  // minus leaves is the standard fix.
  const dragDepth = useRef(0);

  const ACCEPT = ".xlsx,.csv,.docx";

  function isAccepted(f) {
    return !!f && ACCEPT.split(",").some((ext) => f.name.toLowerCase().endsWith(ext));
  }

  function onDrop(e) {
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    // Reject by extension here so a wrong file never costs a round-trip; the server
    // validates again on upload (never trust the client).
    if (!isAccepted(f)) {
      setBulkFile(null); setBulkPreview(null);
      setError(`"${f.name}" is not a supported sheet — use .xlsx, .csv or .docx.`);
      return;
    }
    chooseFile(f);
  }

  async function chooseFile(f) {
    setError(""); setBulkPreview(null); setBulkFile(f || null);
    if (!f) return;
    setBusy(true);
    try {
      setBulkPreview(await api.bulkPreview(f));
    } catch (e) { setError(e.message); setBulkFile(null); }
    finally { setBusy(false); }
  }

  async function beginBulk() {
    if (!bulkFile) { setError("Choose a subject sheet first."); return; }
    setError(""); setBusy(true);
    // Ask for notification permission here: this click is the user gesture browsers
    // require, and it is the moment the officer actually wants to be told when it ends.
    await requestPermission();
    try {
      const res = await api.bulkCreate(bulkFile);
      onBulkCreated(res.created);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  // ── Agentic web mode ──
  const [agTools, setAgTools] = useState([]);
  const [agTool, setAgTool] = useState("socialsearcher");
  const [agType, setAgType] = useState("username");
  const [agQuery, setAgQuery] = useState("");
  const [agUrl, setAgUrl] = useState("");
  const [agInstr, setAgInstr] = useState("");
  const [agTask, setAgTask] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    if (mode !== "agentic" || agTools.length) return;
    api.getAgenticTools().then(setAgTools).catch(() => {});
  }, [mode, agTools.length]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  function addSeed() {
    if (!draftValue.trim()) return;
    setSeeds([...seeds, { type: draftType, value: draftValue.trim() }]);
    setDraftValue("");
  }

  async function begin() {
    setError(""); setBusy(true);
    try {
      if (!seeds.length) throw new Error("Add at least one identifier to continue.");
      const res = await api.createCase(title || "Untitled investigation", seeds, region,
                                       caseContext.trim(), captureEvidence);
      onCreated(res.case_id);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  async function beginAgentic() {
    setError("");
    if (!agQuery.trim()) { setError("Enter a query for the agent to look up."); return; }
    if (agTool === "custom" && !agUrl.trim()) { setError("Enter a URL for the custom web tool."); return; }
    setBusy(true);
    try {
      const task = await api.startAgenticInvestigate({
        query: agQuery.trim(),
        tool_id: agTool,
        seed_type: agType,
        title: title || `Agentic: ${agQuery.trim()}`,
        custom_url: agTool === "custom" ? agUrl.trim() : null,
        custom_instruction: agTool === "custom" ? (agInstr.trim() || null) : null,
      });
      setAgTask(task);
      pollRef.current = setInterval(async () => {
        try {
          const t = await api.getAgenticStatus(task.task_id);
          setAgTask(t);
          if (["complete", "blocked", "error"].includes(t.status)) {
            clearInterval(pollRef.current); pollRef.current = null; setBusy(false);
          }
        } catch (_) {}
      }, 1500);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  const placeholder = SEED_TYPES.find((t) => t.value === draftType)?.placeholder || "";
  const typeLabel = (v) => SEED_TYPES.find((t) => t.value === v)?.label || v;
  const toolList = agTools.length ? agTools : [
    { id: "socialsearcher", name: "Social Searcher (real-time mentions)", icon: "🔍" },
    { id: "inflact", name: "Inflact Instagram Viewer (best-effort)", icon: "📸" },
    { id: "custom", name: "Custom web tool (any URL)", icon: "🛠️" },
  ];
  const terminal = agTask && ["complete", "blocked", "error"].includes(agTask.status);
  const selectedTool = toolList.find((t) => t.id === agTool);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <GlassPanel className="w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto relative">
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-200 text-lg leading-none"
          aria-label="Close"
        >
          ✕
        </button>

        <h2 className="text-lg font-semibold text-slate-100">New investigation</h2>
        <p className="mt-1 text-xs text-slate-500">
          Enter identifiers for one subject, or upload a sheet to profile several at once.
        </p>

        {/* Agentic-web mode disabled for now (browser-agent path unreliable). */}
        <div className="mt-4 flex gap-2">
          {[
            { id: "standard", label: "Manual entry" },
            { id: "bulk", label: "Bulk upload" },
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                setMode(m.id); setError("");
                dragDepth.current = 0; setDragging(false);
              }}
              aria-pressed={mode === m.id}
              className={`flex-1 rounded-lg border px-3 py-2 text-[13px] transition-colors ${
                mode === m.id
                  ? "border-cyan-400 text-slate-100 bg-cyan-400/10"
                  : "border-white/10 text-slate-400 hover:text-slate-200"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {error && (
          <div
            className="mt-4 rounded-lg px-3 py-2 text-[13px]"
            style={{ color: "var(--tone-rose)", background: "rgba(255,51,102,0.12)", border: "1px solid rgba(255,51,102,0.35)" }}
          >
            {error}
          </div>
        )}

        {/* Case title — manual entry only; bulk takes each case's title from the document. */}
        <div className={`mt-5 ${mode === "bulk" ? "hidden" : ""}`}>
          <Label>Case title</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Sushil Kumar - phishing case #24"
            disabled={!!agTask}
          />
        </div>

        {/* ─────────── STANDARD MODE ─────────── */}
        {mode === "standard" && (
          <>
            {/* Optional crime-type context — never filters the search; it sharpens the
                LLM guidance layers (recommended next steps, briefing, case chat). */}
            <div className="mt-4">
              <Label>What kind of case is this? <span className="normal-case text-slate-500">(optional)</span></Label>
              <textarea
                value={caseContext}
                onChange={(e) => setCaseContext(e.target.value)}
                rows={2}
                maxLength={500}
                placeholder="e.g. investment fraud through Telegram — guides the recommended next steps, not the search itself"
                className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/40 resize-none"
              />
            </div>

            <div className="mt-4">
              <Label>Region</Label>
              <select value={region} onChange={(e) => setRegion(e.target.value)} className={SELECT_CLS}>
                {REGIONS.map((r) => (
                  <option key={r.value} value={r.value} className="bg-slate-900">{r.label}</option>
                ))}
              </select>
            </div>

            <div className="mt-4">
              <Label>Identifiers</Label>
              <div className="flex gap-2">
                <select
                  value={draftType}
                  onChange={(e) => setDraftType(e.target.value)}
                  className={SELECT_CLS + " basis-[30%] shrink-0 px-2"}
                >
                  {SEED_TYPES.map((t) => (
                    <option key={t.value} value={t.value} className="bg-slate-900">{t.label}</option>
                  ))}
                </select>
                <Input
                  className="flex-1"
                  value={draftValue}
                  placeholder={placeholder}
                  onChange={(e) => setDraftValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSeed(); } }}
                />
                <Button variant="secondary" onClick={addSeed} className="text-xs px-3 py-2 shrink-0">
                  Add
                </Button>
              </div>

              {seeds.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {seeds.map((s, i) => (
                    <PivotPill key={i}>
                      <span className="text-slate-400">[{typeLabel(s.type)}]</span> {s.value}
                      <button
                        type="button"
                        onClick={() => setSeeds(seeds.filter((_, j) => j !== i))}
                        className="ml-1 text-slate-400 hover:text-slate-200"
                        aria-label="Remove identifier"
                      >
                        ×
                      </button>
                    </PivotPill>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={captureEvidence}
                  onChange={(e) => setCaptureEvidence(e.target.checked)}
                  style={{ accentColor: "#00f2fe" }}
                />
                <span className="text-sm text-slate-200">Capture court-grade evidence</span>
                <Tooltip content="Captures each source page at the moment of viewing — screenshot + MHTML + DOM — SHA-256 hashed, written to the tamper-evident ledger and externally timestamped (RFC-3161). Exhibits appear in the downloadable report. Sources are dynamic; this preserves what was seen." />
              </label>
            </div>
          </>
        )}

        {/* ─────────── AGENTIC MODE (setup) ─────────── */}
        {mode === "agentic" && !agTask && (
          <>
            <div className="mt-4">
              <Label>OSINT web tool</Label>
              <select value={agTool} onChange={(e) => setAgTool(e.target.value)} className={SELECT_CLS}>
                {toolList.map((t) => (
                  <option key={t.id} value={t.id} className="bg-slate-900">{t.icon} {t.name}</option>
                ))}
              </select>
              {selectedTool?.description && (
                <p className="mt-1 text-[11px] text-slate-500">{selectedTool.description}</p>
              )}
            </div>

            {agTool === "custom" && (
              <>
                <div className="mt-4">
                  <Label>Target URL</Label>
                  <Input value={agUrl} onChange={(e) => setAgUrl(e.target.value)}
                         placeholder="https://some-osint-tool.example/search" />
                </div>
                <div className="mt-4">
                  <Label>Extraction instruction (optional)</Label>
                  <Input value={agInstr} onChange={(e) => setAgInstr(e.target.value)}
                         placeholder="e.g. Search the query and extract each profile's name, handle, bio." />
                </div>
              </>
            )}

            <div className="mt-4 flex gap-2">
              <div className="basis-[30%] shrink-0">
                <Label>Type</Label>
                <select value={agType} onChange={(e) => setAgType(e.target.value)} className={SELECT_CLS + " px-2"}>
                  {SEED_TYPES.filter((t) => ["username", "name", "email"].includes(t.value)).map((t) => (
                    <option key={t.value} value={t.value} className="bg-slate-900">{t.label}</option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <Label>Query</Label>
                <Input value={agQuery} onChange={(e) => setAgQuery(e.target.value)}
                       placeholder="e.g. ash29_03"
                       onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); beginAgentic(); } }} />
              </div>
            </div>

            <p className="mt-3 text-[11px] text-slate-500 leading-relaxed">
              The agent drives a real browser, extracts only what's on the page (never fabricated),
              and the result is correlated into the case. Protected sites may be blocked — that's
              reported honestly, not faked.
            </p>
          </>
        )}

        {/* ─────────── AGENTIC MODE (live progress) ─────────── */}
        {mode === "agentic" && agTask && (
          <div className="mt-5">
            <div className="flex items-center gap-2">
              <StatusPill status={agTask.status === "complete" ? "complete"
                                : agTask.status === "error" ? "error" : "running"} />
              <span className="text-xs font-mono text-slate-400">{agTask.status}</span>
              {agTask.entities_added > 0 && (
                <span className="text-[11px] text-emerald-300">+{agTask.entities_added} account(s)</span>
              )}
            </div>

            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 max-h-56 overflow-y-auto space-y-1.5">
              {(agTask.step_logs || []).map((l, i) => (
                <div key={i} className="text-[12px] font-mono flex gap-2">
                  <span style={{ color: STEP_COLOR[l.status] || "#94a3b8" }}>•</span>
                  <span className="text-slate-300">{l.details}</span>
                </div>
              ))}
              {!terminal && (
                <div className="text-[12px] font-mono text-cyan-400 flex items-center gap-2">
                  <span className="pulse-dot" style={{ color: "var(--tone-cyan)" }} /> working…
                </div>
              )}
            </div>

            {agTask.status === "blocked" && (
              <p className="mt-3 text-[12px]" style={{ color: "var(--tone-amber)" }}>
                🚧 The site blocked automated access (CAPTCHA / login wall). No data was fabricated.
              </p>
            )}
            {agTask.status === "error" && (
              <p className="mt-3 text-[12px]" style={{ color: "var(--tone-rose)" }}>
                {agTask.error_message || "The agent could not complete the task."}
              </p>
            )}
          </div>
        )}

        {/* ─────────── BULK MODE ─────────── */}
        {mode === "bulk" && (
          <div className="mt-5">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv,.docx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => chooseFile(e.target.files?.[0])}
              className="hidden"
            />

            {/* Drop zone. A <button> rather than a <div onClick> so it is reachable by
                keyboard and announced properly; the real <input type="file"> above stays
                in the DOM (hidden) and is what actually opens the picker. */}
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              onDragEnter={(e) => { e.preventDefault(); dragDepth.current += 1; setDragging(true); }}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={(e) => {
                e.preventDefault();
                dragDepth.current = Math.max(0, dragDepth.current - 1);
                if (dragDepth.current === 0) setDragging(false);
              }}
              onDrop={onDrop}
              aria-label="Drop a subject sheet here, or choose a file"
              className={`w-full rounded-xl border-2 border-dashed px-6 py-9 text-center transition-colors duration-150 ${
                dragging
                  ? "border-cyan-400 bg-cyan-400/10"
                  : bulkFile
                    ? "border-cyan-500/40 bg-cyan-500/[0.06] hover:border-cyan-400/60"
                    : "border-white/15 bg-white/[0.02] hover:border-cyan-400/50 hover:bg-white/[0.04]"
              }`}
            >
              <svg
                className={`mx-auto h-9 w-9 ${dragging || bulkFile ? "text-cyan-300" : "text-slate-500"}`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
              >
                <path d="M12 16V4" />
                <path d="M7 9l5-5 5 5" />
                <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
              </svg>

              {bulkFile ? (
                <>
                  <div className="mt-3 text-[15px] font-semibold text-slate-100 break-all px-2">
                    {bulkFile.name}
                  </div>
                  <div className="mt-1 text-[13px] text-slate-400">
                    {(bulkFile.size / 1024).toFixed(1)} KB · tap to choose a different file
                  </div>
                </>
              ) : (
                <>
                  <div className="mt-3 text-[15px] font-semibold text-slate-100">
                    {dragging ? "Release to load the sheet" : "Drop a .xlsx, .csv or .docx here"}
                  </div>
                  <div className="mt-1 text-[13px] text-slate-400">or tap to choose a file</div>
                </>
              )}
            </button>

            {/* Format card — the rules, then the templates that already satisfy them.
                Sample files are served straight out of frontend/public, so these are
                plain static downloads with no API round-trip. Regenerate both with
                `python -m scripts.make_bulk_template`. */}
            <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <p className="text-[13px] leading-relaxed text-slate-400">
                One subject per row, with a header row naming the columns:{" "}
                <span className="text-slate-200">Name</span>,{" "}
                <span className="text-slate-200">Phone</span>,{" "}
                <span className="text-slate-200">Email</span>,{" "}
                <span className="text-slate-200">Username</span>,{" "}
                <span className="text-slate-200">UPI</span>,{" "}
                <span className="text-slate-200">Profile URLs</span>,{" "}
                <span className="text-slate-200">Photo URL</span>. No column is required —
                fill in what you have. Several profile links (Facebook, Instagram, YouTube,
                X…) can share the one <span className="text-slate-200">Profile URLs</span> cell.
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-400">
                Each row becomes its own case — identifiers are never merged across rows —
                and runs are queued one at a time. Files up to{" "}
                <span className="text-slate-200">5 MB</span>; there is no limit on the
                number of subjects, so you will see the exact count to confirm before
                anything runs.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                {[
                  { href: "/bulk_template.xlsx", label: "Download Excel template" },
                  { href: "/bulk_template.csv", label: "Download CSV template" },
                ].map((t) => (
                  <a
                    key={t.href}
                    href={t.href}
                    download
                    className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-cyan-300 hover:text-cyan-200 transition-colors"
                  >
                    <span aria-hidden="true">↓</span>
                    {t.label}
                  </a>
                ))}
              </div>
            </div>

            {busy && !bulkPreview && (
              <p className="mt-3 text-sm text-slate-400">Reading document…</p>
            )}

            {bulkPreview && (
              <div className="mt-4">
                <div className="text-sm text-slate-300">
                  Found <span className="text-slate-100 font-semibold">{bulkPreview.subjects.length}</span>
                  {" "}subject{bulkPreview.subjects.length === 1 ? "" : "s"} and{" "}
                  <span className="text-slate-100 font-semibold">{bulkPreview.total_seeds}</span> identifiers.
                  Nothing has run yet.
                </div>
                {/* With no row cap, this confirmation IS the guard — a large sheet is a
                    long job, so state the cost before the button is pressed. ~7 min per
                    case is the measured median of live runs. */}
                <div className="mt-1 text-xs text-slate-500">
                  Queued one at a time — roughly{" "}
                  <span className="text-slate-400">
                    {bulkPreview.subjects.length < 9
                      ? `${Math.max(1, Math.round(bulkPreview.subjects.length * 7))} min`
                      : `${(bulkPreview.subjects.length * 7 / 60).toFixed(1)} hours`}
                  </span>{" "}
                  in total at ~7 min per case.
                </div>
                <div className="mt-3 max-h-56 overflow-y-auto rounded-lg border border-white/10 divide-y divide-white/5">
                  {bulkPreview.subjects.map((sub, i) => (
                    <div key={i} className="px-3 py-2">
                      <div className="text-[13px] font-medium text-slate-200 truncate">
                        {sub.title}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {sub.seeds.map((sd, j) => (
                          <span
                            key={j}
                            className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[11px] font-mono text-slate-400"
                            title={typeLabel(sd.type)}
                          >
                            {sd.value}
                          </span>
                        ))}
                      </div>
                      {!!sub.dropped_seeds && (
                        <div className="mt-1 text-[11px]" style={{ color: "var(--tone-amber, #ffb703)" }}>
                          {sub.dropped_seeds} further identifier(s) dropped — 25 per row max.
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {permission() === "denied" && (
                  <p className="mt-3 text-xs text-slate-500">
                    Desktop notifications are blocked for this site — completions will show
                    on the Investigations page instead.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 flex items-center justify-end gap-3">
          {!agTask && (
            <>
              <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
              {mode === "standard" ? (
                <Button variant="primary" onClick={begin} disabled={busy}>
                  {busy ? "Starting..." : "Start investigation"}
                </Button>
              ) : mode === "bulk" ? (
                <Button variant="primary" onClick={beginBulk} disabled={busy || !bulkPreview}>
                  {busy
                    ? "Starting..."
                    : bulkPreview
                      ? `Start ${bulkPreview.subjects.length} investigation${bulkPreview.subjects.length === 1 ? "" : "s"}`
                      : "Start investigations"}
                </Button>
              ) : (
                <Button variant="primary" onClick={beginAgentic} disabled={busy}>
                  {busy ? "Launching agent..." : "🤖 Run agent"}
                </Button>
              )}
            </>
          )}
          {agTask && (
            <Button
              variant="primary"
              onClick={() => onCreated(agTask.case_id)}
              disabled={!terminal}
            >
              {terminal ? "Open case →" : "Working…"}
            </Button>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}
