/* components/ui/TimelineGraph.jsx
   The "timeline graph" — an account-wise swimlane on a shared time axis, grouped by
   confidence so it reads the same way as the rest of the case room.

   Layout, top → bottom:
     • PERSON SUMMARY  — headline facts about the confirmed identity (span, oldest
       account, last active, count). The one thing you read in half a second.
     • CREATION DENSITY — bars showing when accounts appeared; a tall bar is a burst
       of accounts created together (a life event, or one person spinning up profiles).
     • YEAR AXIS       — the shared horizontal scale every lane below is measured on.
     • STRONG matches  — always open. The clean core of who this person is.
     • POSSIBLE matches— collapsible (auto-open when there are no strong matches).
     • NOT LINKED      — collapsible, closed by default; keeps "earliest online
       presence" reachable without cluttering the confirmed story.
     • DATA EXPOSURE   — a separate band of breach events on the same axis (breaches
       are leak events, not the person's accounts, so they don't share the lanes).

   Every section shares ONE domain/axis, so lanes line up in time across sections even
   when some are collapsed. All colors are paired with a glyph SHAPE + text label, so
   the graph survives colorblindness and grayscale (tier palette validated on the dark
   surface via the dataviz color checks). Positioned purely by % of the domain → fully
   responsive, no measuring. */
"use client";
import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import PlatformLogo from "./PlatformLogo";
import {
  yearTicks, pctOf, creationBins, tierStyle, BREACH_COLOR, groupByTier, personSummary,
  formatFullDate, formatTime, formatMonthYear, durationHuman, relativeTime,
} from "@/lib/timeline";

const LABEL_W = 184; // px — account-label gutter; the time track is the rest (1fr)
const GRID = { display: "grid", gridTemplateColumns: `${LABEL_W}px 1fr` };

/* ── event-kind glyphs (the secondary encoding, so kind ≠ color-only) ── */
function Marker({ ev, color, onEnter, onLeave }) {
  const c = ev.kind === "breach" ? BREACH_COLOR : color;
  const common = {
    className: "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 cursor-default transition-transform duration-150 hover:scale-[1.35] z-10",
    style: { left: `${ev._pct}%` },
    onMouseEnter: (e) => onEnter(e, ev),
    onMouseMove: (e) => onEnter(e, ev),
    onMouseLeave: onLeave,
  };
  if (ev.kind === "created")
    return <span {...common}><span className="block w-3 h-3 rounded-full border-2"
      style={{ borderColor: c, background: "var(--tl-surface,#0b1220)", boxShadow: `0 0 0 3px ${c}22, 0 0 8px ${c}66` }} /></span>;
  if (ev.kind === "archived")
    return <span {...common}><span className="block w-2.5 h-2.5 rounded-[3px]"
      style={{ background: c, boxShadow: `0 0 0 3px ${c}22, 0 0 6px ${c}55` }} /></span>;
  if (ev.kind === "breach")
    return <span {...common}><span className="block w-[11px] h-[11px] rotate-45"
      style={{ background: c, boxShadow: `0 0 8px ${c}aa` }} /></span>;
  return <span {...common}><span className="block w-2 h-2 rounded-full"
    style={{ background: c, boxShadow: `0 0 5px ${c}88` }} /></span>;
}

function GlyphSample({ kind }) {
  if (kind === "created") return <span className="inline-block w-[10px] h-[10px] rounded-full border-2 border-current" />;
  if (kind === "archived") return <span className="inline-block w-2 h-2 rounded-[2px] bg-current" />;
  if (kind === "breach") return <span className="inline-block w-2 h-2 rotate-45 bg-current" />;
  return <span className="inline-block w-1.5 h-1.5 rounded-full bg-current" />;
}

