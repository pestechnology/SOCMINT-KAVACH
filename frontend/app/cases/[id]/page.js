/* app/cases/[id]/page.js
   CHANGED: full rewrite to the 3-panel Case Room workspace — status strip, account
   registry (filters + live scanning feed), correlation graph (hover tooltip + SCANNING
   overlay), cluster analysis (signal tables + member chips + unlinked section), timeline.
   DECISION: polling logic + api.getResults/downloadReport are UNCHANGED; report button
   stays disabled until status==='complete'; chain integrity derives from completion. */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { api, getToken } from "@/lib/api";

const NetworkGraph = dynamic(() => import("@/components/Graph"), { ssr: false });
const Timeline = dynamic(() => import("@/components/Timeline"), { ssr: false });

// ---------- helpers ----------
const NODE_HEX = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#8A97AD" };
const TIER_CLASS = { HIGH: "tier-high", MEDIUM: "tier-medium", LOW: "tier-low", REJECT: "tier-reject" };
const TIER_SHORT = { HIGH: "HIGH", MEDIUM: "MED", LOW: "LOW", REJECT: "REJECT" };
const FILTERS = [["ALL", "ALL"], ["HIGH", "HIGH"], ["MED", "MEDIUM"], ["LOW", "LOW"], ["REJECT", "REJECT"]];

