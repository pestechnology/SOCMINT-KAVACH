// components/ui/ReiterateBar.jsx
// Re-iteration / identifier cross-pivoting — the multi-select + drag-and-drop model.
// Every account card has a checkbox; names/aliases and profile pictures in the Summary
// tab are draggable (and clickable). Everything lands in ONE staging tray, fixed above
// the floating "Re-iterate" button — that's the single persistent control, not a
// per-item button. Opening it lets you also pick from suggested identifiers derived
// from the staged selection, or type a custom one, then runs ONE combined pivot.
// Repeatable: the tray clears after a run so you can stage a fresh batch once the
// larger result set streams in.
"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Button from "./Button";
import GlassPanel from "./GlassPanel";

const SEED_TYPES = ["username", "name", "email", "phone", "upi", "url"];
const QUERY_COST_TYPES = new Set(["username", "name", "email"]);

const STRATEGY_LABELS = {
  existing_account: "already found",
  summary_pick: "from summary",
  manual: "typed",
  // facts harvested from a discovered account's bio/profile (high-value leads)
  bio_name: "real name from bio",
  bio_employer: "employer / school from bio",
  bio_link: "linked account from bio",
  // deterministic derivations from the seed string
  username_to_email_guess: "guessed email",
  username_to_name_guess: "recovered name",
  username_variant: "handle variant",
  name_to_handle_variant: "handle variant",
  name_to_email_guess: "guessed email",
  email_local_part: "username from email",
  email_to_name_guess: "recovered name",
  email_local_variant: "handle variant",
};

function estimateQueries(seeds) {
  return seeds.filter((s) => QUERY_COST_TYPES.has(s.type)).length;
}

function seedFromDrop(dataTransfer) {
  try {
    const raw = dataTransfer.getData("application/json");
    if (!raw) return null;
    const seed = JSON.parse(raw);
    if (!seed || !seed.type || !seed.value) return null;
    return seed;
  } catch {
    return null;
  }
}