/* ── one account lane ── */
function Lane({ a, domain, onEnter, onLeave, onSelectAccount }) {
  const ts = tierStyle(a.tier);
  const laneColor = a.isBreach ? BREACH_COLOR : ts.color;
  const firstPct = pctOf(a.firstDate, domain);
  const lastPct = pctOf(a.lastDate, domain);
  const enter = (e, ev) => onEnter(e, a, ev);
  return (
    <div style={GRID} className="group items-center rounded-lg hover:bg-white/[0.03] transition-colors">
      <button
        onClick={() => onSelectAccount && onSelectAccount(a.entity_id)}
        className="flex items-center gap-2 pr-3 py-1.5 min-w-0 text-left"
        title={a.value}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: laneColor, boxShadow: `0 0 5px ${laneColor}` }} />
        <PlatformLogo platform={a.platform} width={16} height={16} className="shrink-0" />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5">
            <span className="text-[12px] text-slate-200 truncate leading-tight group-hover:text-white transition-colors">{a.value || a.name}</span>
            {a.exactMatch && <span className="text-[8px] leading-none font-mono uppercase tracking-wider text-cyan-300 border border-cyan-400/40 bg-cyan-400/10 rounded px-1 py-0.5 shrink-0">★</span>}
          </span>
          <span className="block text-[9px] font-mono uppercase tracking-wide text-slate-500 truncate leading-tight">{a.name}</span>
        </span>
      </button>
      <div className="relative h-7">
        {a.lastDate > a.firstDate && (
          <div className="absolute top-1/2 -translate-y-1/2 h-[3px] rounded-full"
            style={{ left: `${firstPct}%`, width: `${Math.max(0, lastPct - firstPct)}%`,
                     background: `linear-gradient(to right, ${laneColor}, ${laneColor}55)`,
                     boxShadow: `0 0 6px ${laneColor}44` }} />
        )}
        {a.events.map((ev, i) => { ev._pct = pctOf(ev.date, domain); return <Marker key={i} ev={ev} color={laneColor} onEnter={enter} onLeave={onLeave} />; })}
      </div>
    </div>
  );
}

/* ── shared vertical gridlines behind a lane group ── */
function GridLines({ ticks, nowPct }) {
  return (
    <div className="absolute inset-0 pointer-events-none" style={{ left: LABEL_W }}>
      {ticks.map((t) => <div key={t.year} className="absolute top-0 bottom-0 border-l border-slate-800/50" style={{ left: `${t.pct}%` }} />)}
      <div className="absolute top-0 bottom-0 border-l border-cyan-500/25" style={{ left: `${nowPct}%` }} />
    </div>
  );
}

/* ── "no date" chips: accounts the platform publishes no date for (Instagram, Threads,
   YouTube…). They can't sit on the axis, but they must NOT vanish — especially when
   they're the strong matches — so we list them honestly under their tier. ── */
