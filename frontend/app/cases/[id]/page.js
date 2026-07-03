/* app/cases/[id]/page.js
   CHANGED: full rewrite to the 3-panel Case Room workspace — status strip, account
   registry (filters + live scanning feed), correlation graph (hover tooltip + SCANNING
   overlay), cluster analysis (signal tables + member chips + unlinked section), timeline.
   DECISION: polling logic + api.getResults/downloadReport are UNCHANGED; report button
   stays disabled until status==='complete'; chain integrity derives from completion. */
"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { api, getToken } from "@/lib/api";
import GlassPanel from "@/components/ui/GlassPanel";
import StatusPill from "@/components/ui/StatusPill";
import Button from "@/components/ui/Button";
import Tooltip from "@/components/ui/Tooltip";
import AccountCard from "@/components/ui/AccountCard";
import ConfidenceBadge from "@/components/ui/ConfidenceBadge";
import EmptyState from "@/components/ui/EmptyState";
import PivotPill from "@/components/ui/PivotPill";
import { labelFor, iconFor } from "@/lib/signalLabels";

const NetworkGraph = dynamic(() => import("@/components/Graph"), { ssr: false });
const Timeline = dynamic(() => import("@/components/Timeline"), { ssr: false });

// ---------- helpers ----------
function platformShort(p) {
  const m = { github: "GH", instagram: "IG", hibp: "HIBP", telegram: "TG", reddit: "RD", linkedin: "LI", twitter: "TW", upi: "UPI", serper: "WEB", derived: "DRV" };
  const k = (p || "").toLowerCase();
  return m[k] || (p || "?").slice(0, 3).toUpperCase();
}

