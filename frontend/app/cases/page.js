/* app/cases/page.js
   CHANGED: full rewrite to the "Investigation Registry" — top nav, mono stats strip,
   row-based case table (no card grid), and an "Initiate Investigation" modal.
   DECISION: FACE removed everywhere; case numbers derived from display index; username
   read from localStorage('vertex_user'); api.listCases/createCase used unchanged. */
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "@/lib/api";

const SEED_TYPES = [
  { value: "username", label: "USERNAME", placeholder: "e.g. ghost_rider99" },
  { value: "email", label: "EMAIL", placeholder: "e.g. subject@mail.com" },
  { value: "phone", label: "PHONE", placeholder: "e.g. +91 98765 43210" },
  { value: "upi", label: "UPI", placeholder: "e.g. subject@oksbi" },
  { value: "name", label: "NAME", placeholder: "e.g. Arjun Mehta" },
  { value: "url", label: "URL", placeholder: "e.g. https://instagram.com/subject" },
]; // NOTE: FACE intentionally excluded

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const STATUS_BAR = { complete: "#27AE60", running: "#D4900A", pending: "#D4900A", error: "#C0392B" };
const STATUS_TEXT = {
  complete: { t: "COMPLETE", c: "tier-complete" },
  running: { t: "RUNNING", c: "tier-high" },
  pending: { t: "PENDING", c: "tier-reject" },
  error: { t: "ERROR", c: "tier-error" },
};

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
    catch (e) { if (String(e).includes("401")) { clearToken(); router.replace("/login"); } }
  }

  function signOut() {
    clearToken();
    try { localStorage.removeItem("vertex_user"); } catch (_) {}
    router.replace("/login");
  }

  const filtered = cases.filter((c) => (c.title || "").toLowerCase().includes(search.toLowerCase()));
  const nRunning = cases.filter((c) => c.status === "running" || c.status === "pending").length;
  const nComplete = cases.filter((c) => c.status === "complete").length;

  return (
    <div className="min-h-screen bg-ink">
      {/* NAV */}
      <nav className="bg-surface border-b border-edge flex items-center justify-between" style={{ padding: "10px 20px" }}>
        <div className="flex items-center">
          <span className="display text-head" style={{ fontSize: 18, fontWeight: 600 }}>VERTEX<span className="text-amber">.</span></span>
          <span style={{ width: 1, height: 16, background: "#2A3148", margin: "0 16px" }} />
          <span className="mono text-dim" style={{ fontSize: 10, letterSpacing: "0.1em" }}>INVESTIGATION REGISTRY</span>
        </div>
        <div className="flex items-center" style={{ gap: 16 }}>
          <span className="mono text-dim" style={{ fontSize: 10 }}>{username}</span>
          <button onClick={signOut} className="mono text-crimson" style={{ fontSize: 10 }}>Sign out</button>
          <AmberButton onClick={() => setShowNew(true)} label="OPEN CASE" />
        </div>
      </nav>

      {/* STATS STRIP */}
      <div className="flex border-b border-edge bg-surface">
        <Stat n={cases.length} label="CASES" />
        <Stat n={nRunning} label="RUNNING" color="tier-high" />
        <Stat n={nComplete} label="COMPLETE" color="tier-complete" />
      </div>

      {/* SEARCH */}
      <div className="flex items-center border-b border-edge" style={{ padding: "10px 24px", gap: 12 }}>
        <input
          className="mono bg-lifted text-head flex-1"
          placeholder="Filter by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ border: "1px solid #2A3148", borderRadius: 2, fontSize: 12, padding: "7px 10px", outline: "none" }}
          onFocus={(e) => (e.currentTarget.style.borderColor = "#D4900A")}
          onBlur={(e) => (e.currentTarget.style.borderColor = "#2A3148")}
        />
      </div>

      {/* TABLE */}
      <div>
        {filtered.length === 0 ? (
          <div className="text-center" style={{ padding: "80px 0" }}>
            <div className="mono text-dim" style={{ fontSize: 11, letterSpacing: "0.12em" }}>NO CASES FOUND</div>
            <div className="display text-dim" style={{ fontSize: 13, marginTop: 8 }}>Open a new case to begin an investigation.</div>
          </div>
        ) : (
          filtered.map((c, i) => {
            const st = STATUS_TEXT[c.status] || { t: (c.status || "—").toUpperCase(), c: "tier-reject" };
            const seeds = (c.seeds || []).filter((s) => s.type !== "face");
            return (
              <div
                key={c.case_id}
                onClick={() => router.push(`/cases/${c.case_id}`)}
                className="case-row flex items-center border-b border-edge cursor-pointer"
                style={{ padding: "12px 24px", gap: 16 }}
              >
                <span style={{ width: 3, height: 36, borderRadius: 1, flexShrink: 0, background: STATUS_BAR[c.status] || "#4A5568" }} />
                <span className="mono text-amber" style={{ fontSize: 12, fontWeight: 500, minWidth: 52 }}>
                  #{String(i + 1).padStart(3, "0")}
                </span>
                <div className="flex flex-col" style={{ flex: 1, minWidth: 0 }}>
                  <span className="display text-head" style={{ fontSize: 14, fontWeight: 500 }}>{c.title}</span>
                  <div className="flex flex-wrap" style={{ gap: 4, marginTop: 3 }}>
                    {seeds.map((s, k) => (
                      <span key={k} className="mono text-dim" style={{ fontSize: 9, border: "0.5px solid #2A3148", borderRadius: 2, padding: "1px 5px" }}>
                        [{(s.type || "").toUpperCase()}]
                      </span>
                    ))}
                  </div>
                </div>
                {!!c.minor_involved && (
                  <span className="mono text-crimson" style={{ fontSize: 8, border: "0.5px solid #C0392B", borderRadius: 2, padding: "1px 5px", letterSpacing: "0.08em" }}>
                    MINOR
                  </span>
                )}
                {c.status === "complete" && (
                  <span className="mono text-dim" style={{ fontSize: 10 }}>{c.account_count ?? 0} accounts</span>
                )}
                <span className={`mono ${st.c}`} style={{ fontSize: 9, letterSpacing: "0.08em", textAlign: "right" }}>{st.t}</span>
                <span className="mono text-dim" style={{ fontSize: 9, textAlign: "right", minWidth: 96 }}>{fmtTime(c.created_at)}</span>
              </div>
            );
          })
        )}
      </div>

      {showNew && <NewInvestigation onClose={() => setShowNew(false)} onCreated={(id) => router.push(`/cases/${id}`)} />}
    </div>
  );
}

