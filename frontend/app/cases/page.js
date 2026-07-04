/* app/cases/page.js
   REDESIGN §4.2 + §4.3 — "Investigations" registry (glass card grid, stats strip,
   plain-English copy) + "New investigation" modal. Killed: "REGISTRY", "OPERATION
   TITLE", "SEEDS", "INITIATE INVESTIGATION", the all-zero stats strip.
   PRESERVED: auth guard, api.listCases().cases, 401->login, signOut, vertex_user,
   and api.createCase(title, seeds, minor, country_filter) -> res.case_id (§1.1, §0.4).
   ADDED: "Agentic web" mode — an AI agent browses a chosen no-API OSINT site, extracts
   real data (never fabricated), and the result flows through the correlation pipeline. */
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "@/lib/api";
import GlassPanel from "@/components/ui/GlassPanel";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Label from "@/components/ui/Label";
import StatusPill from "@/components/ui/StatusPill";
import EmptyState from "@/components/ui/EmptyState";
import PivotPill from "@/components/ui/PivotPill";
import Tooltip from "@/components/ui/Tooltip";

// §4.3 identifier types — Name, Email, Phone, Username, UPI, Face URL (spec order).
const SEED_TYPES = [
  { value: "name", label: "Name", placeholder: "e.g. Arjun Mehta" },
  { value: "email", label: "Email", placeholder: "e.g. subject@mail.com" },
  { value: "phone", label: "Phone", placeholder: "e.g. +91 98765 43210" },
  { value: "username", label: "Username", placeholder: "e.g. ghost_rider99" },
  { value: "upi", label: "UPI", placeholder: "e.g. subject@oksbi" },
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

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    try { setUsername(localStorage.getItem("vertex_user") || "investigator"); } catch (_) {}
    refresh();
  }, [router]);

  async function refresh() {
    try { setCases((await api.listCases()).cases); }
    catch (e) { if (e.status === 401) { clearToken(); router.replace("/login"); } }
  }

  function signOut() {
    clearToken();
    try { localStorage.removeItem("vertex_user"); } catch (_) {}
    router.replace("/login");
  }

  const filtered = cases.filter((c) =>
    (c.title || "").toLowerCase().includes(search.toLowerCase())
  );
  const nTotal = cases.length;
  const nRunning = cases.filter((c) => c.status === "running" || c.status === "pending").length;
  const nComplete = cases.filter((c) => c.status === "complete").length;

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

      <main className="mx-auto max-w-6xl px-6 py-8">
        {/* PAGE TITLE */}
        <h1 className="text-2xl font-semibold text-slate-100">Investigations</h1>
        <p className="mt-1 text-sm text-slate-500">Your active and completed profiling cases.</p>

        {/* STATS STRIP — only when there is at least one case (§4.2) */}
        {nTotal > 0 && (
          <GlassPanel className="p-4 mt-6">
            <div className="grid grid-cols-3 gap-4">
              <StatCard n={nTotal} label="Total investigations" />
              <StatCard n={nRunning} label="In progress" color="#00f2fe" pulse={nRunning > 0} />
              <StatCard n={nComplete} label="Complete" color="#00ff88" />
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
              >
                {/* Top row: title + status */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-100 truncate">{c.title}</div>
                    {!!c.minor_involved && (
                      <span className="mt-1 inline-block text-[10px] font-mono uppercase tracking-wide text-[#ff3366] border border-[rgba(255,51,102,0.35)] rounded px-1.5 py-0.5">
                        Minor
                      </span>
                    )}
                  </div>
                  <StatusPill status={c.status} className="shrink-0" />
                </div>

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
                  <span className="text-xs font-mono text-slate-500">{fmtTime(c.created_at)}</span>
                  <Button variant="secondary" className="text-xs px-3 py-1.5">
                    Open case →
                  </Button>
                </div>
              </GlassPanel>
            ))}
          </div>
        )}
      </main>

      {showNew && (
        <NewInvestigation
          onClose={() => setShowNew(false)}
          onCreated={(id) => router.push(`/cases/${id}`)}
        />
      )}
    </div>
  );
}

function StatCard({ n, label, color = "#f8fafc", pulse = false }) {
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

function NewInvestigation({ onClose, onCreated }) {
  const [mode, setMode] = useState("standard"); // "standard" | "agentic"
  const [title, setTitle] = useState("");
  const [region, setRegion] = useState("INDIA");
  const [seeds, setSeeds] = useState([]);
  // Default to "username" — best-tested, highest-recall path (see prior note).
  const [draftType, setDraftType] = useState("username");
  const [draftValue, setDraftValue] = useState("");
  const [minor, setMinor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
      const res = await api.createCase(title || "Untitled investigation", seeds, minor, region);
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
          Enter identifiers to profile a subject, or let an AI agent browse a web tool for you.
        </p>

        {/* Agentic-web mode disabled for now (browser-agent path unreliable). Standard only. */}

        {error && (
          <div
            className="mt-4 rounded-lg px-3 py-2 text-[13px]"
            style={{ color: "#ff3366", background: "rgba(255,51,102,0.12)", border: "1px solid rgba(255,51,102,0.35)" }}
          >
            {error}
          </div>
        )}

        {/* Case title (both modes) */}
        <div className="mt-5">
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

            <div className="mt-5">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={minor}
                  onChange={(e) => setMinor(e.target.checked)}
                  style={{ accentColor: "#00f2fe" }}
                />
                <span className="text-sm text-slate-200">Subject is a minor</span>
                <Tooltip content="Enables POCSO Act protections. Identifying details will be redacted in the evidence report." />
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
                  <span className="pulse-dot" style={{ color: "#00f2fe" }} /> working…
                </div>
              )}
            </div>

            {agTask.status === "blocked" && (
              <p className="mt-3 text-[12px]" style={{ color: "#ffb703" }}>
                🚧 The site blocked automated access (CAPTCHA / login wall). No data was fabricated.
              </p>
            )}
            {agTask.status === "error" && (
              <p className="mt-3 text-[12px]" style={{ color: "#ff3366" }}>
                {agTask.error_message || "The agent could not complete the task."}
              </p>
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
