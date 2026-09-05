/* app/flagged/page.js
   Cross-case "Flagged" dashboard — every red/orange/yellow-flagged account across ALL
   of the investigator's cases, in three columns (one per severity), newest first.
   Clicking an item redirects to that account's case (and deep-selects + scrolls to it
   there via ?entity=<id> — see the effect in cases/[id]/page.js).
   Mirrors AccountCard.jsx's FLAGS colours/semantics (red = high concern, orange =
   suspicious, yellow = watch) — this is the per-ACCOUNT flag set from
   annotations_service.py, distinct from the per-CASE red/orange/green priority on the
   case list (app/cases/page.js). */
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "@/lib/api";
import GlassPanel from "@/components/ui/GlassPanel";
import EmptyState from "@/components/ui/EmptyState";
import PlatformLogo from "@/components/ui/PlatformLogo";
import ThemeToggle from "@/components/ui/ThemeToggle";

// Mirrors AccountCard.jsx's FLAGS exactly (kept in sync deliberately — see that file's
// own comment pointing back at annotations_service.VALID_FLAGS).
const COLUMNS = [
  { key: "red", label: "High concern", color: "#ff3366", icon: "🔴" },
  { key: "orange", label: "Suspicious", color: "#ff9f1c", icon: "🟠" },
  { key: "yellow", label: "Watch", color: "#ffd23f", icon: "🟡" },
];

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function FlaggedDashboard() {
  const router = useRouter();
  const [data, setData] = useState(null); // {red:[], orange:[], yellow:[]}
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    try { setUsername(localStorage.getItem("vertex_user") || "investigator"); } catch (_) {}
    refresh();
  }, [router]);

  async function refresh() {
    try {
      setData(await api.getFlaggedAccounts());
    } catch (e) {
      if (e.status === 401) { clearToken(); router.replace("/login"); return; }
      setError(e.message || "Could not load flagged accounts.");
    }
  }

  function signOut() {
    clearToken();
    try { localStorage.removeItem("vertex_user"); } catch (_) {}
    router.replace("/login");
  }

  function openItem(item) {
    router.push(`/cases/${item.case_id}?entity=${encodeURIComponent(item.entity_id)}`);
  }

  const total = data ? COLUMNS.reduce((s, c) => s + (data[c.key]?.length || 0), 0) : 0;

  return (
    <div className="min-h-screen">
      {/* TOP BAR — matches app/cases/page.js */}
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
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <button
          onClick={() => router.push("/cases")}
          className="text-xs text-slate-500 hover:text-cyan-400 mb-2"
        >
          ← Back to investigations
        </button>
        <h1 className="text-2xl font-semibold text-slate-100">Flagged accounts</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every red/orange/yellow-flagged account across all your cases, in one place. Click any
          entry to jump straight to its case.
        </p>

        {error && (
          <div className="mt-4 rounded-lg px-3 py-2 text-[13px]"
               style={{ color: "var(--tone-rose)", background: "rgba(255,51,102,0.12)", border: "1px solid rgba(255,51,102,0.35)" }}>
            {error}
          </div>
        )}

        {!data ? (
          <div className="mt-10 text-center text-sm text-slate-500">Loading…</div>
        ) : total === 0 ? (
          <div className="mt-10">
            <EmptyState
              icon="🚩"
              title="Nothing flagged yet"
              description='Open a case and flag an account red/orange/yellow (on its account card) — it will show up here.'
            />
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
            {COLUMNS.map((col) => (
              <FlagColumn
                key={col.key}
                col={col}
                items={data[col.key] || []}
                onOpen={openItem}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function FlagColumn({ col, items, onOpen }) {
  return (
    <GlassPanel className="overflow-hidden p-0">
      {/* Colour-coded header — echoes the flag colour so the column is identifiable at
          a glance without reading the label. */}
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ background: `${col.color}1f`, borderBottom: `2px solid ${col.color}` }}
      >
        <span className="text-sm font-semibold" style={{ color: col.color }}>
          {col.icon} {col.label}
        </span>
        <span
          className="text-[11px] font-mono rounded-full px-2 py-0.5"
          style={{ color: col.color, border: `1px solid ${col.color}66`, background: `${col.color}14` }}
        >
          {items.length}
        </span>
      </div>

      <div className="max-h-[70vh] overflow-y-auto divide-y divide-white/[0.06]">
        {items.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-slate-600">
            No {col.label.toLowerCase()} flags.
          </div>
        ) : (
          items.map((item) => <FlagItem key={`${item.case_id}:${item.entity_id}`} item={item} color={col.color} onOpen={onOpen} />)
        )}
      </div>
    </GlassPanel>
  );
}

function FlagItem({ item, color, onOpen }) {
  const name = item.name || item.value || "Unknown account";
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className="w-full text-left px-4 py-3 hover:bg-white/[0.04] transition-colors group"
    >
      <div className="flex items-start gap-2.5">
        {item.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.photo_url}
            alt=""
            className="w-8 h-8 rounded-full object-cover shrink-0 border border-white/10"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        ) : (
          <span className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-slate-800 border border-white/10">
            <PlatformLogo platform={item.platform} width={16} height={16} />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm text-slate-100 truncate">{name}</span>
            {item.bookmarked && <span title="Bookmarked" className="text-amber-300 text-xs shrink-0">★</span>}
          </div>
          <div className="text-[11px] text-slate-500 truncate">
            {item.platform || item.type} · @{item.value}
          </div>
          <div className="mt-1 text-[11px] font-mono truncate" style={{ color: `${color}cc` }}>
            🗂 {item.case_title}
          </div>
          {!!item.note && (
            <div className="mt-1 text-[11px] text-slate-400 italic truncate" title={item.note}>
              “{item.note}”
            </div>
          )}
          {!!item.updated_at && (
            <div className="mt-1 text-[10px] font-mono text-slate-600">{fmtTime(item.updated_at)}</div>
          )}
        </div>
        <span className="text-slate-600 group-hover:text-cyan-400 text-xs shrink-0 mt-0.5">→</span>
      </div>
    </button>
  );
}