function platformShort(p) {
  const m = { github: "GH", instagram: "IG", hibp: "HIBP", telegram: "TG", reddit: "RD", linkedin: "LI", twitter: "TW", upi: "UPI", serper: "WEB", derived: "DRV" };
  const k = (p || "").toLowerCase();
  return m[k] || (p || "?").slice(0, 3).toUpperCase();
}
function fmtFollowers(n) {
  const v = Number(n);
  if (isNaN(v)) return null;
  return v >= 1000 ? (v / 1000).toFixed(1) + "k" : String(v);
}
function activeHours(hrs) {
  if (!Array.isArray(hrs) || !hrs.length) return null;
  const nums = hrs.map(Number).filter((x) => !isNaN(x));
  if (!nums.length) return null;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.min(...nums))}:00–${p(Math.max(...nums))}:00`;
}

export default function CaseView() {
  const router = useRouter();
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [mouse, setMouse] = useState({ x: 0, y: 0 });
  const [filter, setFilter] = useState("ALL");
  const [showUnlinked, setShowUnlinked] = useState(false);

  // scanning feed (running state)
  const seenRef = useRef(new Set());
  const [logLines, setLogLines] = useState([]);

  // ---------- POLLING (UNCHANGED) ----------
  const load = useCallback(async () => {
    try { setData(await api.getResults(id)); }
    catch (e) { if (e.status === 401) router.replace("/login"); }
  }, [id, router]);

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    load();
  }, [load, router]);

  useEffect(() => {
    const status = data?.status;
    if (status === "running" || status === "pending") {
      const t = setInterval(() => { load(); }, 1500);
      return () => clearInterval(t);
    }
  }, [data?.status, load]);
  // ---------- /POLLING ----------

  // append scanning-feed lines as entities arrive
  useEffect(() => {
    if (!data) return;
    const ents = data.entities || [];
    const fresh = ents.filter((e) => !seenRef.current.has(e.entity_id));
    if (!fresh.length) return;
    fresh.forEach((e) => seenRef.current.add(e.entity_id));
    const now = new Date();
    const p = (n) => String(n).padStart(2, "0");
    const ts = `${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`;
    const lines = fresh.map((e) => `[${ts}]  ${platformShort(e.platform).padEnd(5)} ${e.value || ""}   found`);
    setLogLines((prev) => [...lines, ...prev].slice(0, 40));
  }, [data]);

  if (!data) {
    return <div className="flex items-center justify-center h-screen mono text-dim" style={{ fontSize: 11 }}>LOADING…</div>;
  }

  const entities = data.entities || [];
  const clusters = data.clusters || [];
  const status = data.status;
  const running = status === "running" || status === "pending";
  const kase = data.case || {};

  // map each entity -> its cluster info
  const infoByEntity = {};
  clusters.forEach((c) => (c.entity_ids || []).forEach((eid) => { infoByEntity[eid] = { tier: c.tier, score: c.confidence_score, cluster: c }; }));

  const entById = {};
  entities.forEach((e) => (entById[e.entity_id] = e));

  const sorted = [...entities].sort((a, b) => (infoByEntity[b.entity_id]?.score || 0) - (infoByEntity[a.entity_id]?.score || 0));
  const visible = filter === "ALL" ? sorted : sorted.filter((e) => (infoByEntity[e.entity_id]?.tier || "REJECT") === filter);

  const multi = clusters.filter((c) => (c.entity_ids || []).length >= 2);
  const unlinked = clusters.filter((c) => (c.entity_ids || []).length < 2);
  const linkedSorted = [...multi].sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
  const highLinks = multi.filter((c) => c.tier === "HIGH").length;
  const topScore = clusters.reduce((m, c) => Math.max(m, c.confidence_score || 0), 0);

  const hoveredEnt = hovered ? entById[hovered] : null;
  const hoveredInfo = hovered ? infoByEntity[hovered] : null;
  const fx = data.forensics || {};

  return (
    <div className="h-screen flex flex-col bg-ink overflow-hidden">
      {/* TOP BAR */}
      <div className="bg-surface border-b border-edge flex items-center justify-between" style={{ padding: "10px 20px" }}>
        <button onClick={() => router.push("/cases")} className="mono text-dim hover:text-amber" style={{ fontSize: 10 }}>← Registry</button>
        <div className="display text-head truncate" style={{ fontSize: 15, fontWeight: 500, maxWidth: "50%" }}>{kase.title}</div>
        <div className="flex items-center" style={{ gap: 12 }}>
          <StatusBadge status={status} />
          <ReportButton id={id} disabled={status !== "complete"} />
        </div>
      </div>

      {/* STATUS STRIP */}
      <div className="flex bg-lifted border-b border-edge">
        <Stat label="ACCOUNTS" value={entities.length} />
        <Stat label="HIGH LINKS" value={highLinks} cls="tier-high" />
        <Stat label="CLUSTERS" value={multi.length} />
        <Stat label="CHAIN" value={status === "complete" ? "VERIFIED ✓" : "—"} cls={status === "complete" ? "tier-complete" : "tier-reject"} />
        <Stat label="TOP SCORE" value={`${topScore}/100`} cls="tier-high" />
      </div>

      {/* THREE PANELS */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        {/* LEFT — ACCOUNT REGISTRY */}
        <div className="overflow-y-auto bg-surface border-r border-edge" style={{ width: 260, flexShrink: 0 }}>
          <div className="panel-label sticky top-0 bg-surface border-b border-edge" style={{ padding: "10px 14px" }}>
            DISCOVERED ACCOUNTS ({entities.length})
          </div>

          {!running && (
            <div className="flex border-b border-edge" style={{ gap: 6, padding: "6px 14px" }}>
              {FILTERS.map(([label, val]) => (
                <button key={val} onClick={() => setFilter(val)} className="mono"
                  style={{ fontSize: 8, padding: "3px 8px", borderRadius: 2, border: "0.5px solid", borderColor: filter === val ? "#D4900A" : "#2A3148", color: filter === val ? "#D4900A" : "#4A5568", background: "transparent" }}>
                  {label}
                </button>
              ))}
            </div>
          )}

          {running ? (
            <div className="bg-ink" style={{ padding: "8px 12px", minHeight: "100%" }}>
              {logLines.length === 0 && <div className="mono text-dim" style={{ fontSize: 10 }}>● initialising scan…</div>}
              {logLines.map((l, i) => (
                <div key={i} className="mono tier-complete" style={{ fontSize: 10, lineHeight: 1.7, whiteSpace: "pre" }}>{l}</div>
              ))}
            </div>
          ) : (
            visible.map((e) => <AccountCard key={e.entity_id} e={e} info={infoByEntity[e.entity_id]} onClick={() => setSelected(e.entity_id)} active={selected === e.entity_id} />)
          )}
        </div>

        {/* MIDDLE — CORRELATION GRAPH */}
        <div className="flex flex-col flex-1 bg-surface border-r border-edge" style={{ minWidth: 0 }}>
          <div className="panel-label border-b border-edge" style={{ padding: "10px 14px" }}>CORRELATION GRAPH</div>
          <div className="relative flex-1" style={{ minHeight: 0 }} onMouseMove={(ev) => setMouse({ x: ev.clientX, y: ev.clientY })}>
            {entities.length > 0 ? (
              <NetworkGraph entities={entities} clusters={clusters} onSelect={setSelected} onHover={setHovered} />
            ) : (
              <div className="flex items-center justify-center h-full mono text-dim" style={{ fontSize: 11 }}>AWAITING DATA</div>
            )}

            {running && (
              <div className="absolute mono text-amber flex items-center" style={{ top: 10, right: 10, gap: 6, background: "#161B27", border: "0.5px solid #D4900A", padding: "4px 10px", fontSize: 9 }}>
                <span className="status-dot-running" /> SCANNING
              </div>
            )}

            {hoveredEnt && (
              <div className="fixed bg-surface border border-edge pointer-events-none z-50" style={{ left: mouse.x + 14, top: mouse.y + 14, padding: "8px 10px", maxWidth: 240 }}>
                <div className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em" }}>{(hoveredEnt.platform || "").toUpperCase()}</div>
                <div className="display text-head" style={{ fontSize: 13, fontWeight: 500 }}>{hoveredEnt.value}</div>
                {hoveredInfo && (
                  <div className={`mono ${TIER_CLASS[hoveredInfo.tier] || "tier-reject"}`} style={{ fontSize: 10, marginTop: 2 }}>
                    {hoveredInfo.score} — {hoveredInfo.tier}
                  </div>
                )}
                {hoveredInfo?.cluster?.signals && (
                  <div className="mono text-dim" style={{ fontSize: 9, marginTop: 3 }}>
                    {Object.keys(hoveredInfo.cluster.signals).slice(0, 2).join(", ") || "no shared signals"}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex border-t border-edge" style={{ gap: 16, padding: "10px 14px" }}>
            {[["HIGH", "#D4900A"], ["MEDIUM", "#5B9BD5"], ["LOW", "#E08A4A"], ["UNLINKED", "#8A97AD"]].map(([t, c]) => (
              <span key={t} className="mono text-dim flex items-center" style={{ fontSize: 9, gap: 5 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, display: "inline-block" }} />{t}
              </span>
            ))}
          </div>
        </div>

        {/* RIGHT — CLUSTER ANALYSIS */}
        <div className="overflow-y-auto bg-surface" style={{ width: 220, flexShrink: 0 }}>
          <div className="panel-label sticky top-0 bg-surface border-b border-edge" style={{ padding: "10px 14px" }}>
            CLUSTER ANALYSIS ({multi.length})
          </div>

          {linkedSorted.length === 0 && !running && (
            <div className="mono text-dim" style={{ fontSize: 10, padding: 14 }}>No multi-account links established.</div>
          )}

          {linkedSorted.map((c) => <ClusterBlock key={c.cluster_id} c={c} entById={entById} />)}

          {unlinked.length > 0 && (
            <div className="border-t border-edge">
              <button onClick={() => setShowUnlinked((v) => !v)} className="flex items-center justify-between w-full" style={{ padding: "10px 14px" }}>
                <span className="mono text-dim" style={{ fontSize: 9 }}>UNLINKED ACCOUNTS ({unlinked.length})</span>
                <span className="mono text-dim" style={{ fontSize: 9 }}>{showUnlinked ? "▾ hide" : "▸ expand"}</span>
              </button>
              {showUnlinked && unlinked.map((c) => {
                const e = entById[(c.entity_ids || [])[0]];
                return (
                  <div key={c.cluster_id} className="border-t border-edge" style={{ padding: "8px 14px", opacity: 0.7 }}>
                    <div className="mono text-dim" style={{ fontSize: 9 }}>
                      {(e?.platform || "?").toUpperCase()} · {e?.value || "—"}
                    </div>
                    <div className="display text-dim" style={{ fontSize: 9, fontStyle: "italic", marginTop: 2 }}>
                      Reason: single signal — insufficient corroboration
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* FORENSIC ANALYSIS */}
      {!running && fx && (fx.tone || fx.activity) && (
        <div className="border-t border-edge bg-surface">
          <div className="panel-label" style={{ padding: "10px 16px" }}>LINGUISTIC &amp; BEHAVIOURAL FORENSICS</div>
          <div className="flex flex-wrap border-t border-edge">
            <FxCell label="TONE" flag={fx.tone?.flag_negative}
              value={fx.tone?.samples_analyzed ? `${(fx.tone.label || "neutral").toUpperCase()} (${fx.tone.compound})` : "—"} />
            <FxCell label="ACTIVE HOURS (UTC)"
              value={fx.activity?.available ? (fx.activity.active_hours_utc || []).map((h) => String(h).padStart(2, "0") + ":00").join(" ") : "—"} />
            <FxCell label="POSTS ANALYSED" value={fx.activity?.posts_analyzed || 0} />
            <FxCell label="ENGAGEMENT" value={fx.engagement?.available ? `${fx.engagement.followers_total} followers` : "—"} />
            <FxCell label="EXPOSURE" value={`${fx.footprint?.breach_exposures || 0} breaches · ${fx.footprint?.registered_services || 0} services`} />
          </div>
          {(fx.keywords?.length || fx.hashtags?.length) ? (
            <div style={{ padding: "10px 16px" }}>
              {fx.keywords?.length > 0 && (
                <div className="flex flex-wrap items-center" style={{ gap: 5, marginBottom: 6 }}>
                  <span className="mono text-dim" style={{ fontSize: 8, minWidth: 64 }}>KEYWORDS</span>
                  {fx.keywords.map((k) => (
                    <span key={k} className="mono text-body" style={{ fontSize: 9, background: "#2A3148", padding: "2px 7px", borderRadius: 2 }}>{k}</span>
                  ))}
                </div>
              )}
              {fx.hashtags?.length > 0 && (
                <div className="flex flex-wrap items-center" style={{ gap: 5 }}>
                  <span className="mono text-dim" style={{ fontSize: 8, minWidth: 64 }}>HASHTAGS</span>
                  {fx.hashtags.map((h) => (
                    <span key={h} className="mono tier-medium" style={{ fontSize: 9, background: "#1E2235", padding: "2px 7px", borderRadius: 2 }}>#{h}</span>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* TIMELINE */}
      <div className="border-t border-edge bg-surface">
        <div className="panel-label" style={{ padding: "10px 16px" }}>CROSS-PLATFORM ACTIVITY TIMELINE</div>
        {entities.some((e) => Array.isArray(e.metadata?.posting_hours) && e.metadata.posting_hours.length) ? (
          <Timeline entities={entities} clusters={clusters} />
        ) : (
          <div className="mono text-dim text-center" style={{ fontSize: 10, padding: "24px 0" }}>INSUFFICIENT TEMPORAL DATA</div>
        )}
      </div>
    </div>
  );
}

// ---------- subcomponents ----------
function Stat({ label, value, cls = "text-head" }) {
  return (
    <div style={{ padding: "8px 16px", borderRight: "1px solid #2A3148" }}>
      <div className={`mono ${cls}`} style={{ fontSize: 16, fontWeight: 500 }}>{value}</div>
      <div className="mono text-dim" style={{ fontSize: 8, letterSpacing: "0.1em", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function FxCell({ label, value, flag }) {
  return (
    <div style={{ padding: "10px 16px", borderRight: "1px solid #2A3148", minWidth: 120 }}>
      <div className={`mono ${flag ? "tier-error" : "text-head"}`} style={{ fontSize: 12, fontWeight: 500 }}>
        {flag ? "⚠ " : ""}{value}
      </div>
      <div className="mono text-dim" style={{ fontSize: 8, letterSpacing: "0.1em", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    complete: { c: "tier-complete", bar: "#27AE60" },
    running: { c: "tier-high", bar: "#D4900A" },
    pending: { c: "tier-reject", bar: "#D4900A" },
    error: { c: "tier-error", bar: "#C0392B" },
  };
  const s = map[status] || { c: "tier-reject", bar: "#4A5568" };
  return (
    <span className="flex items-center" style={{ gap: 6 }}>
      <span style={{ width: 6, height: 6, borderRadius: 1, background: s.bar }} />
      <span className={`mono ${s.c}`} style={{ fontSize: 9, letterSpacing: "0.08em" }}>{(status || "—").toUpperCase()}</span>
    </span>
  );
}

function MetaRow({ label, children }) {
  return (
    <div className="flex" style={{ marginTop: 2 }}>
      <span className="mono text-dim" style={{ fontSize: 8, width: 52, flexShrink: 0, letterSpacing: "0.05em" }}>{label}</span>
      <span className="display text-body" style={{ fontSize: 10, lineHeight: 1.4 }}>{children}</span>
    </div>
  );
}

function AccountCard({ e, info, onClick, active }) {
  const tier = info?.tier || "REJECT";
  const score = info?.score ?? 0;
  const isReject = tier === "REJECT";
  const accent = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#3A4358" }[tier];
  const m = e.metadata || {};
  const followers = fmtFollowers(m.follower_count);
  const hours = activeHours(m.posting_hours);
  const breaches = Array.isArray(m.breaches) && m.breaches.length
    ? `${m.breaches.join(", ")} (${m.breaches.length})`
    : m.breach_name || null;

  return (
    <div
      onClick={onClick}
      className="cursor-pointer border-b border-edge relative"
      style={{ padding: "10px 14px", borderLeft: `2.5px solid ${accent}`, background: active ? "#1E2235" : "transparent", opacity: isReject ? 0.45 : 1 }}
    >
      <div className="flex items-start justify-between">
        <span className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em" }}>{(e.platform || "").toUpperCase()}</span>
        <div style={{ textAlign: "right" }}>
          <div className={`mono ${TIER_CLASS[tier]}`} style={{ fontSize: 18, fontWeight: 500, lineHeight: 1 }}>{score}</div>
          <div className={`mono ${TIER_CLASS[tier]}`} style={{ fontSize: 8, marginTop: 1 }}>{TIER_SHORT[tier]}</div>
        </div>
      </div>

      <div className="display text-head" style={{ fontSize: 14, fontWeight: 500, marginTop: 3, wordBreak: "break-all" }}>{e.value}</div>

      {isReject && (
        <div className="display text-dim" style={{ fontSize: 9, fontStyle: "italic", marginTop: 3 }}>Single signal — insufficient corroboration</div>
      )}

      <div style={{ marginTop: 6 }}>
        {m.fullname && <div className="display text-body" style={{ fontSize: 11 }}>{m.fullname}</div>}
        {m.location && <MetaRow label="LOC">{m.location}</MetaRow>}
        {m.bio && <MetaRow label="BIO">{String(m.bio).slice(0, 55)}{String(m.bio).length > 55 ? "…" : ""}</MetaRow>}
        {m.phone && <MetaRow label="PH">{m.phone}</MetaRow>}
        {breaches && <MetaRow label="BREACH">{breaches}</MetaRow>}
        {hours && <MetaRow label="ACTIVE">{hours}</MetaRow>}
        {followers && <MetaRow label="FOLLOW">{followers}</MetaRow>}
      </div>

      {e.sha256 && <div className="hash-val" style={{ marginTop: 6 }}>SHA  {String(e.sha256).slice(0, 16)}…</div>}
      {e.source_url && safeUrl(e.source_url) && (
        <a href={safeUrl(e.source_url)} target="_blank" rel="noreferrer noopener" onClick={(ev) => ev.stopPropagation()}
          className="mono text-amber block" style={{ fontSize: 8, marginTop: 2, textAlign: "right" }}>SOURCE ↗</a>
      )}
    </div>
  );
}

function ClusterBlock({ c, entById }) {
  const tier = c.tier;
  const accent = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#8A97AD" }[tier] || "#8A97AD";
  const cls = TIER_CLASS[tier] || "tier-reject";
  const label = { HIGH: "HIGH CONFIDENCE LINK", MEDIUM: "MEDIUM CONFIDENCE LINK", LOW: "LOW CONFIDENCE LINK", REJECT: "REJECTED" }[tier] || "LINK";
  const signals = c.signals || {};
  const members = (c.entity_ids || []).map((id) => entById[id]).filter(Boolean);

  return (
    <div className="border-b border-edge" style={{ borderLeft: `2px solid ${accent}`, padding: "12px 14px" }}>
      <div className="flex items-start justify-between">
        <span className={`mono ${cls}`} style={{ fontSize: 8, letterSpacing: "0.1em" }}>{label}</span>
        <span className={`mono ${cls}`} style={{ fontSize: 22, fontWeight: 500, lineHeight: 1 }}>{c.confidence_score}<span style={{ fontSize: 11 }}>/100</span></span>
      </div>

      <div className="display text-body" style={{ fontSize: 12, lineHeight: 1.6, marginTop: 6, borderLeft: "2px solid #2A3148", paddingLeft: 8 }}>
        {c.explanation}
      </div>

      <div style={{ marginTop: 8 }}>
        {Object.entries(signals).map(([name, pts]) => (
          <div key={name} className="flex items-center justify-between" style={{ marginTop: 2 }}>
            <span className="mono text-dim" style={{ fontSize: 8 }}>{name}</span>
            <span className="mono text-body" style={{ fontSize: 8 }}>+{pts}</span>
          </div>
        ))}
        <div className="flex items-center justify-between" style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid #2A3148" }}>
          <span className="mono text-dim" style={{ fontSize: 8 }}>TOTAL SCORE</span>
          <span className={`mono ${cls}`} style={{ fontSize: 8 }}>{c.confidence_score} / 100</span>
        </div>
      </div>

      {members.length > 0 && (
        <div className="flex flex-wrap" style={{ gap: 4, marginTop: 8 }}>
          {members.map((e) => (
            <span key={e.entity_id} className="mono text-body" style={{ fontSize: 8, background: "#2A3148", padding: "2px 6px", borderRadius: 2 }}>
              {platformShort(e.platform)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ReportButton({ id, disabled }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function generate() {
    if (disabled) return;
    setErr(""); setBusy(true);
    try {
      const blob = await api.downloadReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `BSA63_report_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }
  return (
    <span className="flex items-center" style={{ gap: 8 }}>
      {err && <span className="mono text-crimson" style={{ fontSize: 9 }}>{err}</span>}
      <button onClick={generate} disabled={disabled || busy} className="mono"
        style={{ border: "1px solid #D4900A", color: "#D4900A", background: "transparent", fontSize: 10, letterSpacing: "0.06em", padding: "6px 14px", borderRadius: 2, opacity: disabled || busy ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
        onMouseEnter={(e) => { if (!disabled && !busy) e.currentTarget.style.background = "rgba(212,144,10,0.10)"; }}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
        {busy ? "GENERATING…" : "GENERATE EVIDENCE REPORT"}
      </button>
    </span>
  );
}

// only allow http(s) links from scraped source_url (blocks javascript:/data:)
function safeUrl(url) {
  try {
    const u = new URL(url, typeof window !== "undefined" ? window.location.origin : "http://localhost");
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}
