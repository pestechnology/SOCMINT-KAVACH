"use client";

import { useState, FormEvent } from "react";
import { investigate } from "@/lib/api";
import { LinkedIdentity, RawProfile } from "@/lib/types";

const identifierOptions = [
  { label: "Username", value: "username" },
  { label: "Email", value: "email" },
  { label: "Phone number", value: "phone" },
  { label: "UPI ID", value: "upi" },
  { label: "Name", value: "name" },
];

const placeholders: Record<string, string> = {
  username: "e.g. arjun_trades99",
  email: "e.g. suspect@gmail.com",
  phone: "e.g. +919876543210",
  upi: "e.g. arjun@oksbi",
  name: "e.g. Arjun Sharma",
};

function getTierLabel(tier: string): string {
  switch (tier?.toUpperCase()) {
    case "HIGH":
      return "Strong match";
    case "MEDIUM":
      return "Possible match";
    case "LOW":
      return "Weak — not linked";
    case "REJECT":
      return "No match";
    default:
      return "Weak — not linked";
  }
}

function getBestGuessName(cluster: LinkedIdentity): string {
  for (const p of cluster.profiles) {
    if (p.metadata?.fullname && typeof p.metadata.fullname === "string") {
      return p.metadata.fullname;
    }
  }
  return cluster.profiles[0]?.value || "Unknown Suspect";
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function formatPlatformName(platform: string): string {
  if (!platform) return "Platform";
  return platform.charAt(0).toUpperCase() + platform.slice(1);
}

function formatHandle(profile: RawProfile): string {
  if (["email", "phone", "upi"].includes(profile.type)) {
    return profile.value;
  }
  return profile.value.startsWith("@") ? profile.value : `@${profile.value}`;
}

export default function Home() {
  const [idType, setIdType] = useState<string>("username");
  const [idValue, setIdValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<LinkedIdentity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!idValue.trim() || loading) return;

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const resp = await investigate(idType, idValue.trim());
      setResults(resp.clusters || []);
    } catch (err: any) {
      setError(err.message || "Could not reach VERTEX backend. Is it running on port 8000?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* SECTION 1 — HEADER BAR */}
        <header className="flex items-center justify-between border-b border-zinc-800 pb-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">VERTEX</h1>
            <p className="text-sm text-zinc-400">SOCMINT Investigator</p>
          </div>
          <div className="text-right">
            <span className="text-sm text-zinc-400 font-medium">Inspector R. Kumar</span>
          </div>
        </header>

        {/* SECTION 2 — SEARCH INPUT */}
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-lg">
          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block text-sm font-medium text-zinc-200">
              What do you know about the suspect?
            </label>

            <div className="flex flex-col sm:flex-row gap-3">
              <select
                value={idType}
                onChange={(e) => setIdType(e.target.value)}
                disabled={loading}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-500 sm:w-48"
              >
                {identifierOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              <input
                type="text"
                value={idValue}
                onChange={(e) => setIdValue(e.target.value)}
                placeholder={placeholders[idType] || "Type identifier..."}
                disabled={loading}
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2.5 text-zinc-100 text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-500"
              />

              <button
                type="submit"
                disabled={loading || !idValue.trim()}
                className="bg-zinc-100 text-zinc-950 font-semibold px-6 py-2.5 rounded-lg text-sm hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
              >
                Start investigation
              </button>
            </div>

            <p className="text-xs text-zinc-500">
              Only publicly available information is collected
            </p>
          </form>
        </section>

        {/* SECTION 3 — LIVE PROGRESS */}
        {loading && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center space-y-4">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-zinc-400 border-r-transparent align-[-0.125em]" />
            <p className="text-sm font-medium text-zinc-300">
              Searching across platforms...
            </p>
          </section>
        )}

        {/* SECTION 4 — ERROR STATE */}
        {error && !loading && (
          <section className="bg-rose-950/40 border border-rose-800/80 rounded-xl p-6 text-center">
            <p className="text-sm font-medium text-rose-300">{error}</p>
          </section>
        )}

        {/* SECTION 4 — RESULTS */}
        {results && !loading && (
          <section className="space-y-6">
            {results.length === 0 ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center">
                <p className="text-sm text-zinc-400">
                  No linked accounts found for this identifier.
                </p>
              </div>
            ) : (
              results.map((cluster) => {
                const isSingleton = cluster.profiles.length === 1;
                const bestName = getBestGuessName(cluster);
                const isHigh = cluster.tier?.toUpperCase() === "HIGH";
                const isLow = cluster.tier?.toUpperCase() === "LOW" || cluster.is_red_herring;

                // SINGLETON CARD
                if (isSingleton) {
                  const profile = cluster.profiles[0];
                  return (
                    <div
                      key={cluster.cluster_id}
                      className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex items-center justify-between"
                    >
                      <div>
                        <p className="text-sm font-semibold text-zinc-200">
                          {formatPlatformName(profile.platform)}
                        </p>
                        <p className="text-sm text-zinc-400 font-mono">
                          {formatHandle(profile)}
                        </p>
                      </div>
                      <span className="bg-zinc-800 border border-zinc-700 text-zinc-400 text-xs px-3 py-1 rounded-lg font-medium">
                        No connections found
                      </span>
                    </div>
                  );
                }

                // HIGH OR LOW CONFIDENCE CARD
                const badgeBg = isHigh
                  ? "bg-emerald-950 border-emerald-500/40 text-emerald-300"
                  : "bg-amber-950 border-amber-500/40 text-amber-300";

                const cardStyle = isLow
                  ? "bg-zinc-900/60 border border-zinc-800/80 opacity-80"
                  : "bg-zinc-900 border border-zinc-800";

                const platformsCount = new Set(
                  cluster.profiles.map((p) => p.platform)
                ).size;

                return (
                  <div key={cluster.cluster_id} className="space-y-3">
                    <div className={`${cardStyle} rounded-xl p-6 space-y-6 shadow-md`}>
                      {/* Top Row */}
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center font-bold text-zinc-300 text-lg">
                            {getInitials(bestName)}
                          </div>
                          <div>
                            <h2 className="text-lg font-bold text-white">
                              {bestName}
                            </h2>
                            <p className="text-sm text-zinc-400">
                              {cluster.profiles.length} linked accounts across {platformsCount} platforms
                            </p>
                          </div>
                        </div>

                        <span
                          className={`border text-xs px-3 py-1.5 rounded-lg font-semibold whitespace-nowrap ${badgeBg}`}
                        >
                          {getTierLabel(cluster.tier)} · {Math.round(cluster.confidence_score)}%
                        </span>
                      </div>

                      {/* Grid of platform tiles */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-2">
                        {cluster.profiles.map((profile, i) => (
                          <div
                            key={`${profile.platform}-${i}`}
                            className="bg-zinc-800/80 border border-zinc-700/60 rounded-lg p-3 flex items-center justify-between overflow-hidden"
                          >
                            <span className="text-xs font-semibold text-zinc-300">
                              {formatPlatformName(profile.platform)}
                            </span>
                            <span className="text-xs text-zinc-400 truncate ml-2 font-mono">
                              {formatHandle(profile)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Why we think these are the same person */}
                      {cluster.why_explanation && cluster.why_explanation.length > 0 && (
                        <div className="border-t border-zinc-800 pt-4 space-y-2">
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                            Why we think these are the same person
                          </h3>
                          <ul className="list-disc list-inside space-y-1">
                            {cluster.why_explanation.map((explanation, i) => (
                              <li key={i} className="text-sm text-zinc-300">
                                {explanation}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Red herring reason text below card */}
                    {cluster.is_red_herring && cluster.red_herring_reason && (
                      <p className="text-xs italic text-rose-400 px-2">
                        {cluster.red_herring_reason}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </section>
        )}
      </div>
    </div>
  );
}
