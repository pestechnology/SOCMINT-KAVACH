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
  const [platformFilter, setPlatformFilter] = useState("ALL");
  const [scoreFilter, setScoreFilter] = useState("ALL");
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

  const uniquePlatforms = Array.from(new Set(entities.map((e) => (e.platform || "").toLowerCase()))).filter(Boolean).sort();

  const sorted = [...entities].sort((a, b) => (infoByEntity[b.entity_id]?.score || 0) - (infoByEntity[a.entity_id]?.score || 0));
  const visible = sorted.filter((e) => {
    const p = (e.platform || "").toLowerCase();
    const tier = infoByEntity[e.entity_id]?.tier || "REJECT";
    const passTierBtn = filter === "ALL" || tier === filter;
    const passPlatform = platformFilter === "ALL" || p === platformFilter;
    const passScore = scoreFilter === "ALL" || tier === scoreFilter;
    return passTierBtn && passPlatform && passScore;
  });

  const multi = clusters.filter((c) => (c.entity_ids || []).length >= 2);
  const unlinked = clusters.filter((c) => (c.entity_ids || []).length < 2);
  const linkedSorted = [...multi].sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
  const highLinks = multi.filter((c) => c.tier === "HIGH").length;
  const topScore = clusters.reduce((m, c) => Math.max(m, c.confidence_score || 0), 0);

  const activeEntId = hovered || selected;
  const hoveredEnt = activeEntId ? entById[activeEntId] : null;
  const hoveredInfo = activeEntId ? infoByEntity[activeEntId] : null;
  const fx = data.forensics || {};
  const galleryItems = buildGalleryItems(entities, infoByEntity);

  return (
    <div className="min-h-screen flex flex-col bg-ink">
      {/* TOP BAR */}
      <div className="bg-surface border-b border-edge flex items-center justify-between" style={{ padding: "10px 20px" }}>
        <button onClick={() => router.push("/cases")} className="mono text-dim hover:text-amber" style={{ fontSize: 10 }}>← Registry</button>
        <div className="flex items-center" style={{ gap: 8, maxWidth: "50%" }}>
          <div className="display text-head truncate" style={{ fontSize: 15, fontWeight: 500 }}>{kase.title}</div>
          {kase.country_filter && kase.country_filter !== "ALL" && (
            <span className="mono text-amber shrink-0" style={{ fontSize: 9, border: "0.5px solid #D4900A", borderRadius: 2, padding: "1px 5px", letterSpacing: "0.08em" }}>
              [{kase.country_filter}]
            </span>
          )}
        </div>
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
      <div className="flex overflow-hidden" style={{ minHeight: 0, height: "64vh", flexShrink: 0 }}>
        {/* LEFT — ACCOUNT REGISTRY */}
        <div className="overflow-y-auto bg-surface border-r border-edge" style={{ width: 260, flexShrink: 0 }}>
          <div className="panel-label sticky top-0 bg-surface border-b border-edge" style={{ padding: "10px 14px" }}>
            DISCOVERED ACCOUNTS ({entities.length})
          </div>

          {!running && (
            <div className="flex flex-col border-b border-edge bg-lifted" style={{ gap: 8, padding: "10px 14px" }}>
              <div className="flex" style={{ gap: 4 }}>
                {FILTERS.map(([label, val]) => (
                  <button key={val} onClick={() => { setFilter(val); if (val !== "ALL") setScoreFilter(val); else setScoreFilter("ALL"); }} className="mono flex-1"
                    style={{ fontSize: 8, padding: "3px 4px", borderRadius: 2, border: "0.5px solid", borderColor: (filter === val || scoreFilter === val) ? "#D4900A" : "#2A3148", color: (filter === val || scoreFilter === val) ? "#D4900A" : "#4A5568", background: "transparent", textAlign: "center" }}>
                    {label}
                  </button>
                ))}
              </div>
              <div>
                <label className="mono text-dim block mb-1" style={{ fontSize: 8, letterSpacing: "0.08em", color: "#8A97AD" }}>PLATFORM FILTER</label>
                <select
                  value={platformFilter}
                  onChange={(e) => setPlatformFilter(e.target.value)}
                  className="mono bg-ink text-head w-full"
                  style={{ fontSize: 8, padding: "4px 6px", border: "1px solid #2A3148", borderRadius: 2 }}
                >
                  <option value="ALL">ALL PLATFORMS ({uniquePlatforms.length})</option>
                  {uniquePlatforms.map((p) => (
                    <option key={p} value={p}>{p.toUpperCase()}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mono text-dim block mb-1" style={{ fontSize: 8, letterSpacing: "0.08em", color: "#8A97AD" }}>CONFIDENCE SCORE</label>
                <select
                  value={scoreFilter}
                  onChange={(e) => {
                    setScoreFilter(e.target.value);
                    if (e.target.value === "ALL" || e.target.value === "HIGH" || e.target.value === "MEDIUM" || e.target.value === "LOW" || e.target.value === "REJECT") {
                      setFilter(e.target.value);
                    }
                  }}
                  className="mono bg-ink text-head w-full"
                  style={{ fontSize: 8, padding: "4px 6px", border: "1px solid #2A3148", borderRadius: 2 }}
                >
                  <option value="ALL">ALL SCORES</option>
                  <option value="HIGH">HIGH CONFIDENCE</option>
                  <option value="MEDIUM">MEDIUM CONFIDENCE</option>
                  <option value="LOW">LOW CONFIDENCE</option>
                  <option value="REJECT">REJECTED</option>
                </select>
              </div>
            </div>
          )}

          <div className="divide-y divide-edge">
            {visible.map((e) => (
              <AccountCard
                key={e.entity_id}
                e={e}
                info={infoByEntity[e.entity_id]}
                active={activeEntId === e.entity_id}
                onClick={() => setSelected((s) => (s === e.entity_id ? null : e.entity_id))}
              />
            ))}
            {visible.length === 0 && !running && (
              <div className="mono text-dim text-center" style={{ fontSize: 9, padding: 20 }}>No matching accounts</div>
            )}
            {running && (
              <div className="flex flex-col bg-ink border-t border-edge" style={{ padding: "12px 14px", gap: 6 }}>
                <div className="mono text-amber flex items-center" style={{ fontSize: 9, gap: 6 }}>
                  <span className="status-dot-running" /> SCANNING LIVE FEED…
                </div>
                {logLines.length === 0 && <div className="mono text-dim" style={{ fontSize: 8 }}>● initializing scrapers…</div>}
                <div className="flex flex-col overflow-y-auto" style={{ maxHeight: "250px", gap: 3 }}>
                  {logLines.map((l, i) => (
                    <div key={i} className="mono tier-complete" style={{ fontSize: 8, lineHeight: 1.4, whiteSpace: "pre-wrap" }}>{l}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* MIDDLE — DETAIL / EVIDENCE / GRAPH */}
        <div className="flex flex-col flex-1 bg-ink border-r border-edge" style={{ minWidth: 0 }}>
          {!hoveredEnt ? (
            <div className="flex flex-col flex-1 h-full bg-surface">
              <div className="panel-label border-b border-edge flex items-center justify-between" style={{ padding: "10px 14px", background: "#131722", flexShrink: 0 }}>
                <span>CORRELATION GRAPH</span>
                <span className="mono text-dim" style={{ fontSize: 8 }}>← Click any node or account card for details</span>
              </div>
              <div className="relative flex-1" style={{ minHeight: 0 }} onMouseMove={(ev) => setMouse({ x: ev.clientX, y: ev.clientY })}>
                {entities.length > 0 ? (
                  <NetworkGraph entities={entities} clusters={clusters} onSelect={(id) => { setSelected(id); setHovered(id); }} onHover={setHovered} />
                ) : (
                  <div className="flex items-center justify-center h-full mono text-dim" style={{ fontSize: 11 }}>AWAITING DATA</div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto">
              <div className="panel-label sticky top-0 bg-surface border-b border-edge flex items-center justify-between" style={{ padding: "10px 14px" }}>
                <span>ACCOUNT DETAILS</span>
                <button onClick={() => { setSelected(null); setHovered(null); }} className="mono text-amber hover:underline" style={{ fontSize: 8 }}>✕ Close Details</button>
              </div>
              <div style={{ padding: 16 }}>
                <div className="flex items-start justify-between border-b border-edge pb-3 mb-3">
                  <div className="flex items-center" style={{ gap: 10 }}>
                    <PlatformIcon platform={hoveredEnt.platform} size={32} />
                    <div>
                      <div className="display text-head" style={{ fontSize: 16, fontWeight: 500 }}>
                        {hoveredEnt.metadata?.fullname || hoveredEnt.metadata?.name || hoveredEnt.value}
                      </div>
                      <div className="mono text-dim" style={{ fontSize: 10 }}>
                        {(hoveredEnt.platform || "?").toUpperCase()} · <span style={{ color: "#E2E8F0" }}>{hoveredEnt.value}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="mono" style={{ fontSize: 20, color: "#D4900A", fontWeight: 500 }}>
                      {hoveredInfo?.score ?? 0}<span style={{ fontSize: 10 }}>/100</span>
                    </div>
                    <ConfidenceLabel tier={hoveredInfo?.tier || "REJECT"} signals={hoveredInfo?.cluster?.signals} />
                  </div>
                </div>

                {hoveredInfo?.cluster?.explanation && (
                  <div className="bg-lifted border border-edge mb-4" style={{ padding: "10px 12px", borderLeft: "2px solid #D4900A" }}>
                    <div className="mono text-dim" style={{ fontSize: 8, letterSpacing: "0.08em", marginBottom: 3 }}>CORRELATION FORENSIC RATIONALE</div>
                    <div className="display text-body" style={{ fontSize: 11, lineHeight: 1.5 }}>
                      {hoveredInfo.cluster.explanation}
                    </div>
                  </div>
                )}

                <div className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em", marginBottom: 6 }}>
                  EXTRACTED METADATA ({Object.keys(hoveredEnt.metadata || {}).length} fields)
                </div>
                <div className="bg-surface border border-edge mb-4" style={{ padding: "10px 12px" }}>
                  {Object.entries(hoveredEnt.metadata || {}).length === 0 ? (
                    <div className="mono text-dim" style={{ fontSize: 9 }}>No metadata extracted</div>
                  ) : (
                    Object.entries(hoveredEnt.metadata || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between py-1 border-b border-edge last:border-0" style={{ fontSize: 9 }}>
                        <span className="mono text-dim">{k}</span>
                        <span className="mono text-head text-right break-all" style={{ maxWidth: "60%" }}>
                          {typeof v === "object" ? JSON.stringify(v) : String(v)}
                        </span>
                      </div>
                    ))
                  )}
                </div>

                <div className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em", marginBottom: 6 }}>
                  CORROBORATED SIGNALS ({hoveredInfo?.cluster?.signals ? Object.keys(hoveredInfo.cluster.signals).length : 0})
                </div>
                <div className="bg-surface border border-edge" style={{ padding: "10px 12px" }}>
                  {!hoveredInfo?.cluster?.signals || Object.keys(hoveredInfo.cluster.signals).length === 0 ? (
                    <div className="mono text-dim" style={{ fontSize: 9 }}>No cross-platform signals matched</div>
                  ) : (
                    Object.entries(hoveredInfo.cluster.signals).map(([sig, val]) => (
                      <div key={sig} className="flex justify-between py-1 border-b border-edge last:border-0" style={{ fontSize: 9 }}>
                        <span className="mono text-amber">{sig}</span>
                        <span className="mono text-head text-right break-all" style={{ maxWidth: "60%" }}>
                          {typeof val === "object" ? JSON.stringify(val) : String(val)}
                        </span>
                      </div>
                    ))
                  )}
                </div>

                <div style={{ marginTop: 16 }}>
                  <div className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em", marginBottom: 6 }}>CHAIN OF CUSTODY</div>
                  <div className="bg-surface border border-edge" style={{ padding: "10px 12px" }}>
                    <div className="mono text-dim" style={{ fontSize: 8 }}>INTERNAL ENTITY ID</div>
                    <div className="mono text-head" style={{ fontSize: 9, marginBottom: 8 }}>{hoveredEnt.entity_id}</div>
                    <div className="mono text-dim" style={{ fontSize: 8 }}>SHA-256 RAW PAYLOAD HASH</div>
                    <div className="hash-val" style={{ fontSize: 9, wordBreak: "break-all" }}>{hoveredEnt.sha256 || "—"}</div>
                    {hoveredEnt.source_url && (
                      <div style={{ marginTop: 8 }}>
                        <div className="mono text-dim" style={{ fontSize: 8 }}>ORIGIN URL</div>
                        <a href={hoveredEnt.source_url} target="_blank" rel="noreferrer noopener" className="mono text-amber hover:underline break-all" style={{ fontSize: 9 }}>
                          {hoveredEnt.source_url} ↗
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
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
                <span className="mono text-dim" style={{ fontSize: 9 }}>{(showUnlinked || multi.length === 0) ? "▾ hide" : "▸ expand"}</span>
              </button>
              {(showUnlinked || (status === "complete" && multi.length === 0)) && unlinked.map((c) => {
                const e = entById[(c.entity_ids || [])[0]];
                return (
                  <div key={c.cluster_id} className="border-t border-edge" style={{ padding: "8px 14px", opacity: 0.7 }}>
                    <div className="mono text-dim" style={{ fontSize: 9 }}>
                      {(e?.platform || "?").toUpperCase()} · {e?.value || "—"}
                    </div>
                    <div className="display text-dim" style={{ fontSize: 9, fontStyle: "italic", marginTop: 2 }}>
                      {c.signals && Object.keys(c.signals).length ? "Single signal — insufficient to link across platforms" : "No corroborating signals found"}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* MEDIA GALLERY — every profile photo + real post image found, with source link */}
      {!running && (
        <div className="border-t border-edge bg-surface">
          <div className="panel-label" style={{ padding: "10px 16px" }}>
            MEDIA GALLERY ({galleryItems.length})
          </div>
          {galleryItems.length === 0 ? (
            <div className="mono text-dim text-center" style={{ fontSize: 10, padding: "24px 0" }}>
              NO IMAGES RECOVERED FOR THIS CASE
            </div>
          ) : (
            <div className="flex flex-wrap" style={{ gap: 10, padding: "12px 16px" }}>
              {galleryItems.map((item) => <GalleryTile key={item.key} item={item} />)}
            </div>
          )}
        </div>
      )}

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

// Platform icon fallbacks (initials) when no photo_url is available
const PLATFORM_ICONS = {
  github: "GH", instagram: "IG", twitter: "TW", telegram: "TG", reddit: "RD",
  linkedin: "LI", youtube: "YT", tiktok: "TK", facebook: "FB", snapchat: "SC",
  pinterest: "PT", tumblr: "TB", mastodon: "MD", spotify: "SP", twitch: "TV",
};
function PlatformIcon({ platform, size = 36 }) {
  const abbr = PLATFORM_ICONS[(platform || "").toLowerCase()] || (platform || "?").slice(0, 2).toUpperCase();
  return (
    <div style={{ width: size, height: size, borderRadius: 4, background: "#2A3148", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
      <span className="mono text-dim" style={{ fontSize: size * 0.28, letterSpacing: "0.05em" }}>{abbr}</span>
    </div>
  );
}

const STRONG_SIGNALS = ["exact_email_match", "exact_phone_match", "exact_upi_match",
  "profile_photo_phash", "exact_name_match"];

// Confirmed / Possible lead / Unconfirmed label based on tier and signals
function ConfidenceLabel({ tier, signals }) {
  const sigs = signals ? Object.keys(signals) : [];
  const hasStrong = sigs.some((s) => STRONG_SIGNALS.includes(s));

  if ((tier === "HIGH" || tier === "MEDIUM") && hasStrong) {
    return <span className="mono tier-complete" style={{ fontSize: 8 }}>● CONFIRMED</span>;
  }
  if (tier === "LOW" || ((tier === "HIGH" || tier === "MEDIUM") && !hasStrong)) {
    return <span className="mono tier-high" style={{ fontSize: 8 }}>◐ POSSIBLE LEAD (username-only, unconfirmed)</span>;
  }
  return <span className="mono tier-reject" style={{ fontSize: 8 }}>○ UNCONFIRMED</span>;
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
  const photoUrl = m.photo_url || m.avatar || m.avatar_url || m.image || null;

  return (
    <div
      onClick={onClick}
      className="cursor-pointer border-b border-edge relative"
      style={{ padding: "10px 14px", borderLeft: `2.5px solid ${accent}`, background: active ? "#1E2235" : "transparent", opacity: isReject ? 0.5 : 1 }}
    >
      {/* Header: avatar + platform + score */}
      <div className="flex items-start" style={{ gap: 8 }}>
        {photoUrl ? (
          <img src={photoUrl} alt="" style={{ width: 36, height: 36, borderRadius: 4, objectFit: "cover", flexShrink: 0, border: `1px solid ${accent}` }}
            onError={(ev) => { ev.currentTarget.style.display = "none"; ev.currentTarget.nextSibling.style.display = "flex"; }} />
        ) : null}
        <div style={{ display: photoUrl ? "none" : "flex" }}>
          <PlatformIcon platform={e.platform} size={36} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between">
            <span className="mono text-dim" style={{ fontSize: 9, letterSpacing: "0.08em" }}>{(e.platform || "").toUpperCase()}</span>
            <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 4 }}>
              <div className={`mono ${TIER_CLASS[tier]}`} style={{ fontSize: 16, fontWeight: 500, lineHeight: 1 }}>{score}</div>
              <div className={`mono ${TIER_CLASS[tier]}`} style={{ fontSize: 8, marginTop: 1 }}>{TIER_SHORT[tier]}</div>
            </div>
          </div>
          <div className="display text-head" style={{ fontSize: 13, fontWeight: 500, marginTop: 2, wordBreak: "break-all" }}>{e.value}</div>
          {m.title && <div className="mono text-dim" style={{ fontSize: 9, marginTop: 1, wordBreak: "break-word" }}>{m.title}</div>}
        </div>
      </div>

      {/* Confirmed / unconfirmed label — every card gets one */}
      <div style={{ marginTop: 4 }}>
        <ConfidenceLabel tier={tier} signals={info?.cluster?.signals} />
      </div>

      <div style={{ marginTop: 5 }}>
        {m.fullname && <div className="display text-body" style={{ fontSize: 11 }}>{m.fullname}</div>}
        {m.location && <MetaRow label="LOC">{m.location}</MetaRow>}
        {m.bio && <MetaRow label="BIO">{String(m.bio).slice(0, 60)}{String(m.bio).length > 60 ? "…" : ""}</MetaRow>}
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

function buildGalleryItems(entities, infoByEntity) {
  const seenUrls = new Set();
  const seenPhashes = new Set();
  const items = [];

  entities.forEach((e) => {
    const m = e.metadata || {};
    const info = infoByEntity[e.entity_id];
    const tier = info?.tier || "REJECT";
    const sigs = info?.cluster?.signals ? Object.keys(info.cluster.signals) : [];
    const confirmed = (tier === "HIGH" || tier === "MEDIUM") &&
                      sigs.some((s) => STRONG_SIGNALS.includes(s));

    const avatarUrl = m.photo_url || m.avatar || m.avatar_url || m.image || null;
    if (avatarUrl && tier !== "REJECT") {
      const phash = m.photo_phash || null;
      const isDup = phash ? seenPhashes.has(phash) : seenUrls.has(avatarUrl);
      if (!isDup) {
        if (phash) seenPhashes.add(phash);
        seenUrls.add(avatarUrl);
        items.push({
          key: `avatar-${e.entity_id}`,
          url: avatarUrl,
          platform: e.platform || "?",
          label: m.fullname || m.name || e.value || "",
          postedAt: m.created_at || null,
          confirmed,
          tier,
          link: safeUrl(e.source_url),
        });
      }
    }

    const posts = Array.isArray(m.recent_posts) ? m.recent_posts : [];
    posts.forEach((p, i) => {
      if (!p.image_url || seenUrls.has(p.image_url)) return;
      seenUrls.add(p.image_url);
      items.push({
        key: `post-${e.entity_id}-${i}`,
        url: p.image_url,
        platform: p.platform || e.platform || "?",
        label: p.title || m.fullname || e.value || "",
        postedAt: p.posted_at || null,
        confirmed,
        tier,
        link: safeUrl(p.permalink || e.source_url),
      });
    });
  });

  items.sort((a, b) => {
    if (a.confirmed !== b.confirmed) return a.confirmed ? -1 : 1;
    if (a.postedAt && b.postedAt) return new Date(b.postedAt) - new Date(a.postedAt);
    if (a.postedAt) return -1;
    if (b.postedAt) return 1;
    return 0;
  });
  return items.slice(0, 30);
}

function GalleryTile({ item }) {
  const accent = { HIGH: "#D4900A", MEDIUM: "#5B9BD5", LOW: "#E08A4A", REJECT: "#3A4358" }[item.tier] || "#3A4358";
  const pName = (item.platform || "?").toUpperCase();
  const dateStr = item.postedAt
    ? new Date(item.postedAt).toISOString().slice(0, 16).replace("T", " ") + " UTC"
    : null;

  const content = (
    <div data-gallery-tile className="relative flex flex-col bg-ink border border-edge"
      style={{ width: 108, borderRadius: 4, overflow: "hidden", borderColor: accent }}>
      <div className="relative" style={{ width: 108, height: 108, background: "#161B27" }}>
        <img src={item.url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onError={(ev) => {
            const tile = ev.currentTarget.closest("[data-gallery-tile]");
            if (tile) tile.style.display = "none";
          }} />
        <span className="mono absolute top-1 left-1 px-1 rounded bg-black/75 text-dim"
          style={{ fontSize: 7, letterSpacing: "0.05em" }}>
          {pName}
        </span>
      </div>
      <div className="flex flex-col justify-between flex-1" style={{ padding: "6px 8px", background: "#1A2030" }}>
        <div className="mono text-body" style={{ fontSize: 8, lineHeight: 1.3, maxHeight: 22, overflow: "hidden" }}>
          {item.label ? String(item.label).slice(0, 40) : "—"}
        </div>
        <div style={{ marginTop: 4 }}>
          {dateStr && <div className="mono text-dim" style={{ fontSize: 7 }}>{dateStr}</div>}
          <div className="mt-1 flex items-center">
            {item.confirmed ? (
              <span className="mono tier-complete" style={{ fontSize: 7 }}>● CONFIRMED</span>
            ) : (
              <span className="mono tier-high" style={{ fontSize: 7 }}>◐ POSSIBLE</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  if (item.link) {
    return <a href={item.link} target="_blank" rel="noreferrer noopener" className="block hover:opacity-90 transition-opacity">{content}</a>;
  }
  return content;
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
  if (!url || typeof url !== "string") return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}
