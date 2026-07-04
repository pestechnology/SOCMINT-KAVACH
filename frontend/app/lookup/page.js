/* app/lookup/page.js — Quick Lookup: a fast multi-source OSINT dossier.
   Separate from the full investigation (case) view: enter one identifier, get a rich,
   SOURCE-TAGGED dossier (names / usernames / emails / phones / locations / accounts /
   timeline / photos). "Send to investigation" promotes it into a correlated case.
   Positioned as lead-generation for a human analyst — every field shows its provenance. */
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "@/lib/api";
import GlassPanel from "@/components/ui/GlassPanel";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Label from "@/components/ui/Label";
import EmptyState from "@/components/ui/EmptyState";

const TYPES = [
  { value: "username", label: "Username", ph: "e.g. ash29_03" },
  { value: "email", label: "Email", ph: "e.g. subject@mail.com" },
  { value: "name", label: "Name", ph: "e.g. Arjun Mehta" },
  { value: "instagram", label: "Instagram", ph: "e.g. ash29_03" },
  { value: "phone", label: "Phone", ph: "e.g. +91 98765 43210" },
];
const SELECT_CLS =
  "rounded-lg bg-slate-900/80 border border-slate-700 px-3 py-2 text-sm text-slate-100 " +
  "outline-none focus:border-cyan-400 cursor-pointer";

// aggregate per-source dossiers into {value -> [sources]} maps so we can show provenance
function aggregate(perSource) {
  const strMap = (key) => {
    const m = new Map();
    for (const r of perSource || []) {
      if (!r.ok || !r.dossier) continue;
      const src = r.name || r.source;
      for (const v of r.dossier[key] || []) {
        const k = String(v);
        if (!m.has(k)) m.set(k, new Set());
        m.get(k).add(src);
      }
    }
    return [...m.entries()].map(([value, srcs]) => ({ value, sources: [...srcs] }));
  };
  const accounts = [], photos = new Set(), timeline = [];
  for (const r of perSource || []) {
    if (!r.ok || !r.dossier) continue;
    const src = r.name || r.source;
    for (const a of r.dossier.accounts || []) accounts.push({ ...a, source: src });
    for (const p of r.dossier.photos || []) photos.add(p);
    for (const t of r.dossier.timeline || []) timeline.push({ ...t, source: src });
  }
  return {
    names: strMap("names"), usernames: strMap("usernames"), emails: strMap("emails"),
    phones: strMap("phones"), locations: strMap("locations"),
    accounts, photos: [...photos], timeline,
  };
}

