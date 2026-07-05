/* components/ui/LeakDataPanel.jsx
   The "Leak Data" tab. Renders @NewleaksOsintBot results that the backend's LLM step
   (backend/ingestion/leak_classify.py) sorted into:
     • leak_classified — canonical identity fields (name/location/employer/…)
     • leak_leftover   — everything that didn't map to a canonical field
   If the LLM was unavailable, leak_classified/leftover are absent and we fall back to
   the scraper's raw parsed fields (databases/passwords/emails/links) so the tab is still
   useful. This is a DISPLAY surface only — none of it feeds correlation/scoring. */
"use client";
import PlatformLogo from "./PlatformLogo";

// Canonical fields in a sensible reading order; anything the LLM returns outside this
// list still renders (appended) so we never silently drop a classified value.
const FIELD_ORDER = [
  "full_name", "first_name", "last_name", "username", "email", "phone",
  "date_of_birth", "address", "location", "city", "region", "country", "employer",
  "school", "ip", "password",
];
const FIELD_LABEL = {
  full_name: "Full name", first_name: "First name", last_name: "Last name",
  username: "Username", email: "Email", phone: "Phone", date_of_birth: "Date of birth",
  address: "Address", location: "Location", city: "City", region: "Region",
  country: "Country", employer: "Employer", school: "School", ip: "IP address",
  password: "Password",
};
const SENSITIVE = new Set(["password"]);

function asList(v) {
  if (Array.isArray(v)) return v.filter((x) => x !== null && x !== undefined && x !== "");
  if (v === null || v === undefined || v === "") return [];
  return [v];
}

function humanize(key) {
  return String(key).replace(/[_\-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function Row({ label, values, sensitive }) {
  const vals = asList(values);
  if (!vals.length) return null;
  return (
    <div className="flex gap-3 py-1.5 border-b border-slate-800/60 last:border-0">
      <span className="text-slate-500 text-[11px] font-mono uppercase tracking-wide w-28 shrink-0 pt-0.5">{label}</span>
      <span className="min-w-0 flex flex-wrap gap-1.5">
        {vals.map((v, i) => (
          <span key={i}
            className={`text-[13px] rounded px-1.5 py-0.5 break-all ${
              sensitive
                ? "font-mono text-red-300 bg-red-500/10 border border-red-500/25"
                : "text-slate-200 bg-slate-800/50 border border-slate-700/50"}`}>
            {String(v)}
          </span>
        ))}
      </span>
    </div>
  );
}

function orderedEntries(obj, order) {
  const keys = Object.keys(obj || {});
  const known = order.filter((k) => keys.includes(k));
  const extra = keys.filter((k) => !order.includes(k));
  return [...known, ...extra];
}

function LeakCard({ entity }) {
  const meta = entity.metadata || {};
  const classified = meta.leak_classified || {};
  const leftover = meta.leak_leftover || {};
  const dbs = meta.databases || meta.breaches || [];
  const count = meta.leaks_count ?? meta.breach_count;

  const hasClassified = Object.keys(classified).length > 0;
  const hasLeftover = Object.keys(leftover).length > 0;

  // Fallback (LLM unavailable): show the scraper's raw parsed fields so the tab still helps.
  const rawFallback = !hasClassified && !hasLeftover
    ? { Emails: meta.emails, Phones: meta.phones, Passwords: meta.passwords, Links: meta.links, Names: meta.names, IPs: meta.ips }
    : null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
      <div className="flex items-center gap-2.5 px-4 py-3 border-b border-slate-800 bg-gradient-to-r from-red-500/[0.06] to-transparent">
        <PlatformLogo platform="newleaks" width={20} height={20} />
        <span className="text-sm font-semibold text-white truncate">{entity.value || "Leak record"}</span>
        <span className="text-[9px] font-mono uppercase tracking-wide text-red-400 bg-red-500/10 border border-red-500/30 rounded px-1.5 py-0.5">leak</span>
        <div className="ml-auto flex items-center gap-2 text-[11px] font-mono text-slate-500">
          {count != null && <span>{count} leak{count === 1 ? "" : "s"}</span>}
          {dbs.length > 0 && <span className="text-slate-400">· {dbs.slice(0, 3).join(", ")}{dbs.length > 3 ? "…" : ""}</span>}
        </div>
      </div>

      <div className="px-4 py-3 grid gap-4 md:grid-cols-2">
        {/* Classified canonical fields */}
        {hasClassified && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wide text-cyan-300 mb-1.5">Classified fields</div>
            <div>
              {orderedEntries(classified, FIELD_ORDER).map((k) => (
                <Row key={k} label={FIELD_LABEL[k] || humanize(k)} values={classified[k]} sensitive={SENSITIVE.has(k)} />
              ))}
            </div>
          </div>
        )}

        {/* Leftover — didn't map to a canonical field */}
        {hasLeftover && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wide text-amber-300 mb-1.5">Other information</div>
            <div>
              {Object.keys(leftover).map((k) => (
                <Row key={k} label={humanize(k)} values={leftover[k]} />
              ))}
            </div>
          </div>
        )}

        {/* Fallback raw fields when the LLM didn't run */}
        {rawFallback && (
          <div className="md:col-span-2">
            <div className="text-[10px] font-mono uppercase tracking-wide text-slate-400 mb-1.5">Raw records (not yet classified)</div>
            <div>
              {Object.entries(rawFallback).map(([k, v]) => (
                <Row key={k} label={k} values={v} sensitive={k === "Passwords"} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function LeakDataPanel({ entities = [] }) {
  const leaks = (entities || []).filter((e) => {
    const m = e.metadata || {};
    return m.source === "newleaks_bot";
  });

  if (!leaks.length) {
    return <div className="py-10 text-center text-sm text-slate-500">No leak-database results for this case.</div>;
  }

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-slate-500">
        Results from leak databases (via @{"NewleaksOsintBot"}), sorted by AI into known identity
        fields and any leftover details. Sensitive by nature — verify before use in a filing.
      </p>
      {leaks.map((e) => <LeakCard key={e.entity_id || e.value} entity={e} />)}
    </div>
  );
}