function Stat({ n, label, color = "text-head" }) {
  return (
    <div style={{ padding: "10px 20px", borderRight: "1px solid #2A3148" }}>
      <div className={`mono ${color}`} style={{ fontSize: 20, fontWeight: 500 }}>{n}</div>
      <div className="mono text-dim" style={{ fontSize: 8, letterSpacing: "0.1em", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function AmberButton({ onClick, label }) {
  return (
    <button
      onClick={onClick}
      className="mono"
      style={{ border: "1px solid #D4900A", color: "#D4900A", background: "transparent", fontSize: 10, letterSpacing: "0.08em", padding: "6px 14px", borderRadius: 2 }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(212,144,10,0.10)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      {label}
    </button>
  );
}

function NewInvestigation({ onClose, onCreated }) {
  const [title, setTitle] = useState("");
  const [seeds, setSeeds] = useState([]);
  const [draftType, setDraftType] = useState("username");
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
      if (!seeds.length) throw new Error("Add at least one identifier");
      const res = await api.createCase(title || "Untitled investigation", seeds, minor);
      onCreated(res.case_id);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  const placeholder = SEED_TYPES.find((t) => t.value === draftType)?.placeholder || "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(14,17,23,0.80)" }}>
      <div className="bg-surface" style={{ border: "1px solid #2A3148", maxWidth: 480, width: "92%" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #2A3148" }}>
          <span className="mono text-head" style={{ fontSize: 10, letterSpacing: "0.12em" }}>INITIATE INVESTIGATION</span>
        </div>

        <div className="flex flex-col" style={{ padding: 20, gap: 16 }}>
          {error && <div className="display text-crimson" style={{ fontSize: 11, background: "rgba(192,57,43,0.15)", borderLeft: "2px solid #C0392B", padding: "8px 12px" }}>{error}</div>}

          <div>
            <label className="mono text-dim block mb-1" style={{ fontSize: 9, letterSpacing: "0.1em" }}>OPERATION TITLE</label>
            <input className="mono bg-lifted text-head w-full" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Investment fraud — complaint #1423"
              style={{ border: "1px solid #2A3148", borderRadius: 2, fontSize: 13, padding: "10px 12px", outline: "none" }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "#D4900A")} onBlur={(e) => (e.currentTarget.style.borderColor = "#2A3148")} />
          </div>

          <div>
            <label className="mono text-dim block mb-2" style={{ fontSize: 9, letterSpacing: "0.1em" }}>SEEDS</label>
            <div className="flex" style={{ gap: 6 }}>
              <select value={draftType} onChange={(e) => setDraftType(e.target.value)} className="mono bg-lifted text-head"
                style={{ border: "1px solid #2A3148", borderRadius: 2, fontSize: 11, padding: "8px 6px", outline: "none", width: 110 }}>
                {SEED_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <input className="mono bg-lifted text-head flex-1" value={draftValue} placeholder={placeholder}
                onChange={(e) => setDraftValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSeed(); } }}
                style={{ border: "1px solid #2A3148", borderRadius: 2, fontSize: 12, padding: "8px 10px", outline: "none" }}
                onFocus={(e) => (e.currentTarget.style.borderColor = "#D4900A")} onBlur={(e) => (e.currentTarget.style.borderColor = "#2A3148")} />
              <button onClick={addSeed} className="mono" style={{ border: "1px solid #2A3148", color: "#CBD5E0", background: "transparent", fontSize: 10, padding: "0 12px", borderRadius: 2 }}>ADD</button>
            </div>
            <div className="flex flex-col" style={{ gap: 6, marginTop: 10 }}>
              {seeds.map((s, i) => (
                <div key={i} className="flex items-center justify-between mono text-body"
                  style={{ fontSize: 10, border: "0.5px solid #2A3148", borderRadius: 2, padding: "4px 8px" }}>
                  <span><span className="text-dim">[{s.type.toUpperCase()}]</span> {s.value}</span>
                  <button onClick={() => setSeeds(seeds.filter((_, j) => j !== i))} className="text-dim" style={{ fontSize: 12, lineHeight: 1 }}>×</button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="flex items-center" style={{ gap: 8 }}>
              <input type="checkbox" checked={minor} onChange={(e) => setMinor(e.target.checked)} style={{ accentColor: "#D4900A" }} />
              <span className="display text-body" style={{ fontSize: 12 }}>Subject is a minor</span>
            </label>
            {minor && (
              <div className="mono text-amber" style={{ fontSize: 9, marginTop: 6, marginLeft: 24 }}>
                POCSO / JJ Act redaction will apply in generated report
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end" style={{ padding: "12px 20px", borderTop: "1px solid #2A3148", gap: 8 }}>
          <button onClick={onClose} disabled={busy} className="mono text-dim" style={{ fontSize: 10 }}>CANCEL</button>
          <button onClick={begin} disabled={busy} className="mono"
            style={{ border: "1px solid #D4900A", color: "#D4900A", background: "transparent", fontSize: 10, padding: "8px 20px", borderRadius: 2 }}
            onMouseEnter={(e) => { if (!busy) e.currentTarget.style.background = "rgba(212,144,10,0.10)"; }}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            {busy ? "STARTING…" : "BEGIN INVESTIGATION"}
          </button>
        </div>
      </div>
    </div>
  );
}