export default function Lookup() {
  const router = useRouter();
  const [idType, setIdType] = useState("username");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => { if (!getToken()) router.replace("/login"); }, [router]);

  async function run() {
    if (!query.trim()) { setError("Enter an identifier to look up."); return; }
    setError(""); setBusy(true); setResult(null);
    try {
      setResult(await api.smartLookup({ id_type: idType, query: query.trim(), max_public: 6 }));
    } catch (e) { setError(e.message); }
    setBusy(false);
  }

  async function sendToCase() {
    if (!result) return;
    setSending(true); setError("");
    try {
      const r = await api.smartLookupSend({ query: result.query, id_type: result.type, dossier: result.combined });
      router.push(`/cases/${r.case_id}`);
    } catch (e) { setError(e.message); setSending(false); }
  }

  const agg = result ? aggregate(result.per_source) : null;
  const ph = TYPES.find((t) => t.value === idType)?.ph || "";
  const okCount = result ? result.per_source.filter((r) => r.ok).length : 0;

  return (
    <div className="min-h-screen">
      <nav className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/cases")} className="font-display font-semibold text-slate-100" style={{ fontSize: 20 }}>
            VERTEX<span className="text-cyan-400">.</span>
          </button>
          <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 border border-cyan-400/30 rounded px-2 py-0.5">🔎 Quick Lookup</span>
        </div>
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/cases")} className="text-[12px] text-slate-400 hover:text-slate-200">Investigations →</button>
          <button onClick={() => { clearToken(); router.replace("/login"); }} className="text-[12px] text-slate-400 hover:text-slate-200">Sign out</button>
        </div>
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="text-2xl font-semibold text-slate-100">Quick Lookup</h1>
        <p className="mt-1 text-sm text-slate-500">
          Fast multi-source OSINT enrichment. Every field is tagged with its source — this is
          lead-generation for an analyst, not a verdict.
        </p>

        {/* search bar */}
        <GlassPanel className="p-4 mt-6">
          <div className="flex flex-wrap gap-2 items-end">
            <div>
              <Label>Type</Label>
              <select value={idType} onChange={(e) => setIdType(e.target.value)} className={SELECT_CLS}>
                {TYPES.map((t) => <option key={t.value} value={t.value} className="bg-slate-900">{t.label}</option>)}
              </select>
            </div>
            <div className="flex-1 min-w-[220px]">
              <Label>Identifier</Label>
              <Input value={query} placeholder={ph} onChange={(e) => setQuery(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); run(); } }} />
            </div>
            <Button variant="primary" onClick={run} disabled={busy}>{busy ? "Looking up…" : "🔎 Look up"}</Button>
          </div>
          {error && <div className="mt-3 text-[13px]" style={{ color: "var(--tone-rose)" }}>{error}</div>}
        </GlassPanel>

        {busy && <div className="mt-8 text-center text-sm text-slate-500">Querying sources…</div>}

        {result && agg && (
          <div className="mt-6">
            {/* header + bridge */}
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
              <div>
                <div className="text-lg font-semibold text-slate-100">{result.query}</div>
                <div className="text-xs font-mono text-slate-500">{result.type} · {okCount}/{result.per_source.length} sources responded</div>
              </div>
              <Button variant="primary" onClick={sendToCase} disabled={sending || agg.accounts.length === 0}>
                {sending ? "Sending…" : "→ Send to investigation"}
              </Button>
            </div>

            {/* source status chips (provenance transparency) */}
            <div className="flex flex-wrap gap-1.5 mb-5">
              {result.per_source.map((r) => (
                <span key={r.source} title={r.error || "ok"}
                      className={`text-[10px] font-mono rounded px-1.5 py-0.5 border ${
                        r.ok ? "text-emerald-300 border-emerald-400/30 bg-emerald-400/5"
                             : "text-slate-500 border-slate-700"}`}>
                  {r.ok ? "●" : "○"} {r.name || r.source}
                </span>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ChipCard icon="👤" title="Names" items={agg.names} />
              <ChipCard icon="@" title="Usernames" items={agg.usernames} />
              <ChipCard icon="✉️" title="Emails" items={agg.emails} />
              <ChipCard icon="📞" title="Phones" items={agg.phones} />
              <ChipCard icon="📍" title="Locations" items={agg.locations} />
              <PhotoCard photos={agg.photos} />
              <AccountsCard accounts={agg.accounts} />
              <TimelineCard timeline={agg.timeline} />
            </div>

            <p className="mt-6 text-[11px] text-slate-600">
              Generated from public/API sources shown above. Investigator aid for triage —
              corroborate before acting.
            </p>
          </div>
        )}

        {result && agg && okCount === 0 && (
          <div className="mt-8">
            <EmptyState icon="🔍" title="No sources responded"
                        description="Sources may be rate-limited or require setup (IntelBase whitelist, login profile)." />
          </div>
        )}
      </main>
    </div>
  );
}

function Card({ icon, title, count, children }) {
  return (
    <GlassPanel className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <span>{icon}</span>
        <span className="text-[11px] font-mono uppercase tracking-wide text-slate-400">{title}</span>
        {count != null && <span className="text-[11px] text-slate-600">· {count}</span>}
      </div>
      {children}
    </GlassPanel>
  );
}

function ChipCard({ icon, title, items }) {
  return (
    <Card icon={icon} title={title} count={items.length}>
      {items.length === 0 ? <div className="text-xs text-slate-600">—</div> : (
        <div className="flex flex-wrap gap-1.5">
          {items.map((it, i) => (
            <span key={i} className="text-xs rounded-md bg-slate-900/70 border border-slate-700 px-2 py-1 text-slate-200">
              {it.value}
              <span className="ml-1.5 text-[10px] text-slate-500">{it.sources.join(", ")}</span>
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

function AccountsCard({ accounts }) {
  return (
    <Card icon="🔗" title="Accounts" count={accounts.length}>
      {accounts.length === 0 ? <div className="text-xs text-slate-600">—</div> : (
        <div className="space-y-1.5">
          {accounts.map((a, i) => (
            <div key={i} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-slate-200">
                <span className="text-slate-400">{a.platform}</span>{a.handle ? ` · ${a.handle}` : ""}
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500">{a.source}</span>
                {a.url && <a href={a.url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300">↗</a>}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function PhotoCard({ photos }) {
  return (
    <Card icon="🖼️" title="Photos" count={photos.length}>
      {photos.length === 0 ? <div className="text-xs text-slate-600">—</div> : (
        <div className="flex flex-wrap gap-2">
          {photos.slice(0, 12).map((p, i) => (
            <a key={i} href={p} target="_blank" rel="noreferrer">
              <img src={p} alt="" className="w-10 h-10 rounded object-cover border border-slate-700" />
            </a>
          ))}
        </div>
      )}
    </Card>
  );
}

function TimelineCard({ timeline }) {
  return (
    <Card icon="🕑" title="Timeline" count={timeline.length}>
      {timeline.length === 0 ? <div className="text-xs text-slate-600">—</div> : (
        <div className="space-y-1.5">
          {timeline.map((t, i) => (
            <div key={i} className="text-xs flex gap-2">
              <span className="text-slate-500 font-mono whitespace-nowrap">{t.date || "—"}</span>
              <span className="text-slate-300">{t.event}</span>
              <span className="text-[10px] text-slate-600 ml-auto">{t.source}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
