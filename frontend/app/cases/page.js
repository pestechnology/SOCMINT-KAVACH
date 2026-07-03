/* app/cases/page.js
   REDESIGN §4.2 + §4.3 — "Investigations" registry (glass card grid, stats strip,
   plain-English copy) + "New investigation" modal. Killed: "REGISTRY", "OPERATION
   TITLE", "SEEDS", "INITIATE INVESTIGATION", the all-zero stats strip.
   PRESERVED: auth guard, api.listCases().cases, 401->login, signOut, vertex_user,
   and api.createCase(title, seeds, minor, country_filter) -> res.case_id (§1.1, §0.4). */
"use client";
import { useEffect, useState } from "react";
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
const REGIONS = [
  { value: "INDIA", label: "India (Indian + Global platforms)" },
  { value: "ALL", label: "Global" },
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

function NewInvestigation({ onClose, onCreated }) {
  const [title, setTitle] = useState("");
  const [region, setRegion] = useState("INDIA");
  const [seeds, setSeeds] = useState([]);
  const [draftType, setDraftType] = useState("name");
  const [draftValue, setDraftValue] = useState("");
  const [minor, setMinor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  const placeholder = SEED_TYPES.find((t) => t.value === draftType)?.placeholder || "";
  const typeLabel = (v) => SEED_TYPES.find((t) => t.value === v)?.label || v;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <GlassPanel className="w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto relative">
        {/* close */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-200 text-lg leading-none"
          aria-label="Close"
        >
          ✕
        </button>

        {/* header */}
        <h2 className="text-lg font-semibold text-slate-100">New investigation</h2>
        <p className="mt-1 text-xs text-slate-500">
          Enter one or more identifiers to profile a subject.
        </p>

        {error && (
          <div
            className="mt-4 rounded-lg px-3 py-2 text-[13px]"
            style={{ color: "#ff3366", background: "rgba(255,51,102,0.12)", border: "1px solid rgba(255,51,102,0.35)" }}
          >
            {error}
          </div>
        )}

        {/* Field 1: Case title */}
        <div className="mt-5">
          <Label>Case title</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Sushil Kumar - phishing case #24"
          />
        </div>

        {/* Field 2: Region */}
        <div className="mt-4">
          <Label>Region</Label>
          <select value={region} onChange={(e) => setRegion(e.target.value)} className={SELECT_CLS}>
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value} className="bg-slate-900">{r.label}</option>
            ))}
          </select>
        </div>

        {/* Field 3: Identifiers */}
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

        {/* Field 4: Minor checkbox + tooltip */}
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

        {/* Footer */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="primary" onClick={begin} disabled={busy}>
            {busy ? "Starting..." : "Start investigation"}
          </Button>
        </div>
      </GlassPanel>
    </div>
  );
}
