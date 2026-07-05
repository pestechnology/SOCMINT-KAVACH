/* components/ui/TimelineModal.jsx
   Account-wise timeline. Two coordinated views over the SAME model (lib/timeline):

     1. GRAPH  — a swimlane per account on a shared time axis, with a creation-density
        strip on top. Answers the profiling questions at a glance: which handle is
        oldest, were accounts created in a burst, which are dormant, when data leaked.
     2. ACCOUNTS — the same accounts as cards, each with its OWN chronology (age,
        active window, per-event rows) so an investigator can read one identity's
        lifecycle in detail without the others in the way.

   Everything is built from real, source-provided dates only (see lib/timeline). An
   account with no verifiable date is surfaced honestly under "No date available"
   rather than being stamped with the scrape time. `clusters` supplies the confidence
   tier per account so the timeline agrees with the rest of the case room. */
"use client";
import { useMemo, useState } from "react";
import PlatformLogo from "./PlatformLogo";
import TimelineGraph from "./TimelineGraph";
import {
  buildTimeline, tierStyle, BREACH_COLOR, EVENT_KINDS,
  formatFullDate, formatTime, formatMonthYear, durationHuman, relativeTime,
} from "@/lib/timeline";

function tierByEntityFrom(clusters) {
  const map = {};
  (clusters || []).forEach((c) => (c.entity_ids || []).forEach((id) => {
    // keep the strongest tier if an entity appears in multiple clusters
    const rank = { HIGH: 3, MEDIUM: 2, LOW: 1, REJECT: 0 };
    if (!map[id] || (rank[c.tier] ?? 0) > (rank[map[id]] ?? 0)) map[id] = c.tier;
  }));
  return map;
}

function EventRow({ ev, now, last }) {
  const k = EVENT_KINDS[ev.kind] || {};
  const color = ev.kind === "breach" ? BREACH_COLOR : "#64748b";
  const glyph =
    ev.kind === "created" ? <span className="w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: color === BREACH_COLOR ? color : "#94a3b8" }} />
    : ev.kind === "archived" ? <span className="w-2 h-2 rounded-[2px]" style={{ background: "#94a3b8" }} />
    : ev.kind === "breach" ? <span className="w-2 h-2 rotate-45" style={{ background: BREACH_COLOR }} />
    : <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#94a3b8" }} />;
  return (
    <div className={`relative pl-5 ${last ? "" : "border-l border-slate-800 pb-3"} ml-1`}>
      <span className="absolute -left-[5px] top-0.5 flex items-center justify-center">{glyph}</span>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-slate-200 truncate">
            {ev.label}
            {ev.kind === "breach" && ev.detail && <span className="text-slate-500"> — {ev.detail}</span>}
          </div>
          {ev.date && (
            <div className="text-[11px] text-slate-500 mt-0.5">
              {formatFullDate(ev.date)}{ev.hasTime ? ` · ${formatTime(ev.date)}` : ""}
            </div>
          )}
        </div>
        <div className="text-[11px] text-slate-500 shrink-0 whitespace-nowrap mt-0.5">
          {ev.date ? relativeTime(ev.date, now) : ""}
        </div>
      </div>
    </div>
  );
}