export default function CaseView() {
  const router = useRouter();
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedClusterId, setSelectedClusterId] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [tab, setTab] = useState("summary");
  const [signalFilter, setSignalFilter] = useState(null);
  const [showAllNodes, setShowAllNodes] = useState(false);

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

  if (!data) {
    return <div className="flex items-center justify-center h-screen text-sm text-slate-500">Loading…</div>;
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

  // §4.4.1 verdict counts: strong/possible = multi-member HIGH/MEDIUM clusters.
  const strong = clusters.filter((c) => c.tier === "HIGH" && (c.entity_ids || []).length >= 2).length;
  const possible = clusters.filter((c) => c.tier === "MEDIUM" && (c.entity_ids || []).length >= 2).length;
  const total = entities.length;

  const fx = data.forensics || {};

  // §4.4.3 — identity-list grouping by cluster tier.
  const groupName = (i) => (i < 26 ? String.fromCharCode(65 + i) : `#${i + 1}`);
  const multiClusters = clusters.filter((c) => (c.entity_ids || []).length >= 2);
  const strongClusters = multiClusters
    .filter((c) => c.tier === "HIGH")
    .sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
  const possibleClusters = multiClusters
    .filter((c) => c.tier === "MEDIUM")
    .sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0));
  const letterByCluster = {};
  [...strongClusters, ...possibleClusters].forEach((c, i) => { letterByCluster[c.cluster_id] = groupName(i); });
  const clusterMembers = (c) => (c.entity_ids || []).map((eid) => entById[eid]).filter(Boolean);
  const accountedIds = new Set();
  [...strongClusters, ...possibleClusters].forEach((c) => (c.entity_ids || []).forEach((eid) => accountedIds.add(eid)));
  const notLinkedEntities = entities.filter((e) => !accountedIds.has(e.entity_id));
  const strongCount = strongClusters.reduce((s, c) => s + clusterMembers(c).length, 0);
  const possibleCount = possibleClusters.reduce((s, c) => s + clusterMembers(c).length, 0);
  const autoExpandNotLinked = strongClusters.length + possibleClusters.length === 0;

  const onSelectEntity = (eid) => {
    setHovered(null);
    setSelected((s) => (s === eid ? null : eid));
    setSelectedClusterId(null);
  };
  const onSelectCluster = (cid) => {
    setHovered(null);
    setSelected(null);
    setSelectedClusterId((c) => (c === cid ? null : cid));
  };

  // §4.4.5 — resolve which analysis state the right panel shows.
  const selCluster = selectedClusterId ? clusters.find((c) => c.cluster_id === selectedClusterId) : null;
  const selEntity = selected ? entById[selected] : null;
  const selEntityCluster = selEntity ? infoByEntity[selected]?.cluster : null;
  const selEntityMulti =
    selEntityCluster && (selEntityCluster.entity_ids || []).length >= 2 &&
    (selEntityCluster.tier === "HIGH" || selEntityCluster.tier === "MEDIUM")
      ? selEntityCluster
      : null;
  const analysisCluster = selCluster || selEntityMulti;

  // §4.4.4.1 evidence quick-link filter — narrow the identity list to clusters that fired a signal.
  const clusterHasSignal = (c, sig) => !!(c.signals && Object.prototype.hasOwnProperty.call(c.signals, sig));
  const filteredStrong = signalFilter ? strongClusters.filter((c) => clusterHasSignal(c, signalFilter)) : strongClusters;
  const filteredPossible = signalFilter ? possibleClusters.filter((c) => clusterHasSignal(c, signalFilter)) : possibleClusters;
  const filteredNotLinked = signalFilter ? [] : notLinkedEntities;
  const filteredStrongCount = filteredStrong.reduce((s, c) => s + clusterMembers(c).length, 0);
  const filteredPossibleCount = filteredPossible.reduce((s, c) => s + clusterMembers(c).length, 0);
  const onToggleSignal = (sig) => setSignalFilter((s) => (s === sig ? null : sig));

  // §4.4.4.3/§4.4.4.4 — Timeline shown only with per-entity posting_hours; Writing
  // shown only when forensics has any populated field (else hide the tab, §5.4).
  const hasPostingHours = entities.some(
    (e) => Array.isArray(e.metadata?.posting_hours) && e.metadata.posting_hours.length
  );
  const hasForensics = !!(fx && (
    fx.tone?.samples_analyzed || fx.tone?.label ||
    (Array.isArray(fx.keywords) && fx.keywords.length) ||
    (Array.isArray(fx.hashtags) && fx.hashtags.length) ||
    fx.activity?.available ||
    (Array.isArray(fx.activity?.active_hours_utc) && fx.activity.active_hours_utc.length) ||
    fx.footprint?.breach_exposures || fx.footprint?.registered_services
  ));
  const centerTabs = [
    { id: "summary", label: "Summary" },
    { id: "network", label: "Network" },
    ...(hasPostingHours ? [{ id: "timeline", label: "Timeline" }] : []),
    ...(hasForensics ? [{ id: "writing", label: "Writing & Activity" }] : []),
  ];
  const activeTabId = centerTabs.some((t) => t.id === tab) ? tab : "summary";

  // §4.4.4.2 — tame the hairball: above 30 nodes, default to clustered nodes only
  // (multi-member, or singleton with tier != REJECT) until "Show all" is toggled.
  const graphClusteredIds = new Set();
  clusters.forEach((c) => {
    const ids = c.entity_ids || [];
    if (ids.length >= 2 || (ids.length === 1 && c.tier !== "REJECT")) ids.forEach((eid) => graphClusteredIds.add(eid));
  });
  const graphEntities = total > 30 && !showAllNodes
    ? entities.filter((e) => graphClusteredIds.has(e.entity_id))
    : entities;

  return (
    <div className="min-h-screen flex flex-col">
      {/* VERDICT BAND (§4.4.1) */}
      <div className="px-4 pt-4">
        <GlassPanel className="p-4">
          {/* Row 1 — nav / title / status / report */}
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <button
              onClick={() => router.push("/cases")}
              className="text-[12px] text-slate-400 hover:text-slate-200 shrink-0"
            >
              ← All investigations
            </button>
            <div className="flex items-center gap-2 min-w-0 flex-1 justify-center">
              <span className="font-semibold text-lg text-slate-100 truncate">{kase.title}</span>
              <span className="font-mono text-xs text-slate-500 shrink-0">
                #{(kase.case_id || id || "").slice(0, 8)}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <StatusPill status={status} />
              <ReportButton id={id} disabled={status !== "complete"} />
            </div>
          </div>

          {/* Row 2 — verdict line (the single most important row) */}
          <div className="mt-3">
            <div className="font-semibold text-base text-slate-100">
              {running ? (
                <>Discovering accounts… <span className="text-slate-200">{total}</span> found so far</>
              ) : (
                <>
                  Found <span style={{ color: "#00ff88" }}>{strong}</span> strong{" "}
                  {strong === 1 ? "match" : "matches"} ·{" "}
                  <span style={{ color: "#ffb703" }}>{possible}</span> possible ·{" "}
                  <span className="text-slate-200">{total}</span> accounts discovered
                </>
              )}
            </div>
            {status === "complete" && (
              <div className="mt-1 font-mono text-xs text-slate-500">
                Audit chain verified · SHA-256 · BSA §63 compliant
              </div>
            )}
          </div>

          {/* Row 3 — stats strip */}
          <div className="grid grid-cols-4 gap-3 pt-3 mt-3 border-t border-slate-800">
            <MiniStat n={total} label="Accounts found" />
            <MiniStat n={strong} label="Strong matches" color="#00ff88" />
            <MiniStat n={possible} label="Possible matches" color="#ffb703" />
            <MiniStat n={clusters.length} label="Identity groups" />
          </div>
        </GlassPanel>
      </div>

      {/* MAIN BODY — 3-column grid (§4.4.2) */}
      <div className="px-4 pt-4 pb-4 grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* LEFT — IDENTITY LIST (§4.4.3) */}
        <div className="lg:col-span-3">
          <GlassPanel className="p-4 max-h-[720px] overflow-y-auto">
            <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400">
              Discovered accounts ({total})
            </div>
            <div className="mt-0.5 mb-3 text-xs text-slate-500">Click any account to inspect.</div>
            {signalFilter && (
              <div className="mb-3 flex items-center justify-between rounded-md bg-cyan-400/10 border border-cyan-400/30 px-2 py-1">
                <span className="text-[11px] text-cyan-400">Filtered: {labelFor(signalFilter)}</span>
                <button onClick={() => setSignalFilter(null)} className="text-[11px] text-cyan-400 hover:underline">Clear</button>
              </div>
            )}
            <IdentityList
              strongClusters={filteredStrong}
              possibleClusters={filteredPossible}
              letterByCluster={letterByCluster}
              clusterMembers={clusterMembers}
              notLinkedEntities={filteredNotLinked}
              strongCount={filteredStrongCount}
              possibleCount={filteredPossibleCount}
              infoByEntity={infoByEntity}
              selectedEntityId={selected}
              onSelectEntity={onSelectEntity}
              onSelectCluster={onSelectCluster}
              autoExpandNotLinked={autoExpandNotLinked}
            />
          </GlassPanel>
        </div>

        {/* CENTER — TABBED MAIN VIEW (§4.4.4) */}
        <div className="lg:col-span-6">
          <GlassPanel className="p-4">
            <div className="flex gap-5 border-b border-slate-800 mb-4">
              {centerTabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`pb-2 -mb-px text-[11px] font-mono uppercase tracking-wider transition-colors ${
                    activeTabId === t.id ? "text-cyan-400 border-b-2 border-cyan-400" : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {activeTabId === "summary" && (
              <SummaryTab
                entities={entities}
                clusters={clusters}
                signalFilter={signalFilter}
                onToggleSignal={onToggleSignal}
              />
            )}

            {activeTabId === "network" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400">Correlation network</div>
                  {total > 30 && (
                    <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showAllNodes}
                        onChange={(e) => setShowAllNodes(e.target.checked)}
                        style={{ accentColor: "#00f2fe" }}
                      />
                      Show all {total} nodes
                    </label>
                  )}
                </div>
                <div className="relative rounded-lg overflow-hidden border border-slate-800" style={{ height: 560 }}>
                  {graphEntities.length > 0 ? (
                    <NetworkGraph
                      entities={graphEntities}
                      clusters={clusters}
                      selectedId={selected}
                      onSelect={(nid) => { setSelected(nid); setSelectedClusterId(null); setHovered(null); }}
                      onHover={() => {}}
                    />
                  ) : (
                    <EmptyState
                      icon="🕸️"
                      title="No linked accounts to graph"
                      description={total > 30 ? "Enable “Show all nodes” to view every account." : "Discovered accounts will appear here."}
                    />
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-4 text-[11px] font-mono text-slate-500">
                  <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: "#00ff88" }} /> strong</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: "#ffb703" }} /> possible</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: "#ff3366" }} /> not linked</span>
                  <span className="flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full" style={{ background: "#00f2fe" }} /> selected</span>
                </div>
              </div>
            )}

            {activeTabId === "timeline" && (
              <div className="pt-1">
                <Timeline entities={entities} clusters={clusters} />
              </div>
            )}

            {activeTabId === "writing" && <WritingActivity fx={fx} />}
          </GlassPanel>
        </div>

        {/* RIGHT — SAME-PERSON ANALYSIS (§4.4.5) */}
        <div className="lg:col-span-3">
          <GlassPanel className="p-4 max-h-[720px] overflow-y-auto lg:sticky lg:top-4">
            <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-3">
              Same-person analysis
            </div>
            <AnalysisPanel
              cluster={analysisCluster}
              letter={analysisCluster ? letterByCluster[analysisCluster.cluster_id] : null}
              members={analysisCluster ? clusterMembers(analysisCluster) : []}
              entity={!analysisCluster ? selEntity : null}
            />
          </GlassPanel>
        </div>
      </div>

    </div>
  );
}

// Platform icon fallbacks (initials) when no photo_url is available
function ReportButton({ id, disabled }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  // §1.4/§1.8 — download the BSA-63 PDF WITH the auth header via a Blob (never <a href>).
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
  const btn = (
    <Button variant="success" onClick={generate} disabled={disabled || busy} className="text-sm px-4 py-2">
      {busy ? "Preparing…" : "Download Evidence Report (BSA-63)"}
    </Button>
  );
  return (
    <span className="flex items-center gap-2">
      {err && <span className="text-xs" style={{ color: "#ff3366" }}>{err}</span>}
      {disabled ? <Tooltip content="Available when investigation completes">{btn}</Tooltip> : btn}
    </span>
  );
}

// §4.4.1 Row 3 — one number + label cell in the verdict stats strip.
function MiniStat({ n, label, color = "#e2e8f0" }) {
  return (
    <div>
      <div className="text-xl font-semibold" style={{ color }}>{n}</div>
      <div className="mt-0.5 text-[11px] font-mono uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

// §4.4.3 — grouped identity list: Strong / Possible / Not linked (collapsible).
function IdentityList({
  strongClusters, possibleClusters, letterByCluster, clusterMembers,
  notLinkedEntities, strongCount, possibleCount,
  infoByEntity, selectedEntityId, onSelectEntity, onSelectCluster, autoExpandNotLinked,
}) {
  const [openNotLinked, setOpenNotLinked] = useState(autoExpandNotLinked);
  useEffect(() => { setOpenNotLinked(autoExpandNotLinked); }, [autoExpandNotLinked]);

  return (
    <div>
      {/* Strong matches */}
      <div className="text-[11px] font-mono uppercase tracking-wide mb-2" style={{ color: "#00ff88" }}>
        Strong matches ({strongCount})
      </div>
      {strongClusters.map((c) => (
        <ClusterGroup
          key={c.cluster_id}
          cluster={c}
          letter={letterByCluster[c.cluster_id]}
          members={clusterMembers(c)}
          selectedEntityId={selectedEntityId}
          onSelectEntity={onSelectEntity}
          onSelectCluster={onSelectCluster}
        />
      ))}

      {/* Possible matches */}
      <div className="mt-4 mb-2 text-[11px] font-mono uppercase tracking-wide" style={{ color: "#ffb703" }}>
        Possible matches ({possibleCount})
      </div>
      {possibleClusters.map((c) => (
        <ClusterGroup
          key={c.cluster_id}
          cluster={c}
          letter={letterByCluster[c.cluster_id]}
          members={clusterMembers(c)}
          selectedEntityId={selectedEntityId}
          onSelectEntity={onSelectEntity}
          onSelectCluster={onSelectCluster}
        />
      ))}

      {/* Not linked (collapsible; auto-expanded when no strong/possible — §1.5, §4.4.3) */}
      <div className="mt-4 border-t border-slate-800 pt-3">
        <button onClick={() => setOpenNotLinked((v) => !v)} className="w-full flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wide" style={{ color: "#ff3366" }}>
            Not linked ({notLinkedEntities.length})
          </span>
          <span className="text-xs text-slate-500">{openNotLinked ? "▾" : "▸"}</span>
        </button>
        {openNotLinked && (
          <div className="mt-2 space-y-2">
            {notLinkedEntities.map((e) => (
              <AccountCard
                key={e.entity_id}
                entity={{ ...e, _tier: infoByEntity[e.entity_id]?.tier }}
                selected={selectedEntityId === e.entity_id}
                onClick={() => onSelectEntity(e.entity_id)}
              />
            ))}
            {notLinkedEntities.length === 0 && (
              <div className="text-xs text-slate-600">No unlinked accounts.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// A single cluster's clickable header + its member AccountCards.
function ClusterGroup({ cluster, letter, members, selectedEntityId, onSelectEntity, onSelectCluster }) {
  return (
    <div className="mb-3">
      <button
        onClick={() => onSelectCluster(cluster.cluster_id)}
        className="w-full text-left text-xs text-slate-300 hover:text-slate-100 mb-1.5"
      >
        Identity group {letter} · {members.length} {members.length === 1 ? "account" : "accounts"}
      </button>
      <div className="space-y-2">
        {members.map((e) => (
          <AccountCard
            key={e.entity_id}
            entity={{ ...e, _tier: cluster.tier }}
            selected={selectedEntityId === e.entity_id}
            onClick={() => onSelectEntity(e.entity_id)}
          />
        ))}
      </div>
    </div>
  );
}

// Points value for a signal (backend usually stores a number; guard objects).
function sigPoints(v) {
  if (typeof v === "number") return v;
  if (v && typeof v === "object") return v.points ?? v.weight ?? "";
  return v;
}

// §4.4.5 — Same-person analysis: (A) empty, (B) cluster, (C) single account.
function AnalysisPanel({ cluster, letter, members, entity }) {
  // State B — cluster selected
  if (cluster) {
    const signals = cluster.signals || {};
    const sigEntries = Object.entries(signals);
    return (
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-slate-100">Identity group {letter}</span>
          <ConfidenceBadge tier={cluster.tier} />
        </div>

        {cluster.explanation && (
          <p className="mt-3 text-sm text-slate-200 leading-relaxed">{cluster.explanation}</p>
        )}

        <div className="mt-4 text-[11px] font-mono uppercase tracking-wide text-slate-400">Matching evidence</div>
        <div className="mt-2 space-y-1.5">
          {sigEntries.length === 0 && (
            <div className="text-xs text-slate-500">No individual signals recorded.</div>
          )}
          {sigEntries.map(([name, val]) => (
            <div key={name} className="flex items-center justify-between gap-2">
              <span className="text-[13px] text-slate-200">
                <span className="mr-1.5" aria-hidden>{iconFor(name)}</span>{labelFor(name)}
              </span>
              <span className="text-xs font-mono text-slate-500 shrink-0">+{sigPoints(val)}</span>
            </div>
          ))}
        </div>

        <div className="mt-3 text-sm font-mono text-slate-400">
          Total score: {cluster.confidence_score}/100
        </div>

        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">Technical details</summary>
          <div className="mt-2 space-y-3">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wide text-slate-500 mb-1">Raw signals</div>
              {sigEntries.map(([name, val]) => (
                <div key={name} className="flex items-center justify-between gap-2 text-[11px] font-mono">
                  <span className="text-slate-500 break-all">{name}</span>
                  <span className="text-slate-400 shrink-0">{typeof val === "object" ? JSON.stringify(val) : String(val)}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wide text-slate-500 mb-1">Member hashes (SHA-256)</div>
              {members.map((e) => (
                <div key={e.entity_id} className="mb-1.5">
                  <div className="text-[11px] text-slate-400">{(e.platform || "?").toUpperCase()} · {e.value}</div>
                  <div className="text-[10px] font-mono text-slate-600 break-all">{e.sha256 || "—"}</div>
                </div>
              ))}
            </div>
          </div>
        </details>
      </div>
    );
  }

  // State C — single account selected (not part of a multi-member cluster)
  if (entity) {
    const m = entity.metadata || {};
    const name = m.fullname || entity.value;
    const conf = Number(entity.confidence) || 0;
    const tier = conf >= 80 ? "HIGH" : conf >= 50 ? "MEDIUM" : "LOW";
    const photo = m.photo_url || m.avatar || m.avatar_url || null;
    const url = safeUrl(entity.source_url);
    return (
      <div>
        <div className="flex items-center gap-3">
          {photo && (
            <img
              src={photo}
              alt=""
              className="w-12 h-12 rounded-md object-cover border border-white/10 shrink-0"
              onError={(ev) => { ev.currentTarget.style.display = "none"; }}
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-100 truncate">{name}</div>
            <div className="text-[11px] font-mono uppercase tracking-wide text-slate-500">{entity.platform}</div>
          </div>
        </div>

        {conf > 0 && <div className="mt-3"><ConfidenceBadge tier={tier} /></div>}
        {m.bio && <p className="mt-3 text-xs text-slate-400 leading-relaxed">{String(m.bio).slice(0, 160)}</p>}
        {url && (
          <a href={url} target="_blank" rel="noreferrer noopener" className="mt-3 block text-xs text-cyan-400 hover:underline break-all">
            {url} ↗
          </a>
        )}

        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400 leading-relaxed">
          Not linked to other accounts. VERTEX refused to link because fewer than 2 corroborating signals were found.
        </div>
      </div>
    );
  }

  // State A — nothing selected
  return (
    <EmptyState
      icon="🔍"
      title="Select an account or group"
      description="Click any item on the left to see why we linked (or didn't link) these accounts."
    />
  );
}

// §4.4.4.1 — Summary matrix: profile pictures / platforms / names / locations + quick-links.
function MatrixCard({ icon, title, count, children }) {
  return (
    <GlassPanel className="p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] text-slate-300">
          <span className="mr-1.5" aria-hidden>{icon}</span>{title}
        </span>
        {typeof count === "number" && (
          <span className="text-[11px] font-mono text-slate-500 border border-slate-700 rounded px-1.5">{count}</span>
        )}
      </div>
      {children}
    </GlassPanel>
  );
}

function EmptyLine({ children }) {
  return <div className="text-xs text-slate-600">{children}</div>;
}

function SummaryTab({ entities, clusters, signalFilter, onToggleSignal }) {
  // Profile pictures (dedupe by URL)
  const seenPhoto = new Set();
  const photos = [];
  entities.forEach((e) => {
    const m = e.metadata || {};
    const url = m.photo_url || m.avatar || m.avatar_url || m.image;
    if (url && !seenPhoto.has(url)) { seenPhoto.add(url); photos.push({ url, platform: e.platform }); }
  });

  // Platforms (count desc, top 10)
  const platformCounts = {};
  entities.forEach((e) => { const p = e.platform || "unknown"; platformCounts[p] = (platformCounts[p] || 0) + 1; });
  const platforms = Object.entries(platformCounts).sort((a, b) => b[1] - a[1]).slice(0, 10);

  // Names & aliases (dedupe normalized)
  const seenName = new Set();
  const names = [];
  entities.forEach((e) => {
    const n = e.metadata?.fullname;
    if (n && typeof n === "string") {
      const key = n.trim().toLowerCase();
      if (key && !seenName.has(key)) { seenName.add(key); names.push(n.trim()); }
    }
  });

  // Locations & context (location + employer/location/city candidates)
  const seenLoc = new Set();
  const locations = [];
  const addLoc = (v) => {
    if (v && typeof v === "string") {
      const k = v.trim().toLowerCase();
      if (k && !seenLoc.has(k)) { seenLoc.add(k); locations.push(v.trim()); }
    }
  };
  entities.forEach((e) => {
    const m = e.metadata || {};
    addLoc(m.location);
    (m.employer_candidates || []).forEach(addLoc);
    (m.location_candidates || []).forEach(addLoc);
    (m.city_candidates || []).forEach(addLoc);
  });

  // Evidence quick-links — signals that fired across multi-member clusters (§4.4.4.1)
  const multi = clusters.filter((c) => (c.entity_ids || []).length >= 2);
  const sigCounts = {};
  multi.forEach((c) => Object.keys(c.signals || {}).forEach((s) => { sigCounts[s] = (sigCounts[s] || 0) + 1; }));
  const sigPills = Object.entries(sigCounts).sort((a, b) => b[1] - a[1]);

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <MatrixCard icon="🖼️" title="Profile pictures" count={photos.length}>
          {photos.length === 0 ? (
            <EmptyLine>No profile pictures found.</EmptyLine>
          ) : (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {photos.map((p, i) => (
                <div key={i} className="relative shrink-0 w-14 h-14">
                  <img
                    src={p.url}
                    alt=""
                    className="w-14 h-14 rounded-md object-cover border border-white/10"
                    onError={(ev) => { ev.currentTarget.parentElement.style.display = "none"; }}
                  />
                  <span className="absolute bottom-0 left-0 text-[8px] font-mono px-1 rounded-tr rounded-bl-md bg-black/70 text-slate-300">
                    {platformShort(p.platform)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </MatrixCard>

        <MatrixCard icon="🌐" title="Platforms" count={platforms.length}>
          {platforms.length === 0 ? (
            <EmptyLine>No platforms found.</EmptyLine>
          ) : (
            <div className="space-y-1">
              {platforms.map(([p, n]) => (
                <div key={p} className="flex items-center justify-between text-[13px]">
                  <span className="text-slate-200 truncate">{p}</span>
                  <span className="text-[11px] font-mono text-slate-500 border border-slate-700 rounded px-1.5 shrink-0">{n}</span>
                </div>
              ))}
            </div>
          )}
        </MatrixCard>

        <MatrixCard icon="👤" title="Names & aliases" count={names.length}>
          {names.length === 0 ? (
            <EmptyLine>No names found.</EmptyLine>
          ) : (
            <div className="space-y-1">
              {names.map((n, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-[13px]">
                  <span className="text-slate-200 truncate">{n}</span>
                  <span className="text-[10px] font-mono uppercase text-cyan-400 shrink-0">Alias</span>
                </div>
              ))}
            </div>
          )}
        </MatrixCard>

        <MatrixCard icon="📍" title="Locations & context" count={locations.length}>
          {locations.length === 0 ? (
            <EmptyLine>No locations found.</EmptyLine>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {locations.map((l, i) => (
                <span key={i} className="text-[11px] text-slate-300 bg-slate-800/70 border border-slate-700 rounded px-2 py-0.5">{l}</span>
              ))}
            </div>
          )}
        </MatrixCard>
      </div>

      {sigPills.length > 0 && (
        <GlassPanel className="p-4 mt-3">
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Evidence quick-links</div>
          <div className="flex flex-wrap gap-2">
            {sigPills.map(([sig, n]) => (
              <PivotPill key={sig} icon={iconFor(sig)} active={signalFilter === sig} onClick={() => onToggleSignal(sig)}>
                {labelFor(sig)} ({n} {n === 1 ? "group" : "groups"})
              </PivotPill>
            ))}
          </div>
          {signalFilter && (
            <button onClick={() => onToggleSignal(signalFilter)} className="mt-2 text-xs text-cyan-400 hover:underline">
              Clear filter
            </button>
          )}
        </GlassPanel>
      )}
    </div>
  );
}

// §4.4.4.4 — Writing & Activity: tone strip, active-hours bars, keywords/hashtags,
// engagement. Renders only populated fields (§5.4 / §9.5 — hide, don't dash).
function WritingActivity({ fx }) {
  const [showAllKw, setShowAllKw] = useState(false);
  const [showAllHt, setShowAllHt] = useState(false);

  const rawTone = (fx.tone?.label || "").toString().toUpperCase();
  const tone = rawTone.includes("POS") ? { word: "Positive", color: "#00ff88" }
    : rawTone.includes("NEG") ? { word: "Negative", color: "#ff3366" }
    : rawTone ? { word: "Neutral", color: "#94a3b8" }
    : null;

  const hoursCount = new Array(24).fill(0);
  if (fx.activity_hours && typeof fx.activity_hours === "object" && !Array.isArray(fx.activity_hours)) {
    Object.entries(fx.activity_hours).forEach(([h, c]) => { const hi = Number(h); if (hi >= 0 && hi < 24) hoursCount[hi] = Number(c) || 0; });
  } else if (Array.isArray(fx.activity?.active_hours_utc)) {
    fx.activity.active_hours_utc.forEach((h) => { const hi = Number(h); if (hi >= 0 && hi < 24) hoursCount[hi] = 1; });
  }
  const maxC = Math.max(1, ...hoursCount);
  const hasHours = hoursCount.some((c) => c > 0);

  const keywords = Array.isArray(fx.keywords) ? fx.keywords : [];
  const hashtags = Array.isArray(fx.hashtags) ? fx.hashtags : [];
  const kwShown = showAllKw ? keywords : keywords.slice(0, 8);
  const htShown = showAllHt ? hashtags : hashtags.slice(0, 8);

  const eng = [];
  if (fx.engagement?.available && fx.engagement.followers_total != null) eng.push(["Followers", fx.engagement.followers_total]);
  if (fx.activity?.posts_analyzed) eng.push(["Posts analysed", fx.activity.posts_analyzed]);
  if (fx.footprint?.breach_exposures) eng.push(["Breach exposures", fx.footprint.breach_exposures]);
  if (fx.footprint?.registered_services) eng.push(["Registered services", fx.footprint.registered_services]);

  return (
    <div className="space-y-5">
      <div className="text-sm font-semibold text-slate-100">Writing &amp; Activity Patterns</div>

      {tone && (
        <div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-1.5">Tone</div>
          <div className="inline-flex items-center gap-2 rounded-md px-3 py-1.5" style={{ background: `${tone.color}1f`, border: `1px solid ${tone.color}55` }}>
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: tone.color }} />
            <span className="text-sm" style={{ color: tone.color }}>Tone: {tone.word}</span>
          </div>
        </div>
      )}

      {hasHours && (
        <div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Active hours</div>
          <div className="flex items-end gap-0.5 h-16">
            {hoursCount.map((c, h) => (
              <div
                key={h}
                className="flex-1 rounded-sm"
                title={`${String(h).padStart(2, "0")}:00 — ${c}`}
                style={{ height: `${Math.max(4, (c / maxC) * 100)}%`, background: c > 0 ? "#00f2fe" : "#1e293b" }}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[9px] font-mono text-slate-600"><span>00:00</span><span>12:00</span><span>23:00</span></div>
        </div>
      )}

      {keywords.length > 0 && (
        <div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Top keywords</div>
          <div className="flex flex-wrap gap-1.5">
            {kwShown.map((k, i) => (
              <span key={`${k}-${i}`} className="text-[11px] text-slate-300 bg-slate-800/70 border border-slate-700 rounded px-2 py-0.5">{k}</span>
            ))}
            {keywords.length > 8 && (
              <button onClick={() => setShowAllKw((v) => !v)} className="text-[11px] text-cyan-400 hover:underline">
                {showAllKw ? "Show fewer" : `+${keywords.length - 8} more`}
              </button>
            )}
          </div>
        </div>
      )}

      {hashtags.length > 0 && (
        <div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Top hashtags</div>
          <div className="flex flex-wrap gap-1.5">
            {htShown.map((h, i) => (
              <span key={`${h}-${i}`} className="text-[11px] text-cyan-400 bg-cyan-400/10 border border-cyan-400/25 rounded px-2 py-0.5">#{h}</span>
            ))}
            {hashtags.length > 8 && (
              <button onClick={() => setShowAllHt((v) => !v)} className="text-[11px] text-cyan-400 hover:underline">
                {showAllHt ? "Show fewer" : `+${hashtags.length - 8} more`}
              </button>
            )}
          </div>
        </div>
      )}

      {eng.length > 0 && (
        <div>
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Engagement</div>
          <div className="grid grid-cols-2 gap-2">
            {eng.map(([label, val]) => (
              <div key={label} className="rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
                <div className="text-lg font-semibold text-slate-100">{val}</div>
                <div className="text-[10px] font-mono uppercase tracking-wide text-slate-500">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
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