function UndatedChips({ accounts, color, onSelectAccount }) {
  if (!accounts.length) return null;
  return (
    <div style={GRID} className="items-start mt-1">
      <div className="pr-3 pt-1 text-right text-[9px] font-mono uppercase tracking-wider text-slate-600 leading-tight">No date<br />published</div>
      <div className="flex flex-wrap gap-1.5 py-1">
        {accounts.map((a) => (
          <button key={a.entity_id} onClick={() => onSelectAccount && onSelectAccount(a.entity_id)}
            title={`${a.name} · ${a.value} — no date available to place on the timeline`}
            className="inline-flex items-center gap-1.5 text-[11px] text-slate-300 bg-slate-900/70 border rounded-full pl-1.5 pr-2.5 py-1 hover:bg-slate-800 transition-colors"
            style={{ borderColor: `${color}33` }}>
            <PlatformLogo platform={a.platform} width={13} height={13} />
            <span className="truncate max-w-[130px]">{a.value || a.name}</span>
            {a.exactMatch && <span className="text-[8px] leading-none font-mono text-cyan-300">★</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── a collapsible confidence section (dated lanes + undated chips) ── */
function Section({ title, color, accounts, undated = [], open, onToggle, collapsible, ticks, nowPct, onSelectAccount, ...laneProps }) {
  if (!accounts.length && !undated.length) return null;
  const total = accounts.length + undated.length;
  const header = (
    <div className="flex items-center gap-2 py-1.5">
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
      <span className="text-[11px] font-mono uppercase tracking-wider" style={{ color }}>{title}</span>
      <span className="text-[10px] font-mono text-slate-500 border border-slate-700 rounded-full px-1.5 leading-tight">{total}</span>
      {collapsible && <span className="ml-auto text-slate-500 text-xs">{open ? "▾" : "▸"}</span>}
    </div>
  );
  const body = (
    <div>
      {accounts.length > 0 && (
        <div className="relative">
          <GridLines ticks={ticks} nowPct={nowPct} />
          <div className="relative">{accounts.map((a) => <Lane key={a.entity_id} a={a} ticks={ticks} onSelectAccount={onSelectAccount} {...laneProps} />)}</div>
        </div>
      )}
      <UndatedChips accounts={undated} color={color} onSelectAccount={onSelectAccount} />
    </div>
  );
  return (
    <div className="mt-2 first:mt-0">
      {collapsible ? (
        <button onClick={onToggle} className="w-full text-left rounded-md px-1 -mx-1 hover:bg-white/[0.02] transition-colors">{header}</button>
      ) : <div className="px-1 -mx-1">{header}</div>}
      {/* smooth height animation via grid-rows 0fr → 1fr */}
      <div className="grid transition-[grid-template-rows] duration-300 ease-out" style={{ gridTemplateRows: open ? "1fr" : "0fr" }}>
        <div className="overflow-hidden">{body}</div>
      </div>
    </div>
  );
}

/* ── person-summary stat pills ── */
function SummaryPill({ icon, value, label, accent }) {
  return (
    <div className="relative rounded-xl border border-slate-800 bg-gradient-to-br from-slate-900/80 to-slate-900/30 px-3.5 py-2.5 overflow-hidden">
      <span className="absolute inset-x-0 top-0 h-px" style={{ background: `linear-gradient(to right, transparent, ${accent}77, transparent)` }} />
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-500">
        <span className="text-xs" style={{ filter: `drop-shadow(0 0 4px ${accent}88)` }}>{icon}</span>{label}
      </div>
      <div className="mt-1 text-[15px] font-semibold text-slate-100 truncate leading-tight">{value}</div>
    </div>
  );
}

export default function TimelineGraph({ model, hideBreaches = false, onSelectAccount }) {
  const [tip, setTip] = useState(null);
  const { domain, now } = model;
  const ticks = useMemo(() => yearTicks(domain), [domain]);
  const nowPct = pctOf(now, domain);

  // Dated accounts become lanes; undated (no scrapable date — Instagram/Threads/etc.)
  // become "no date" chips within their own tier, so nothing — least of all a strong
  // match — silently disappears just because its platform publishes no date.
  const groups = useMemo(() => groupByTier(model.accounts), [model.accounts]);
  const undatedGroups = useMemo(() => groupByTier(model.undated), [model.undated]);
  const strongTotal = groups.strong.length + undatedGroups.strong.length;
  const possibleTotal = groups.possible.length + undatedGroups.possible.length;

  const summary = useMemo(
    () => personSummary([...groups.strong, ...undatedGroups.strong, ...groups.possible, ...undatedGroups.possible], now)
       || personSummary([...groups.notLinked, ...undatedGroups.notLinked], now),
    [groups, undatedGroups, now]
  );

  // Possible auto-opens when there's no strong section; not-linked opens only if it's
  // the only thing we have. (Users can toggle either afterwards.)
  const [possibleOpen, setPossibleOpen] = useState(strongTotal === 0);
  const [notLinkedOpen, setNotLinkedOpen] = useState(strongTotal === 0 && possibleTotal === 0);

  // Anchor the card to the DOT (its bounding rect), not the mouse, so it sits centered
  // over the marker instead of chasing the cursor. Using currentTarget's rect also keeps
  // it steady while the pointer moves within the marker.
  const onEnter = (e, account, ev) => {
    const r = e.currentTarget.getBoundingClientRect();
    setTip({ cx: r.left + r.width / 2, top: r.top, bottom: r.bottom, account, ev });
  };
  const onLeave = () => setTip(null);
  const laneProps = { domain, onEnter, onLeave, onSelectAccount };

  const breaches = hideBreaches ? [] : groups.breaches;
  const densityAccounts = [...groups.strong, ...groups.possible, ...groups.notLinked];
  const { bins, max: binMax, binWidthPct } = useMemo(() => creationBins(densityAccounts, domain), [densityAccounts, domain]);

  if (!model.accounts.length && !model.undated.length) {
    return <div className="py-10 text-center text-sm text-slate-500">No accounts to place on the timeline yet.</div>;
  }

  return (
    <div className="select-none">
      {/* ── PERSON SUMMARY ── */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-5">
          <SummaryPill icon="🕐" accent="#22d3ee" value={summary.hasDates ? summary.span : "no dates"} label={summary.hasDates ? `${summary.earliestYear}–${summary.latestYear}` : "on record"} />
          <SummaryPill icon="🎂" accent="#00ff88" value={summary.hasDates ? summary.oldestPlatform : "—"} label={summary.hasDates ? `earliest · ${summary.earliestYear}` : "earliest unknown"} />
          <SummaryPill icon="⚡" accent="#ffb703" value={summary.hasDates ? summary.lastActive : "—"} label="last activity" />
          <SummaryPill icon="👤" accent="#a78bfa" value={`${summary.count} account${summary.count === 1 ? "" : "s"}`} label={summary.busiestYear ? `most active ${summary.busiestYear}` : "confirmed identity"} />
        </div>
      )}

      {/* ── CREATION DENSITY ── */}
      <div style={GRID} className="items-end">
        <div className="pr-3 pb-1 text-right text-[10px] font-mono uppercase tracking-wider text-slate-500 leading-tight">Accounts<br />created</div>
        <div className="relative h-11 border-b border-slate-700/70">
          {bins.map((v, i) => v > 0 ? (
            <div key={i} className="absolute bottom-0 rounded-t-[2px]" title={`${v} account${v === 1 ? "" : "s"} created here`}
              style={{ left: `${i * binWidthPct}%`, width: `${binWidthPct}%`, height: `${binMax ? (v / binMax) * 100 : 0}%`,
                       background: "linear-gradient(to top, rgba(34,211,238,0.15), rgba(34,211,238,0.9))",
                       boxShadow: "0 0 8px rgba(34,211,238,0.35)", minHeight: 4 }} />
          ) : null)}
        </div>
      </div>

      {/* ── YEAR AXIS ── */}
      <div style={GRID}>
        <div />
        <div className="relative h-6">
          {ticks.map((t) => (
            <span key={t.year} className="absolute top-1 -translate-x-1/2 text-[10px] font-mono text-slate-500 whitespace-nowrap" style={{ left: `${t.pct}%` }}>{t.year}</span>
          ))}
          <span className="absolute top-1 -translate-x-1/2 text-[9px] font-mono text-cyan-400/90 whitespace-nowrap" style={{ left: `${nowPct}%` }}>now</span>
        </div>
      </div>

      {/* ── LANE SECTIONS (scrolls if tall) ── */}
      <div className="mt-1 max-h-[48vh] overflow-y-auto custom-scrollbar pr-1">
        <Section title="Strong matches" color="#00ff88" accounts={groups.strong} undated={undatedGroups.strong}
          open collapsible={false} ticks={ticks} nowPct={nowPct} {...laneProps} />
        <Section title="Possible matches" color="#ffb703" accounts={groups.possible} undated={undatedGroups.possible}
          open={possibleOpen} onToggle={() => setPossibleOpen((v) => !v)} collapsible ticks={ticks} nowPct={nowPct} {...laneProps} />
        <Section title="Not linked" color="#64748b" accounts={groups.notLinked} undated={undatedGroups.notLinked}
          open={notLinkedOpen} onToggle={() => setNotLinkedOpen((v) => !v)} collapsible ticks={ticks} nowPct={nowPct} {...laneProps} />

        {/* ── DATA EXPOSURE BAND ── */}
        {breaches.length > 0 && (
          <div className="mt-4 pt-3 border-t border-red-500/20">
            <div className="flex items-center gap-2 py-1.5">
              <span className="w-2.5 h-2.5 rotate-45 shrink-0" style={{ background: BREACH_COLOR, boxShadow: `0 0 6px ${BREACH_COLOR}` }} />
              <span className="text-[11px] font-mono uppercase tracking-wider" style={{ color: BREACH_COLOR }}>Data exposure</span>
              <span className="text-[10px] font-mono text-slate-500 border border-slate-700 rounded-full px-1.5 leading-tight">{breaches.reduce((s, b) => s + b.events.length, 0)}</span>
            </div>
            <div className="relative">
              <GridLines ticks={ticks} nowPct={nowPct} />
              <div style={GRID} className="relative items-center rounded-lg hover:bg-white/[0.03]">
                <div className="pr-3 text-[11px] text-slate-400 truncate">Breaches on record</div>
                <div className="relative h-8">
                  {breaches.flatMap((b) => b.events.map((ev, i) => {
                    ev._pct = pctOf(ev.date, domain);
                    return <Marker key={`${b.entity_id}-${i}`} ev={{ ...ev, kind: "breach" }} color={BREACH_COLOR}
                      onEnter={(e, x) => onEnter(e, b, x)} onLeave={onLeave} />;
                  }))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── LEGEND ── */}
      <div className="mt-4 pt-3 border-t border-slate-800 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px]">
        <span className="text-slate-500 font-mono uppercase tracking-wider text-[10px]">Event</span>
        {["created", "activity", "archived", "breach"].map((k) => (
          <span key={k} className="flex items-center gap-1.5" style={{ color: k === "breach" ? BREACH_COLOR : "#94a3b8" }}>
            <GlyphSample kind={k} />
            <span className="text-slate-400">{k === "created" ? "Created" : k === "archived" ? "Last seen" : k === "breach" ? "Breach" : "Activity"}</span>
          </span>
        ))}
        <span className="ml-auto text-[10px] font-mono text-slate-600">line = time an account was active</span>
      </div>

      {/* ── TOOLTIP ── centered on the DOT (above it, flipping below near the top), and
          portaled to <body> so no transformed ancestor can throw off its fixed position.
          Wears the match tier's color (green strong / amber possible / gray not-linked /
          red breach) as its outline + glow. ── */}
      {tip && typeof document !== "undefined" && createPortal((() => {
        const strong = tip.account.exactMatch || tip.account.tier === "HIGH";
        const tc = tip.account.isBreach ? BREACH_COLOR
          : strong ? "#00ff88" : tip.account.tier === "MEDIUM" ? "#ffb703" : "#64748b";
        const W = 288, H = 172, GAP = 12;
        const vw = window.innerWidth, vh = window.innerHeight;
        let left = Math.max(8, Math.min(tip.cx - W / 2, vw - W - 8));
        let top = tip.top - H - GAP;                       // prefer above the dot
        const below = top < 8;
        if (below) top = Math.min(tip.bottom + GAP, vh - H - 8);
        top = Math.max(8, top);
        // little pointer, centered on the dot, clamped to the card
        const arrowLeft = Math.max(12, Math.min(tip.cx - left, W - 12));
        return (
          <div className="fixed z-[100] pointer-events-none rounded-xl border-2 bg-slate-900/95 backdrop-blur px-3.5 py-2.5 text-xs"
            style={{ left, top, width: W, borderColor: tc, boxShadow: `0 8px 28px rgba(0,0,0,0.55), 0 0 20px ${tc}44` }}>
            <span className="absolute w-2.5 h-2.5 rotate-45 bg-slate-900 border-2"
              style={{ left: arrowLeft - 5, [below ? "top" : "bottom"]: -7, borderColor: tc,
                       borderTopColor: below ? tc : "transparent", borderLeftColor: below ? tc : "transparent",
                       borderRightColor: below ? "transparent" : tc, borderBottomColor: below ? "transparent" : tc }} />
            <div className="flex items-center gap-2 mb-1.5 pb-1.5 border-b border-slate-800">
              <PlatformLogo platform={tip.account.platform} width={16} height={16} />
              <span className="font-semibold text-slate-100">{tip.account.name}</span>
              <span className="text-slate-500 truncate">{tip.account.value}</span>
              <span className="ml-auto w-2 h-2 rounded-full shrink-0" style={{ background: tc, boxShadow: `0 0 6px ${tc}` }} />
            </div>
            <div className="flex items-center gap-1.5" style={{ color: tip.ev.kind === "breach" ? BREACH_COLOR : "#cbd5e1" }}>
              <GlyphSample kind={tip.ev.kind} /><span className="text-slate-200">{tip.ev.label}</span>
            </div>
            {tip.ev.kind === "breach" && tip.ev.detail && <div className="text-slate-400 mt-0.5">{tip.ev.detail}</div>}
            {tip.ev.date && (
              <div className="text-slate-400 mt-1">
                {formatFullDate(tip.ev.date)}{tip.ev.hasTime ? ` · ${formatTime(tip.ev.date)}` : ""}
                <span className="text-slate-500"> · {relativeTime(tip.ev.date, now)}</span>
              </div>
            )}
            {tip.ev.kind === "created" && tip.account.lastDate && (
              <div className="text-[10px] text-slate-500 mt-1 font-mono">age {durationHuman(tip.ev.date, now)} · active {durationHuman(tip.account.firstDate, tip.account.lastDate) || "—"}</div>
            )}
          </div>
        );
      })(), document.body)}
    </div>
  );
}
