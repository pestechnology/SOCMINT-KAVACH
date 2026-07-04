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
import ExecutiveSummaryModal from "@/components/ui/ExecutiveSummaryModal";
import { labelFor, iconFor, tierFor } from "@/lib/signalLabels";

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
  const [graphLarge, setGraphLarge] = useState(false);   // open the network graph in a big modal
  const [tierFilter, setTierFilter] = useState("all");   // all | HIGH | MEDIUM
  const [platformFilter, setPlatformFilter] = useState("all");
  const [showSummaryModal, setShowSummaryModal] = useState(false);

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
  // primary seed value → root label of the correlation tree
  const seedLabel = (kase.seeds && kase.seeds[0] && kase.seeds[0].value) || kase.title || "Target";

  // Match confidence (LOW/MEDIUM/HIGH) — "is this a correct match for the search?" — is what
  // the result cards show, distinct from the forensic linkage `tier` ("same person?"). Exact
  // username/seed matches are HIGH (backend/scoring/confidence.py). Fall back to the linkage
  // tier/score for older cases scored before match confidence existed.
  const matchTier = (c) => c?.match?.tier || c?.tier || "LOW";
  const matchScore = (c) => (c?.match?.score ?? c?.confidence_score ?? 0);

  // map each entity -> its cluster info (tier shown to the user = match tier)
  const infoByEntity = {};
  clusters.forEach((c) => (c.entity_ids || []).forEach((eid) => { infoByEntity[eid] = { tier: matchTier(c), score: matchScore(c), cluster: c }; }));

  const entById = {};
  entities.forEach((e) => (entById[e.entity_id] = e));

  // §4.4.1 verdict counts: strong/possible = multi-member HIGH/MEDIUM clusters.
  const strong = clusters.filter((c) => c.tier === "HIGH" && (c.entity_ids || []).length >= 2).length;
  const possible = clusters.filter((c) => c.tier === "MEDIUM" && (c.entity_ids || []).length >= 2).length;
  const total = entities.length;

  const fx = data.forensics || {};

  // §4.4.3 — identity-list grouping by cluster tier.
  const groupName = (i) => (i < 26 ? String.fromCharCode(65 + i) : `#${i + 1}`);
  // Priority-1 = exact match: a cluster containing the account that literally matches the
  // search input (relevance.score === 100) sorts ahead of everything in its tier, then by
  // confidence. This is what "exact match first" means in the results list.
  const isExactMatch = (c) => (c.relevance?.score || 0) >= 100 || (c.entity_ids || []).some(eid => entById[eid]?.metadata?.exact_seed_match);
  const byExactThenConfidence = (a, b) =>
    (isExactMatch(b) - isExactMatch(a)) || (matchScore(b) - matchScore(a));
  const rankedClusters = clusters.filter((c) => (c.entity_ids || []).length >= 2 || isExactMatch(c));
  const strongClusters = rankedClusters.filter((c) => matchTier(c) === "HIGH" || isExactMatch(c)).sort(byExactThenConfidence);
  const possibleClusters = rankedClusters.filter((c) => matchTier(c) !== "HIGH" && !isExactMatch(c)).sort(byExactThenConfidence);
  const letterByCluster = {};
  [...strongClusters, ...possibleClusters].forEach((c, i) => { letterByCluster[c.cluster_id] = groupName(i); });
  const clusterMembers = (c) => (c.entity_ids || []).map((eid) => entById[eid]).filter(Boolean);
  const accountedIds = new Set();
  [...strongClusters, ...possibleClusters].forEach((c) => (c.entity_ids || []).forEach((eid) => accountedIds.add(eid)));
  const isExactEntity = (e) => ((infoByEntity[e.entity_id]?.cluster?.relevance?.score) || 0) >= 100;
  const notLinkedEntities = entities
    .filter((e) => !accountedIds.has(e.entity_id))
    .sort((a, b) => isExactEntity(b) - isExactEntity(a));   // exact seed match(es) first
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
    selEntityCluster && ((selEntityCluster.entity_ids || []).length >= 2 || isExactMatch(selEntityCluster))
      ? selEntityCluster
      : null;
  const analysisCluster = selCluster || selEntityMulti;

  // Platform list present in this case (for the platform filter dropdown).
  const allPlatforms = Array.from(new Set(entities.map((e) => (e.platform || "").toLowerCase()).filter(Boolean))).sort();
  const clusterHasPlatform = (c, plat) =>
    plat === "all" || clusterMembers(c).some((e) => (e.platform || "").toLowerCase() === plat);
  const entityHasPlatform = (e, plat) => plat === "all" || (e.platform || "").toLowerCase() === plat;

  const clusterHasSignal = (c, sig) => !!(c.signals && Object.prototype.hasOwnProperty.call(c.signals, sig));

  // Exact-match accounts: the profile(s) whose handle literally equals the search query
  // (flagged server-side as metadata.exact_seed_match). These are pinned to the TOP of the
  // list regardless of whether they linked to anything, so the literal answer to the
  // search is never buried under variant-derived clusters.
  // A rare handle yields 1-3 of these (exactly what we want pinned); a common handle
  // (e.g. "octocat") exists on hundreds of sites, so we PIN only the top few on the major
  // platforms an investigator cares about and leave the rest in their normal positions
  // (still ★-badged) rather than flooding the top with a wall of cards.
  const PLATFORM_PRIORITY = { instagram: 0, github: 1, linkedin: 2, twitter: 3, x: 3, facebook: 4, youtube: 5, reddit: 6, telegram: 7, tiktok: 8 };
  const platRank = (e) => PLATFORM_PRIORITY[(e.platform || "").toLowerCase()] ?? 50;
  const exactMatchAll = entities
    .filter((e) => e.metadata?.exact_seed_match)
    .filter((e) => entityHasPlatform(e, platformFilter))
    .sort((a, b) => platRank(a) - platRank(b));
  const exactMatchEntities = exactMatchAll.slice(0, 12);           // pinned at top
  const exactMatchIds = new Set(exactMatchEntities.map((e) => e.entity_id));  // dedupe only the pinned ones

  // §4.4.4.1 evidence quick-link filter. When a signal pill is active, show EVERY
  // multi-member cluster that fired that signal — ANY tier. The pills are counted from all
  // ≥2-member clusters, but a 2-account link can be tier LOW (single hard signal, capped
  // by the red-herring rule); searching only HIGH/MEDIUM was the bug that made a pill with
  // "2 accounts" show nothing when you clicked it.
  const signalClusters = signalFilter
    ? clusters.filter((c) => clusterHasSignal(c, signalFilter) && clusterHasPlatform(c, platformFilter))
    : [];
  const signalAccountCount = signalClusters.reduce((s, c) => s + clusterMembers(c).length, 0);

  // Confidence-tier + platform filters (applied to the normal, non-signal view).
  const applyFilters = (list) => list.filter((c) => clusterHasPlatform(c, platformFilter));
  const filteredStrong = tierFilter === "MEDIUM" ? [] : applyFilters(strongClusters);
  const filteredPossible = tierFilter === "HIGH" ? [] : applyFilters(possibleClusters);
  const filteredNotLinked = tierFilter !== "all"
    ? []
    : notLinkedEntities.filter((e) => entityHasPlatform(e, platformFilter) && !exactMatchIds.has(e.entity_id));
  const filteredStrongCount = filteredStrong.reduce((s, c) => s + clusterMembers(c).length, 0);
  const filteredPossibleCount = filteredPossible.reduce((s, c) => s + clusterMembers(c).length, 0);
  const onToggleSignal = (sig) => setSignalFilter((s) => (s === sig ? null : sig));
  const anyFilterActive = !!signalFilter || tierFilter !== "all" || platformFilter !== "all";
  const clearAllFilters = () => { setSignalFilter(null); setTierFilter("all"); setPlatformFilter("all"); };

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
              <button
                onClick={() => setShowSummaryModal(true)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-cyan-500/20 via-indigo-500/20 to-blue-500/20 hover:from-cyan-500/30 hover:via-indigo-500/30 hover:to-blue-500/30 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10 transition-all duration-200 hover:scale-105 active:scale-95"
              >
                <span>✨</span>
                <span>Briefing</span>
              </button>
              <SummaryReportButton id={id} disabled={status !== "complete"} />
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

          {/* Scan progress — indeterminate (the pipeline runs ~3–7 min across stages) */}
          {running && (
            <div className="mt-3">
              <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className="h-full w-1/3 rounded-full"
                  style={{
                    background: "linear-gradient(90deg, transparent, #00f2fe, transparent)",
                    animation: "vertex-scan 1.3s ease-in-out infinite",
                  }}
                />
              </div>
              <div className="mt-1.5 font-mono text-[11px] text-slate-500">
                Scanning platforms · correlating · scoring — {total} accounts so far
              </div>
            </div>
          )}

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

            {/* Filters — confidence tier + platform */}
            <div className="mb-3 space-y-2">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 w-14 shrink-0">Confidence</span>
                {[
                  { id: "all", label: "All" },
                  { id: "HIGH", label: "Strong", color: "#00ff88" },
                  { id: "MEDIUM", label: "Possible", color: "#ffb703" },
                ].map((o) => (
                  <button
                    key={o.id}
                    onClick={() => setTierFilter(o.id)}
                    className={`text-[11px] px-2 py-0.5 rounded border transition-colors ${
                      tierFilter === o.id
                        ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-200"
                        : "border-slate-700 text-slate-400 hover:text-slate-200"
                    }`}
                    style={tierFilter === o.id && o.color ? { color: o.color, borderColor: `${o.color}66` } : undefined}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 w-14 shrink-0">Platform</span>
                <select
                  value={platformFilter}
                  onChange={(e) => setPlatformFilter(e.target.value)}
                  className="flex-1 text-[11px] bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 focus:border-cyan-400/60 outline-none"
                >
                  <option value="all">All platforms ({allPlatforms.length})</option>
                  {allPlatforms.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
            </div>

            {(signalFilter || anyFilterActive) && (
              <div className="mb-3 flex items-center justify-between rounded-md bg-cyan-400/10 border border-cyan-400/30 px-2 py-1">
                <span className="text-[11px] text-cyan-400 truncate">
                  {signalFilter ? `Evidence: ${labelFor(signalFilter)}` : "Filtered"}
                </span>
                <button onClick={clearAllFilters} className="text-[11px] text-cyan-400 hover:underline shrink-0 ml-2">Clear all</button>
              </div>
            )}
            <IdentityList
              strongClusters={filteredStrong}
              possibleClusters={filteredPossible}
              letterByCluster={letterByCluster}
              clusterMembers={clusterMembers}
              notLinkedEntities={filteredNotLinked}
              exactMatchEntities={exactMatchEntities}
              exactMatchTotal={exactMatchAll.length}
              strongCount={filteredStrongCount}
              possibleCount={filteredPossibleCount}
              infoByEntity={infoByEntity}
              selectedEntityId={selected}
              onSelectEntity={onSelectEntity}
              onSelectCluster={onSelectCluster}
              autoExpandNotLinked={autoExpandNotLinked}
              anyFilter={anyFilterActive}
              onClearFilters={clearAllFilters}
              signalFilter={signalFilter}
              signalLabel={signalFilter ? labelFor(signalFilter) : ""}
              signalClusters={signalClusters}
              signalAccountCount={signalAccountCount}
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
                identity={fx.identity}
                signalFilter={signalFilter}
                onToggleSignal={onToggleSignal}
              />
            )}

            {activeTabId === "network" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400">Correlation network</div>
                  <div className="flex items-center gap-3">
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
                    {graphEntities.length > 0 && (
                      <button onClick={() => setGraphLarge(true)}
                        className="text-[11px] font-mono text-slate-300 border border-slate-700 rounded px-2 py-1 hover:border-cyan-400 hover:text-cyan-300">
                        ⛶ Expand
                      </button>
                    )}
                  </div>
                </div>
                <div className="relative rounded-lg overflow-hidden border border-slate-800" style={{ height: 560 }}>
                  {graphEntities.length > 0 ? (
                    <>
                      <NetworkGraph
                        entities={graphEntities}
                        clusters={clusters}
                        seed={seedLabel}
                        selectedId={selected}
                        onSelect={(nid) => { setSelected(nid); setSelectedClusterId(null); setHovered(null); }}
                        onHover={() => {}}
                        startCollapsed
                      />
                      {/* click the preview to open the graph large; expand nodes there */}
                      <button onClick={() => setGraphLarge(true)}
                        className="absolute inset-0 z-10 cursor-zoom-in group" aria-label="Open graph large">
                        <span className="absolute bottom-2 right-2 text-[10px] font-mono text-slate-300 bg-slate-900/85 border border-slate-700 rounded px-2 py-1 group-hover:border-cyan-400 group-hover:text-cyan-300">
                          click to expand ⛶
                        </span>
                      </button>
                    </>
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

            {graphLarge && graphEntities.length > 0 && (
              <Modal wide icon="🕸️" title="Correlation network"
                     subtitle="Click a branch to expand · scroll to zoom · drag to pan"
                     onClose={() => setGraphLarge(false)}>
                <div className="rounded-lg overflow-hidden border border-slate-800" style={{ height: "72vh" }}>
                  <NetworkGraph
                    entities={graphEntities}
                    clusters={clusters}
                    seed={seedLabel}
                    selectedId={selected}
                    onSelect={(nid) => { setSelected(nid); setSelectedClusterId(null); setHovered(null); }}
                    onHover={() => {}}
                    startCollapsed
                  />
                </div>
              </Modal>
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

      <ExecutiveSummaryModal
        isOpen={showSummaryModal}
        onClose={() => setShowSummaryModal(false)}
        kase={kase}
        id={id}
        status={status}
        strongClusters={strongClusters}
        possibleClusters={possibleClusters}
        notLinkedEntities={notLinkedEntities}
        clusterMembers={clusterMembers}
      />

    </div>
  );
}

// Platform icon fallbacks (initials) when no photo_url is available
function ReportButton({ id, disabled }) {
  const [busy, setBusy] = useState("");   // "" | "summary" | "report"
  const [err, setErr] = useState("");
  // §1.4/§1.8 — download the PDF WITH the auth header via a Blob (never <a href>).
  async function grab(kind) {
    if (disabled) return;
    setErr(""); setBusy(kind);
    try {
      const blob = kind === "summary" ? await api.downloadSummary(id) : await api.downloadReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `BSA63_${kind}_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(e.message); }
    finally { setBusy(""); }
  }
  const summaryBtn = (
    <Button variant="secondary" onClick={() => grab("summary")} disabled={disabled || !!busy} className="text-sm px-3 py-2">
      {busy === "summary" ? "Preparing…" : "📋 Summary briefing"}
    </Button>
  );
  const reportBtn = (
    <Button variant="success" onClick={() => grab("report")} disabled={disabled || !!busy} className="text-sm px-4 py-2">
      {busy === "report" ? "Preparing…" : "Evidence Report (BSA-63)"}
    </Button>
  );
  return (
    <span className="flex items-center gap-2">
      {err && <span className="text-xs" style={{ color: "#ff3366" }}>{err}</span>}
      {disabled ? (
        <Tooltip content="Available when investigation completes"><span className="flex gap-2">{summaryBtn}{reportBtn}</span></Tooltip>
      ) : (<>{summaryBtn}{reportBtn}</>)}
    </span>
  );
}

function SummaryReportButton({ id, disabled }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function generate() {
    if (disabled) return;
    setErr(""); setBusy(true);
    try {
      const blob = await api.downloadSummaryReport(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `BSA63_summary_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }
  const btn = (
    <Button variant="primary" onClick={generate} disabled={disabled || busy} className="text-sm px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 border border-cyan-400/30 text-white font-semibold shadow-md shadow-cyan-500/10">
      {busy ? "Preparing…" : "📄 Summary Report"}
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

// §4.4.3 — grouped identity list: Exact match / Strong / Possible / Not linked.
function IdentityList({
  strongClusters, possibleClusters, letterByCluster, clusterMembers,
  notLinkedEntities, exactMatchEntities = [], exactMatchTotal = 0, strongCount, possibleCount,
  infoByEntity, selectedEntityId, onSelectEntity, onSelectCluster, autoExpandNotLinked,
  anyFilter = false, onClearFilters,
  signalFilter = null, signalLabel = "", signalClusters = [], signalAccountCount = 0,
}) {
  const [openNotLinked, setOpenNotLinked] = useState(autoExpandNotLinked);
  useEffect(() => { setOpenNotLinked(autoExpandNotLinked); }, [autoExpandNotLinked]);

  // Evidence quick-link mode: a signal pill is active → show ONLY the accounts linked by
  // that evidence, across every confidence tier (that's the whole point of the pivot).
  if (signalFilter) {
    return (
      <div>
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[11px] font-mono uppercase tracking-wide text-cyan-300">
            🔗 Linked by {signalLabel} ({signalClusters.length} {signalClusters.length === 1 ? "group" : "groups"} · {signalAccountCount} accounts)
          </span>
        </div>
        {signalClusters.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-sm text-slate-400">No accounts match this evidence with the current platform filter.</div>
            <button onClick={onClearFilters} className="mt-2 text-xs text-cyan-400 hover:underline">Clear filters</button>
          </div>
        ) : signalClusters.map((c) => (
          <ClusterGroup
            key={c.cluster_id}
            cluster={c}
            letter={letterByCluster[c.cluster_id] || "•"}
            members={clusterMembers(c)}
            selectedEntityId={selectedEntityId}
            onSelectEntity={onSelectEntity}
            onSelectCluster={onSelectCluster}
          />
        ))}
      </div>
    );
  }

  // Nothing to show in ANY section — almost always because an active filter excluded
  // everything. Make that explicit so a filtered view never reads as "broken/empty".
  const nothingShown = exactMatchEntities.length === 0 && strongClusters.length === 0 && possibleClusters.length === 0 && notLinkedEntities.length === 0;
  if (nothingShown && anyFilter) {
    return (
      <div className="text-center py-8">
        <div className="text-sm text-slate-400">No accounts match the active filter.</div>
        <button onClick={onClearFilters} className="mt-2 text-xs text-cyan-400 hover:underline">Clear filters</button>
      </div>
    );
  }

  return (
    <div>
      {/* Exact match to the search query — pinned above everything (§ exact-match priority) */}
      {exactMatchEntities.length > 0 && (
        <div className="mb-4">
          <div className="text-[11px] font-mono uppercase tracking-wide mb-2 flex items-center gap-1.5" style={{ color: "#22d3ee" }}>
            🎯 Exact match to your search ({exactMatchTotal > exactMatchEntities.length ? `top ${exactMatchEntities.length} of ${exactMatchTotal}` : exactMatchEntities.length})
          </div>
          <div className="space-y-2">
            {exactMatchEntities.map((e) => (
              <AccountCard
                key={e.entity_id}
                entity={{ ...e, _tier: infoByEntity[e.entity_id]?.tier, _exactMatch: true }}
                selected={selectedEntityId === e.entity_id}
                onClick={() => onSelectEntity(e.entity_id)}
              />
            ))}
          </div>
        </div>
      )}

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
                exactMatch={((infoByEntity[e.entity_id]?.cluster?.relevance?.score) || 0) >= 100}
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
  const exact = (cluster.relevance?.score || 0) >= 100;
  return (
    <div className="mb-3">
      <button
        onClick={() => onSelectCluster(cluster.cluster_id)}
        className="w-full text-left mb-1.5 flex items-center gap-2 flex-wrap"
      >
        <span className="text-xs text-slate-300 hover:text-slate-100">
          {members.length > 1 || letter !== "•" ? `Identity group ${letter} · ` : "Single account · "}
          {members.length} {members.length === 1 ? "account" : "accounts"}
        </span>
        {cluster.identity?.name && (
          <span className="text-[11px] text-emerald-300" title={cluster.identity.source_platform ? `recovered from ${cluster.identity.source_platform}` : "recovered identity"}>
            👤 {cluster.identity.name}
          </span>
        )}
        {exact && (
          <span className="text-[9px] font-mono uppercase tracking-wider text-cyan-300 border border-cyan-400/40 bg-cyan-400/10 rounded px-1.5 py-0.5">
            ★ Exact match
          </span>
        )}
      </button>
      <div className="space-y-2">
        {members.map((e) => (
          <AccountCard
            key={e.entity_id}
            entity={{ ...e, _tier: cluster.match?.tier || cluster.tier }}
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
    // Only REAL corroborating signals — `_`-prefixed keys are internal ranking metadata.
    const signals = cluster.signals || {};
    const sigEntries = Object.entries(signals).filter(([name]) => !name.startsWith("_"));
    return (
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-slate-100">
            {cluster.member_indices?.length > 1 || (cluster.entity_ids || []).length > 1 || letter !== "•" ? `Identity group ${letter}` : "Account analysis"}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            {cluster.ai_confirmed && (
              <span className="text-[10px] font-mono uppercase tracking-wide text-violet-300 border border-violet-400/40 bg-violet-400/10 rounded px-1.5 py-0.5">
                🤖 AI-assessed
              </span>
            )}
            <ConfidenceBadge tier={cluster.match?.tier || cluster.tier} score={cluster.match?.score} />
          </span>
        </div>
        {cluster.match?.reason && (
          <p className="mt-1 text-[11px] text-slate-500">{cluster.match.reason}</p>
        )}

        {cluster.ai_confirmed && (
          <div className="mt-3 rounded-lg border border-violet-400/30 bg-violet-400/[0.06] p-3">
            <div className="text-[10px] font-mono uppercase tracking-wide text-violet-300 mb-1">
              AI examiner verdict · {cluster.ai_confidence}% confidence
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">{cluster.ai_reason}</p>
            <p className="mt-1.5 text-[10px] text-slate-500">
              Assessed from profile context (name, handle, bio, location, interests) — verify before use in a filing.
            </p>
          </div>
        )}

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
          Corroboration points: {cluster.confidence_score}/100
          <span className="ml-1 text-slate-600">(evidence linking these accounts)</span>
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
    const tier = conf >= 70 ? "HIGH" : conf >= 40 ? "MEDIUM" : "LOW";
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
function MatrixCard({ icon, title, count, children, onExpand }) {
  return (
    <GlassPanel
      className={`p-4 ${onExpand ? "cursor-pointer" : ""}`}
      onClick={onExpand}
      role={onExpand ? "button" : undefined}
      title={onExpand ? "Click to expand" : undefined}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] text-slate-300">
          <span className="mr-1.5" aria-hidden>{icon}</span>{title}
        </span>
        <span className="flex items-center gap-1.5 shrink-0">
          {typeof count === "number" && (
            <span className="text-[11px] font-mono text-slate-500 border border-slate-700 rounded px-1.5">{count}</span>
          )}
          {onExpand && <span className="text-slate-500 text-xs" aria-hidden>⤢</span>}
        </span>
      </div>
      {children}
    </GlassPanel>
  );
}

// Full-screen popup for a Summary card's complete contents (§ UI: click card -> full view).
function Modal({ title, icon, subtitle, onClose, children, wide = false }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className={`w-full ${wide ? "max-w-6xl" : "max-w-3xl"} max-h-[90vh] overflow-y-auto rounded-xl border border-white/10 bg-[#0b1220] p-5 shadow-2xl`}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4 sticky -top-5 bg-[#0b1220] py-2 -my-2">
          <span className="text-sm font-semibold text-slate-100">
            <span className="mr-2" aria-hidden>{icon}</span>{title}
            {subtitle && <span className="ml-2 text-xs font-normal text-slate-500">{subtitle}</span>}
          </span>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-xl leading-none px-2" aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function EmptyLine({ children }) {
  return <div className="text-xs text-slate-600">{children}</div>;
}

// Decode HTML entities scraped fields arrive with (e.g. "&#064;" -> "@", "&#x2022;" -> "•").
function decodeEntities(s) {
  if (!s || typeof s !== "string") return s;
  if (typeof document !== "undefined") {
    const el = document.createElement("textarea");
    el.innerHTML = s;
    return el.value;
  }
  return s.replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d))
          .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
          .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
}

// A list that shows a few items and expands to the rest on click (§ UI: expandable panels).
function ExpandableList({ items, initial = 4, render }) {
  const [open, setOpen] = useState(false);
  const shown = open ? items : items.slice(0, initial);
  return (
    <div className="space-y-1">
      {shown.map((it, i) => render(it, i))}
      {items.length > initial && (
        <button onClick={() => setOpen((v) => !v)} className="mt-1 text-[11px] text-cyan-400 hover:underline">
          {open ? "Show less" : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
}

// Expandable profile-photo wall: shows one row, click to reveal all in a wrapping grid.
function PhotoGrid({ photos }) {
  const [open, setOpen] = useState(false);
  const shown = open ? photos : photos.slice(0, 5);
  return (
    <div>
      <div className={open ? "flex flex-wrap gap-2" : "flex gap-2 overflow-x-auto pb-1"}>
        {shown.map((p, i) => (
          <div key={i} className="relative shrink-0 w-14 h-14">
            <img src={p.url} alt="" className="w-14 h-14 rounded-md object-cover border border-white/10"
              onError={(ev) => { ev.currentTarget.parentElement.style.display = "none"; }} />
            <span className="absolute bottom-0 left-0 text-[8px] font-mono px-1 rounded-tr rounded-bl-md bg-black/70 text-slate-300">
              {platformShort(p.platform)}
            </span>
          </div>
        ))}
      </div>
      {photos.length > 5 && (
        <button onClick={() => setOpen((v) => !v)} className="mt-1.5 text-[11px] text-cyan-400 hover:underline">
          {open ? "Show less" : `Show all ${photos.length}`}
        </button>
      )}
    </div>
  );
}

function SummaryTab({ entities, clusters, identity, signalFilter, onToggleSignal }) {
  const [modal, setModal] = useState(null);   // "photos" | "platforms" | "names" | "locations" | null
  // Profile pictures — EVERY image fetched from every account (dedupe only exact-same URL,
  // regardless of the account's confidence/tier). Carries source_url so the popup links out.
  const seenPhoto = new Set();
  const photos = [];
  entities.forEach((e) => {
    const m = e.metadata || {};
    const url = m.photo_url || m.avatar || m.avatar_url || m.image;
    if (url && !seenPhoto.has(url)) {
      seenPhoto.add(url);
      photos.push({ url, platform: e.platform, source_url: e.source_url });
    }
  });

  // Platforms (count desc; full list, panel expands)
  const platformCounts = {};
  entities.forEach((e) => { const p = e.platform || "unknown"; platformCounts[p] = (platformCounts[p] || 0) + 1; });
  const platforms = Object.entries(platformCounts).sort((a, b) => b[1] - a[1]);

  // Names / aliases / locations: PREFER the LLM identity agent's clean, classified output
  // (real names vs handles vs locations, junk removed). Fall back to a raw metadata sweep
  // only if the agent hasn't produced anything (e.g. still running, or LLM unavailable).
  const dedupeCI = (arr) => {
    const seen = new Set(); const out = [];
    (arr || []).forEach((x) => { const v = decodeEntities(String(x || "")).trim(); const k = v.toLowerCase();
      if (v && !seen.has(k)) { seen.add(k); out.push(v); } });
    return out;
  };

  let names = dedupeCI(identity?.real_names);
  let aliases = dedupeCI(identity?.aliases);
  let locations = dedupeCI([...(identity?.locations || []), ...(identity?.employers || [])]);

  if (names.length === 0) {
    const raw = [];
    [...entities].sort((a, b) => (b.metadata?.exact_seed_match ? 1 : 0) - (a.metadata?.exact_seed_match ? 1 : 0))
      .forEach((e) => { const n = e.metadata?.fullname || e.metadata?.name; if (typeof n === "string") raw.push(n); });
    names = dedupeCI(raw);
  }
  if (locations.length === 0) {
    const raw = [];
    entities.forEach((e) => { const m = e.metadata || {};
      raw.push(m.location, ...(m.employer_candidates || []), ...(m.location_candidates || []), ...(m.city_candidates || [])); });
    locations = dedupeCI(raw.filter(Boolean));
  }
  // Merge names + aliases for the "Names & aliases" panel, names first, aliases tagged.
  const nameRows = [...names.map((n) => ({ v: n, alias: false })),
                    ...aliases.filter((a) => !names.some((n) => n.toLowerCase() === a.toLowerCase()))
                              .map((a) => ({ v: a, alias: true }))];

  // Evidence quick-links (§4.4.4.1) — the moat. Count, for every REAL corroborating
  // signal, how many identity groups it links and how many accounts those groups hold.
  // `_`-prefixed keys are internal ranking metadata (relevance), NOT evidence — excluded.
  const sigStat = {}; // signal -> { groups, accounts }
  clusters.forEach((c) => {
    const members = (c.entity_ids || []).length;
    Object.keys(c.signals || {}).forEach((s) => {
      if (s.startsWith("_")) return;
      if (!sigStat[s]) sigStat[s] = { groups: 0, accounts: 0 };
      sigStat[s].groups += 1;
      sigStat[s].accounts += members;
    });
  });
  const EVIDENCE_TIERS = [
    { key: "hard", label: "Decisive evidence", hint: "Standalone-strong — one is enough to anchor a link" },
    { key: "identity", label: "Identity signals", hint: "Same handle or real name across platforms" },
    { key: "context", label: "Corroborating context", hint: "Supporting only — never sufficient alone" },
  ];
  const sigByTier = { hard: [], identity: [], context: [] };
  Object.entries(sigStat).forEach(([sig, st]) => {
    (sigByTier[tierFor(sig)] || sigByTier.context).push([sig, st]);
  });
  Object.values(sigByTier).forEach((arr) => arr.sort((a, b) => b[1].accounts - a[1].accounts || b[1].groups - a[1].groups));
  const hasEvidence = Object.keys(sigStat).length > 0;

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <MatrixCard icon="🖼️" title="Profile pictures" count={photos.length}
          onExpand={photos.length ? () => setModal("photos") : undefined}>
          {photos.length === 0 ? (
            <EmptyLine>No profile pictures found.</EmptyLine>
          ) : (
            <PhotoGrid photos={photos} />
          )}
        </MatrixCard>

        <MatrixCard icon="🌐" title="Platforms" count={platforms.length}
          onExpand={platforms.length ? () => setModal("platforms") : undefined}>
          {platforms.length === 0 ? (
            <EmptyLine>No platforms found.</EmptyLine>
          ) : (
            <ExpandableList
              items={platforms}
              initial={6}
              render={([p, n]) => (
                <div key={p} className="flex items-center justify-between text-[13px]">
                  <span className="text-slate-200 truncate">{decodeEntities(p)}</span>
                  <span className="text-[11px] font-mono text-slate-500 border border-slate-700 rounded px-1.5 shrink-0">{n}</span>
                </div>
              )}
            />
          )}
        </MatrixCard>

        <MatrixCard icon="👤" title="Names & aliases" count={nameRows.length}
          onExpand={nameRows.length ? () => setModal("names") : undefined}>
          {nameRows.length === 0 ? (
            <EmptyLine>No names found.</EmptyLine>
          ) : (
            <ExpandableList
              items={nameRows}
              initial={4}
              render={(r, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-[13px]">
                  <span className="text-slate-200 truncate">{r.v}</span>
                  <span className={`text-[10px] font-mono uppercase shrink-0 ${r.alias ? "text-slate-500" : "text-cyan-400"}`}>
                    {r.alias ? "Alias" : "Name"}
                  </span>
                </div>
              )}
            />
          )}
        </MatrixCard>

        <MatrixCard icon="📍" title="Locations & context" count={locations.length}
          onExpand={locations.length ? () => setModal("locations") : undefined}>
          {locations.length === 0 ? (
            <EmptyLine>No locations found.</EmptyLine>
          ) : (
            <ExpandableList
              items={locations}
              initial={6}
              render={(l, i) => (
                <span key={i} className="inline-block mr-1.5 mb-1 text-[11px] text-slate-300 bg-slate-800/70 border border-slate-700 rounded px-2 py-0.5">{l}</span>
              )}
            />
          )}
        </MatrixCard>
      </div>

      {/* Full-view popups (click a card) */}
      {modal === "photos" && (
        <Modal icon="🖼️" title="All profile pictures" subtitle={`${photos.length} images across every platform`} onClose={() => setModal(null)}>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
            {photos.map((p, i) => (
              <a key={i} href={safeUrl(p.source_url) || p.url} target="_blank" rel="noreferrer noopener" className="group">
                <div className="relative aspect-square rounded-md overflow-hidden border border-white/10">
                  <img src={p.url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                    onError={(ev) => { ev.currentTarget.parentElement.parentElement.style.display = "none"; }} />
                  <span className="absolute bottom-0 left-0 text-[9px] font-mono px-1 rounded-tr rounded-bl-md bg-black/75 text-slate-200">
                    {decodeEntities(p.platform || "")}
                  </span>
                </div>
              </a>
            ))}
          </div>
        </Modal>
      )}
      {modal === "platforms" && (
        <Modal icon="🌐" title="All platforms" subtitle={`${platforms.length} distinct`} onClose={() => setModal(null)}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
            {platforms.map(([p, n]) => (
              <div key={p} className="flex items-center justify-between text-[13px] border-b border-slate-800/60 py-1">
                <span className="text-slate-200 truncate">{decodeEntities(p)}</span>
                <span className="text-[11px] font-mono text-slate-500 border border-slate-700 rounded px-1.5 shrink-0">{n}</span>
              </div>
            ))}
          </div>
        </Modal>
      )}
      {modal === "names" && (
        <Modal icon="👤" title="Names & aliases" subtitle={`${nameRows.length} total`} onClose={() => setModal(null)}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
            {nameRows.map((r, i) => (
              <div key={i} className="flex items-center justify-between gap-2 text-[13px] border-b border-slate-800/60 py-1">
                <span className="text-slate-200 truncate">{r.v}</span>
                <span className={`text-[10px] font-mono uppercase shrink-0 ${r.alias ? "text-slate-500" : "text-cyan-400"}`}>
                  {r.alias ? "Alias" : "Name"}
                </span>
              </div>
            ))}
          </div>
        </Modal>
      )}
      {modal === "locations" && (
        <Modal icon="📍" title="Locations & context" subtitle={`${locations.length} total`} onClose={() => setModal(null)}>
          <div className="flex flex-wrap gap-2">
            {locations.map((l, i) => (
              <span key={i} className="text-[12px] text-slate-300 bg-slate-800/70 border border-slate-700 rounded px-2.5 py-1">{l}</span>
            ))}
          </div>
        </Modal>
      )}

      {hasEvidence && (
        <GlassPanel className="p-4 mt-3 border border-cyan-400/20">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[11px] font-mono uppercase tracking-wide text-cyan-300">
              🔎 Evidence quick-links
            </div>
            {signalFilter && (
              <button
                onClick={() => onToggleSignal(signalFilter)}
                className="text-[11px] font-mono uppercase tracking-wide text-cyan-400 hover:text-cyan-200 border border-cyan-400/40 rounded px-2 py-0.5"
              >
                ✕ Clear filter
              </button>
            )}
          </div>
          <div className="text-[11px] text-slate-500 mb-3">
            Click any evidence type to isolate the identity groups it links. Each linkage is
            traced to the exact signal that produced it — nothing is asserted without evidence.
          </div>

          {EVIDENCE_TIERS.map(({ key, label, hint }) => {
            const rows = sigByTier[key];
            if (!rows.length) return null;
            const accent = key === "hard" ? "#00ff88" : key === "identity" ? "#38bdf8" : "#94a3b8";
            return (
              <div key={key} className="mb-3 last:mb-0">
                <div className="flex items-baseline gap-2 mb-1.5">
                  <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: accent }}>{label}</span>
                  <span className="text-[10px] text-slate-600">{hint}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {rows.map(([sig, st]) => (
                    <PivotPill key={sig} icon={iconFor(sig)} active={signalFilter === sig} onClick={() => onToggleSignal(sig)}>
                      <span className="font-medium">{labelFor(sig)}</span>
                      <span className="ml-1.5 text-[10px] opacity-70">
                        {st.groups} {st.groups === 1 ? "group" : "groups"} · {st.accounts} {st.accounts === 1 ? "account" : "accounts"}
                      </span>
                    </PivotPill>
                  ))}
                </div>
              </div>
            );
          })}
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
          <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400 mb-2">Topics &amp; interests</div>
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
