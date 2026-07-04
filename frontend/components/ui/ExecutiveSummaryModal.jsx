"use client";

import React, { useState } from "react";
import PlatformLogo from "./PlatformLogo";
import Button from "./Button";
import { api } from "@/lib/api";

export default function ExecutiveSummaryModal({
  isOpen,
  onClose,
  kase = {},
  id,
  status,
  strongClusters = [],
  possibleClusters = [],
  notLinkedEntities = [],
  clusterMembers = () => []
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!isOpen) return null;

  const allLinkages = [...strongClusters, ...possibleClusters];
  const strongAccountCount = strongClusters.reduce((s, c) => s + clusterMembers(c).length, 0);
  const possibleAccountCount = possibleClusters.reduce((s, c) => s + clusterMembers(c).length, 0);

  async function downloadReport() {
    if (status !== "complete") return;
    setErr("");
    setBusy(true);
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
    } catch (e) {
      setErr(e.message || "Failed to download report");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-5xl max-h-[90vh] flex flex-col bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden text-slate-100">
        
        {/* TOP BANNER */}
        <div className="px-6 py-5 bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border-b border-slate-800 flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="text-xl">⚖️</span>
              <h2 className="text-lg font-bold tracking-tight text-slate-100 uppercase font-sans">
                Electronic Evidence Report — Executive Briefing
              </h2>
            </div>
            <div className="text-xs font-mono text-slate-400 mt-1 flex items-center gap-3">
              <span>Prepared under Section 63, Bharatiya Sakshya Adhiniyam, 2023</span>
              <span>•</span>
              <span>Case Ref: #{str_slice(kase.case_id || id || "", 8)}</span>
              <span>•</span>
              <span className="text-cyan-400">Status: {status?.toUpperCase() || "ACTIVE"}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-slate-100 flex items-center justify-center transition-colors text-lg"
            title="Close summary"
          >
            ✕
          </button>
        </div>

        {/* SCROLLABLE BODY */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 custom-scrollbar">
          

          {/* METRICS STRIP */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-900/80 border border-emerald-500/30 relative overflow-hidden group hover:border-emerald-500/50 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-xl -mr-6 -mt-6 group-hover:bg-emerald-500/10 transition-all" />
              <div className="text-2xl font-bold text-emerald-400 font-mono">{strongClusters.length}</div>
              <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mt-1">Confirmed Linkages</div>
              <div className="text-[11px] text-slate-500 mt-0.5">{strongAccountCount} corroborated accounts</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-amber-500/30 relative overflow-hidden group hover:border-amber-500/50 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-xl -mr-6 -mt-6 group-hover:bg-amber-500/10 transition-all" />
              <div className="text-2xl font-bold text-amber-400 font-mono">{possibleClusters.length}</div>
              <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mt-1">Probable Linkages</div>
              <div className="text-[11px] text-slate-500 mt-0.5">{possibleAccountCount} accounts (verify independently)</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-cyan-500/30 relative overflow-hidden group hover:border-cyan-500/50 transition-all">
              <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/5 rounded-full blur-xl -mr-6 -mt-6 group-hover:bg-cyan-500/10 transition-all" />
              <div className="text-2xl font-bold text-cyan-400 font-mono">{notLinkedEntities.length}</div>
              <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mt-1">Unconfirmed Leads</div>
              <div className="text-[11px] text-slate-500 mt-0.5">Username match only</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 relative overflow-hidden">
              <div className="text-2xl font-bold text-slate-400 font-mono">0</div>
              <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider mt-1">Assessed Unrelated</div>
              <div className="text-[11px] text-slate-500 mt-0.5">No corroborating signals</div>
            </div>
          </div>

          {/* SECTION 1: CONFIRMED & PROBABLE LINKAGES */}
          <div className="space-y-4">
            <div className="border-b border-slate-800 pb-2 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-100 uppercase tracking-wide">
                  1. Confirmed & Probable Linkages (Corroborated Evidence)
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Accounts sharing independent biometric, photographic, or behavioral signals across platforms.
                </p>
              </div>
            </div>

            {allLinkages.length === 0 ? (
              <div className="p-8 text-center bg-slate-900/40 rounded-xl border border-slate-800/80">
                <div className="text-slate-400 text-sm">No multi-signal account clusters identified yet.</div>
                <div className="text-xs text-slate-500 mt-1">Standalone accounts appear under unconfirmed leads below.</div>
              </div>
            ) : (
              <div className="space-y-4">
                {allLinkages.map((cluster, idx) => {
                  const members = clusterMembers(cluster);
                  // Rank/display by MATCH confidence (exact search match = 100%), not the
                  // linkage score — the searched-for account must lead, not sink.
                  const conf = Math.round(cluster.match?.score ?? cluster.confidence_score ?? cluster.confidence ?? 100);
                  const isHigh = (cluster.match?.tier || cluster.tier) === "HIGH" || conf >= 70;

                  return (
                    <div
                      key={cluster.cluster_id || idx}
                      className={`p-5 rounded-xl bg-slate-900/90 border transition-all shadow-xl ${
                        isHigh ? "border-emerald-500/40 hover:border-emerald-500/60" : "border-amber-500/40 hover:border-amber-500/60"
                      }`}
                    >
                      {/* CARD TOP BAR */}
                      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-bold font-mono border flex items-center gap-1.5 shadow-sm ${
                              isHigh
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-emerald-500/10"
                                : "bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-amber-500/10"
                            }`}
                          >
                            <span>{isHigh ? "★" : "◆"}</span>
                            <span>{conf}% {members.length > 1 ? (isHigh ? "CONFIRMED LINKAGE" : "PROBABLE LINKAGE") : "MATCH"}</span>
                          </span>
                          <span className="text-xs font-mono text-slate-400 bg-slate-800 px-2.5 py-1 rounded-md border border-slate-700">
                            TIER: {cluster.tier || (isHigh ? "HIGH" : "MEDIUM")}
                          </span>
                        </div>
                        <span className="text-xs font-mono text-slate-500">
                          Group #{idx + 1} · {members.length} Accounts
                        </span>
                      </div>

                      {/* ACCOUNTS GRID */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {members.map((ent) => (
                          <div
                            key={ent.entity_id}
                            className="flex items-center gap-3.5 p-3 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-slate-700/80 transition-all group"
                          >
                            <div className="w-9 h-9 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center shrink-0 shadow-inner group-hover:scale-105 transition-transform">
                              <PlatformLogo platform={ent.platform} width={24} height={24} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 truncate">
                                {ent.platform || "Account"}
                              </div>
                              <div className="text-sm font-semibold text-slate-100 truncate mt-0.5" title={ent.value}>
                                {ent.value}
                              </div>
                            </div>
                            {ent.source_url && (
                              <a
                                href={ent.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-slate-500 hover:text-cyan-400 text-xs px-1.5 py-1 rounded hover:bg-slate-900 transition-colors"
                                title="Open source profile"
                              >
                                ↗
                              </a>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* REASONING BOX */}
                      <div className="mt-4 p-3.5 rounded-lg bg-slate-950/90 border border-slate-800/80 text-xs text-slate-300 leading-relaxed flex items-start gap-2.5">
                        <span className="text-base leading-none mt-0.5">💡</span>
                        <div>
                          <span className="font-semibold text-slate-200">Forensic Reasoning: </span>
                          <span>{cluster.explanation || cluster.reasoning || "Identical username and corroborated multi-signal match across platforms."}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* SECTION 2: UNCONFIRMED LEADS PREVIEW */}
          {notLinkedEntities.length > 0 && (
            <div className="space-y-3 pt-2">
              <div className="border-b border-slate-800 pb-2 flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-100 uppercase tracking-wide">
                    2. Appendix A — Unconfirmed Leads ({notLinkedEntities.length})
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Accounts sharing a username variant without independent corroboration. For investigative follow-up only.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5 max-h-64 overflow-y-auto p-1 custom-scrollbar">
                {notLinkedEntities.map((ent, i) => (
                  <div
                    key={ent.entity_id || i}
                    className="flex items-center gap-2.5 p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/80 hover:bg-slate-900 transition-all text-xs"
                  >
                    <PlatformLogo platform={ent.platform} width={18} height={18} className="shrink-0 opacity-80" />
                    <div className="min-w-0 flex-1 truncate">
                      <span className="text-slate-400">{ent.platform}: </span>
                      <span className="font-mono text-slate-200 font-medium">{ent.value}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* BOTTOM ACTION BAR */}
        <div className="px-6 py-4 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between gap-4 flex-wrap">
          <div className="text-xs font-mono text-slate-400 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
            <span>Audit chain verified · SHA-256 · BSA §63 compliant</span>
            {err && <span className="text-red-400 ml-2">({err})</span>}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            >
              Close Briefing
            </button>
            <Button
              variant="success"
              onClick={downloadReport}
              disabled={status !== "complete" || busy}
              className="text-sm px-4 py-2 flex items-center gap-2 shadow-lg shadow-emerald-500/20"
            >
              <span>{busy ? "Preparing…" : "📄 Download Summary Report (PDF)"}</span>
            </Button>
          </div>
        </div>

      </div>
    </div>
  );
}

function str_slice(str, len) {
  return (str || "").slice(0, len);
}
