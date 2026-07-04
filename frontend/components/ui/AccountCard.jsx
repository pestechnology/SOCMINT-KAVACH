// components/ui/AccountCard.jsx
// §3.4 — a single discovered account in the identity list.
// Rows: platform + Live chip / primary name / secondary (title|bio) / tier badge.
// Tier is derived from confidence (>=80 HIGH, 50-79 MEDIUM, <50 LOW) per §3.4,
// unless the caller already stamped entity._tier.
import ConfidenceBadge from "./ConfidenceBadge";

// Minimal platform → glyph map (functional glyphs only, §2.5). Falls back to •.
const PLATFORM_ICONS = {
  github: "🐙", linkedin: "💼", instagram: "📸", twitter: "🐦", x: "🐦",
  facebook: "📘", youtube: "▶️", reddit: "👽", telegram: "✈️",
  hibp: "🛡️", breach: "🛡️", upi: "🏦", derived: "🧩", web: "🌐",
  email: "📧", phone: "📞", username: "🆔",
};

function iconForPlatform(platform = "") {
  return PLATFORM_ICONS[String(platform).toLowerCase()] ?? "•";
}

function tierFromConfidence(confidence) {
  const c = Number(confidence) || 0;
  if (c >= 80) return "HIGH";
  if (c >= 50) return "MEDIUM";
  return "LOW";
}

function truncate(str, n = 80) {
  if (!str) return "";
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

export default function AccountCard({ entity = {}, selected = false, onClick, exactMatch = false }) {
  const meta = entity.metadata || {};
  const platform = entity.platform || entity.type || "account";
  const tier = entity._tier || tierFromConfidence(entity.confidence);
  // Badge the literal search-query match wherever it appears, from prop or server flag.
  const isExact = exactMatch || entity._exactMatch || !!meta.exact_seed_match;

  const primary = meta.fullname || entity.value || "Unknown account";
  const secondary = truncate(meta.title || meta.bio || "", 80);
  const isLive = entity.data_mode === "live";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        w-full text-left rounded-lg p-3 border transition-all duration-200
        ${selected
          ? "border-cyan-400 bg-slate-900/70 shadow-[0_0_0_1px_rgba(0,242,254,0.25),0_4px_16px_-6px_rgba(0,242,254,0.4)] translate-x-1"
          : "border-white/[0.08] bg-slate-900/50 hover:border-cyan-400 hover:translate-x-1 hover:shadow-[0_4px_16px_-8px_rgba(0,242,254,0.35)]"}
      `}
    >
      {/* Row 1: platform + Live chip */}
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 min-w-0">
          <span className="text-[12px] leading-none shrink-0" aria-hidden>
            {iconForPlatform(platform)}
          </span>
          <span className="text-[11px] font-mono uppercase tracking-wide text-slate-400 truncate">
            {platform}
          </span>
        </span>
        <span className="inline-flex items-center gap-1.5 shrink-0">
          {isExact && (
            <span className="text-[10px] font-mono uppercase tracking-wide text-cyan-300 border border-cyan-400/40 bg-cyan-400/10 rounded px-1.5 py-0.5">
              ★ Exact
            </span>
          )}
          {isLive && (
            <span className="text-[10px] font-mono uppercase tracking-wide text-emerald-400 border border-emerald-400/40 rounded px-1.5 py-0.5">
              Live
            </span>
          )}
        </span>
      </div>

      {/* Row 2: primary display */}
      <div className="mt-1.5 text-sm font-medium text-slate-100 truncate">
        {primary}
      </div>

      {/* Row 3: secondary (title | bio) */}
      {secondary && (
        <div className="mt-0.5 text-xs text-slate-500 line-clamp-2">
          {secondary}
        </div>
      )}

      {/* Row 4: tier badge */}
      <div className="mt-2">
        <ConfidenceBadge tier={tier} />
      </div>
    </button>
  );
}