function AccountCardRow({ account, now }) {
  const [open, setOpen] = useState(false);
  const ts = tierStyle(account.tier);
  const accent = account.isBreach ? BREACH_COLOR : ts.color;
  const created = account.events.find((e) => e.kind === "created");
  const activeWindow = account.firstDate && account.lastDate && account.lastDate > account.firstDate
    ? durationHuman(account.firstDate, account.lastDate) : null;
  const dormantFor = account.lastDate ? relativeTime(account.lastDate, now) : null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-3 px-3.5 py-3 text-left hover:bg-slate-800/40 transition-colors">
        <span className="w-1 self-stretch rounded-full shrink-0" style={{ background: accent }} />
        <PlatformLogo platform={account.platform} width={26} height={26} className="shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white truncate">{account.name}</span>
            {account.isBreach ? (
              <span className="text-[9px] font-mono uppercase tracking-wide text-red-400 bg-red-500/10 border border-red-500/30 rounded px-1.5 py-0.5">breach</span>
            ) : (
              <span className="text-[9px] font-mono uppercase tracking-wide rounded px-1.5 py-0.5 border"
                style={{ color: accent, borderColor: `${accent}55`, background: `${accent}14` }}>{ts.label}</span>
            )}
          </div>
          <div className="text-[11px] text-slate-500 truncate">{account.value}</div>
        </div>
        <div className="text-right shrink-0">
          {created ? (
            <>
              <div className="text-[11px] text-slate-400">{formatMonthYear(created.date)}</div>
              <div className="text-[10px] font-mono text-slate-600">age {durationHuman(created.date, now)}</div>
            </>
          ) : (
            <div className="text-[10px] font-mono text-slate-600">{account.events.length} event{account.events.length === 1 ? "" : "s"}</div>
          )}
        </div>
        <span className="text-slate-600 text-xs shrink-0">{open ? "▾" : "▸"}</span>
      </button>

      {/* at-a-glance profiling facts */}
      <div className="px-3.5 pb-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-slate-500">
        {activeWindow && <span>active window <span className="text-slate-400">{activeWindow}</span></span>}
        {dormantFor && <span>last seen <span className="text-slate-400">{dormantFor}</span></span>}
        <span>{account.events.length} dated event{account.events.length === 1 ? "" : "s"}</span>
      </div>

      {open && (
        <div className="px-4 pb-4 pt-1">
          {account.events.map((ev, i) => (
            <EventRow key={i} ev={ev} now={now} last={i === account.events.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function TimelineModal({ isOpen, onClose, entities = [], clusters = [] }) {
  const [hideBreaches, setHideBreaches] = useState(false);
  const [view, setView] = useState("graph"); // "graph" | "accounts"
  const now = useMemo(() => new Date(), [isOpen]);

  const model = useMemo(
    () => buildTimeline(entities, tierByEntityFrom(clusters)),
    [entities, clusters]
  );

  if (!isOpen) return null;

  const shownAccounts = hideBreaches ? model.accounts.filter((a) => !a.isBreach) : model.accounts;
  const { stats } = model;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-4xl max-h-[88vh] flex flex-col bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden text-slate-100"
           style={{ "--tl-surface": "#0b1220" }}>
        {/* HEADER */}
        <div className="relative px-6 py-5 border-b border-slate-800 flex items-start justify-between gap-4 bg-gradient-to-r from-cyan-500/[0.07] via-transparent to-transparent">
          <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Timeline</h2>
            <p className="text-sm text-slate-400 mt-1">
              Each account's lifecycle on one time axis — built from real creation, activity, archive and breach dates.
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors text-lg shrink-0"
            title="Close timeline"
          >
            ✕
          </button>
        </div>

        {/* CONTROLS: view toggle + hide breaches */}
        <div className="px-6 pt-5 flex items-center justify-between gap-4 flex-wrap">
          <div className="inline-flex rounded-lg border border-slate-800 p-0.5 bg-slate-900/60">
            {[["graph", "Graph"], ["accounts", "By account"]].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  view === id ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {stats.breaches > 0 && (
            <label className="inline-flex items-center gap-2.5 cursor-pointer select-none">
              <span
                className={`relative inline-block w-9 h-5 rounded-full transition-colors ${hideBreaches ? "bg-cyan-500" : "bg-slate-700"}`}
                onClick={() => setHideBreaches((v) => !v)}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${hideBreaches ? "translate-x-4" : "translate-x-0"}`} />
              </span>
              <span className="text-sm text-slate-300" onClick={() => setHideBreaches((v) => !v)}>Hide data breaches</span>
            </label>
          )}
        </div>

        {/* BODY */}
        <div className="px-6 pb-6 pt-4 overflow-y-auto flex-1 custom-scrollbar">
          {model.accounts.length === 0 && model.undated.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-500">No events to show yet for this case.</div>
          ) : view === "graph" ? (
            <TimelineGraph model={model} hideBreaches={hideBreaches} />
          ) : (
            <div className="space-y-2.5">
              {shownAccounts.map((a) => <AccountCardRow key={a.entity_id} account={a} now={now} />)}
            </div>
          )}

          {/* Undated accounts — in graph view these are surfaced per-tier as "no date"
              chips inside the graph itself, so this bottom tray is only for the
              account-card view (which lists dated accounts). */}
          {view === "accounts" && model.undated.length > 0 && (
            <div className="mt-5 pt-4 border-t border-slate-800">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                No date available ({model.undated.length})
              </div>
              <div className="flex flex-wrap gap-2">
                {model.undated.map((a) => (
                  <span key={a.entity_id} className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 bg-slate-900/60 border border-slate-800 rounded-full pl-1.5 pr-2.5 py-1">
                    <PlatformLogo platform={a.platform} width={14} height={14} />
                    <span className="truncate max-w-[140px]">{a.value || a.name}</span>
                  </span>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-600">
                These accounts were discovered but expose no verifiable creation or activity date, so they are not placed on the timeline.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