function ReiterateModal({ caseId, baseSeeds, onClose, onPivotStarted, onDone }) {
  const [loadingSuggestions, setLoadingSuggestions] = useState(true);
  const [suggestions, setSuggestions] = useState([]);
  const [checkedSuggestions, setCheckedSuggestions] = useState(() => new Set());
  const [manualSeeds, setManualSeeds] = useState([]);
  const [manualType, setManualType] = useState("username");
  const [manualValue, setManualValue] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadingSuggestions(true);
    api.suggestPivot(caseId, baseSeeds.map(({ type, value }) => ({ type, value })))
      .then((res) => { if (!cancelled) setSuggestions(res.suggestions || []); })
      .catch((e) => { if (!cancelled) setError(e.message || "Failed to load suggestions"); })
      .finally(() => { if (!cancelled) setLoadingSuggestions(false); });
    return () => { cancelled = true; };
  }, [caseId, baseSeeds]);

  const toggleSuggestion = (i) => {
    setCheckedSuggestions((s) => {
      const next = new Set(s);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const addManual = () => {
    const value = manualValue.trim();
    if (!value) return;
    setManualSeeds((m) => [...m, { type: manualType, value, strategy: "manual" }]);
    setManualValue("");
  };

  const removeManual = (i) => setManualSeeds((m) => m.filter((_, idx) => idx !== i));

  const finalSeeds = [
    ...baseSeeds,
    ...suggestions.filter((_, i) => checkedSuggestions.has(i)),
    ...manualSeeds,
  ];
  const estimatedQueries = estimateQueries(finalSeeds);

  async function run() {
    if (finalSeeds.length === 0) return;
    setRunning(true);
    setError("");
    try {
      await api.runPivot(caseId, finalSeeds);
      onPivotStarted?.();
      onDone();
    } catch (e) {
      setError(e.message || "Failed to start pivot");
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <GlassPanel
        className="w-full max-w-2xl max-h-[80vh] overflow-y-auto p-4 bg-[#0b1220]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-slate-100">⤴ Re-iterate</span>
          <button type="button" onClick={onClose} className="text-xs text-slate-500 hover:text-slate-300">✕</button>
        </div>

        {error && <div className="text-xs mb-2" style={{ color: "var(--tone-rose)" }}>{error}</div>}

        {/* Base selection — what was staged in the tray */}
        <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-1.5">
          Staged ({baseSeeds.length})
        </div>
        <div className="flex flex-wrap gap-1.5 mb-4">
          {baseSeeds.map((s, i) => (
            <span key={s.key || `${s.type}-${s.value}-${i}`} className="text-[11px] font-mono text-cyan-300 border border-cyan-400/30 bg-cyan-400/10 rounded px-2 py-0.5">
              {s.value}
            </span>
          ))}
          {baseSeeds.length === 0 && (
            <span className="text-xs text-slate-500">Nothing staged yet — add identifiers manually below.</span>
          )}
        </div>

        {/* Suggested identifiers derived from the staged selection */}
        <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-1.5">
          Suggested identifiers
        </div>
        {loadingSuggestions && <div className="text-xs text-slate-500 mb-3">Deriving candidates…</div>}
        {!loadingSuggestions && suggestions.length === 0 && (
          <div className="text-xs text-slate-500 mb-3">No plausible identifiers could be derived from the staged selection.</div>
        )}
        {!loadingSuggestions && suggestions.length > 0 && (
          <div className="space-y-1 max-h-40 overflow-y-auto pr-1 mb-3">
            {suggestions.map((s, i) => (
              <label key={`${s.type}-${s.value}-${i}`} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={checkedSuggestions.has(i)}
                  onChange={() => toggleSuggestion(i)}
                  className="accent-cyan-400"
                />
                <span className="text-[10px] font-mono uppercase text-slate-500 shrink-0">{s.type}</span>
                <span className="font-mono truncate">{s.value}</span>
                <span className="text-slate-600 shrink-0">· {STRATEGY_LABELS[s.strategy] || s.strategy}</span>
                <span className="text-slate-700 shrink-0">from {s.from_value}</span>
              </label>
            ))}
          </div>
        )}

        {/* Manually typed identifiers */}
        <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-1.5">
          Add your own
        </div>
        <div className="flex items-center gap-2 mb-2">
          <select
            value={manualType}
            onChange={(e) => setManualType(e.target.value)}
            className="text-xs bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-300"
          >
            {SEED_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input
            type="text"
            value={manualValue}
            onChange={(e) => setManualValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addManual(); } }}
            placeholder="type a name, handle, email…"
            className="flex-1 text-xs bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200 placeholder:text-slate-600"
          />
          <Button variant="secondary" onClick={addManual} className="text-xs px-3 py-1.5">Add</Button>
        </div>
        {manualSeeds.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {manualSeeds.map((s, i) => (
              <span key={`${s.type}-${s.value}-${i}`} className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-300 border border-slate-700 bg-slate-900/60 rounded px-2 py-0.5">
                {s.type}:{s.value}
                <button type="button" onClick={() => removeManual(i)} className="text-slate-500 hover:text-slate-200">✕</button>
              </span>
            ))}
          </div>
        )}

        <div className="mt-2 text-[11px] text-slate-500 font-mono">
          Will use ~{estimatedQueries} Serper {estimatedQueries === 1 ? "query" : "queries"} · {finalSeeds.length} total identifier{finalSeeds.length === 1 ? "" : "s"}
        </div>

        <div className="mt-3">
          <Button
            variant="primary"
            onClick={run}
            disabled={running || finalSeeds.length === 0}
            className="text-xs px-4 py-2 w-full"
          >
            {running ? "Starting…" : `Run combined re-iteration (${finalSeeds.length})`}
          </Button>
        </div>
      </GlassPanel>
    </div>
  );
}

export default function ReiterateBar({ caseId, stagedSeeds, onDropSeed, onRemoveSeed, onClear, onPivotStarted }) {
  const [open, setOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const count = stagedSeeds.length;
  const hasSelection = count > 0;

  return (
    <>
      {/* Staging tray — a PERMANENT drop target, always visible so drag-and-drop from
          the Summary tab (names/aliases, profile pictures) is discoverable even before
          anything is staged. Account checkboxes land here too. */}
      <div
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const seed = seedFromDrop(e.dataTransfer);
          if (seed) onDropSeed(seed);
        }}
        className={`
          fixed bottom-24 right-6 z-40 w-72 max-h-56 overflow-y-auto rounded-xl p-3
          border-2 border-dashed transition-colors duration-150
          ${dragOver ? "border-cyan-400 bg-cyan-400/10" : "border-slate-700 bg-[#0b1220]/90 backdrop-blur-md"}
        `}
      >
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] font-mono uppercase tracking-wide text-slate-400">Re-iterate staging</span>
          {hasSelection && (
            <button type="button" onClick={onClear} className="text-[10px] text-slate-500 hover:text-slate-300">clear</button>
          )}
        </div>
        {!hasSelection ? (
          <div className="text-[11px] text-slate-500 leading-relaxed">
            Drag names, aliases, or profile pictures here from the Summary tab — or check accounts in the list.
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {stagedSeeds.map((s) => (
              <span key={s.key} className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-300 border border-cyan-400/30 bg-cyan-400/10 rounded px-2 py-0.5">
                <span className="text-[9px] uppercase text-cyan-500">{s.type}</span>
                <span className="truncate max-w-[9rem]">{s.label || s.value}</span>
                <button type="button" onClick={() => onRemoveSeed(s.key)} className="text-cyan-500 hover:text-cyan-200">✕</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* The single persistent trigger, below the tray */}
      <button
        type="button"
        onClick={() => hasSelection && setOpen(true)}
        disabled={!hasSelection}
        className={`
          fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full px-5 py-3
          text-sm font-semibold shadow-lg transition-all duration-200
          ${hasSelection
            ? "text-black bg-gradient-to-r from-cyan-400 to-purple-400 shadow-[0_4px_24px_-4px_rgba(107,169,189,0.6)] hover:-translate-y-0.5 cursor-pointer"
            : "text-slate-500 bg-slate-800/70 border border-slate-700 cursor-not-allowed opacity-70"}
        `}
      >
        <span aria-hidden>⤴</span>
        {hasSelection ? `Re-iterate (${count})` : "Re-iterate"}
      </button>

      {open && (
        <ReiterateModal
          caseId={caseId}
          baseSeeds={stagedSeeds}
          onClose={() => setOpen(false)}
          onPivotStarted={onPivotStarted}
          onDone={() => { setOpen(false); onClear(); }}
        />
      )}
    </>
  );
}
