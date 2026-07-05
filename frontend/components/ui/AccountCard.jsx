// components/ui/AccountCard.jsx
// §3.4 — a single discovered account in the identity list.
// Rows: platform + Live chip / primary name / secondary (title|bio) / tier badge.
// Tier is the MATCH confidence (>=70 HIGH, 40-69 MEDIUM, <40 LOW) — thresholds mirror
// backend/scoring/confidence.py — unless the caller already stamped entity._tier.
import ConfidenceBadge from "./ConfidenceBadge";
import PlatformLogo from "./PlatformLogo";

function tierFromConfidence(confidence) {
  const c = Number(confidence) || 0;
  if (c >= 70) return "HIGH";
  if (c >= 40) return "MEDIUM";
  return "LOW";
}

function truncate(str, n = 80) {
  if (!str) return "";
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

// Only allow http(s) — blocks a javascript:/data: URI from ever becoming a clickable
// href (an XSS vector if a scraped field were ever malicious). Same rule page.js's
// own safeUrl() uses; duplicated here since this is a separate component file.
function safeUrl(url) {
  if (!url || typeof url !== "string") return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}

export default function AccountCard({
  entity = {}, selected = false, onClick, exactMatch = false,
  reiterateChecked = false, onToggleReiterate = null,
}) {
  const meta = entity.metadata || {};
  const platform = entity.platform || entity.type || "account";
  const tier = entity._tier || tierFromConfidence(entity.confidence);
  // Badge the literal search-query match wherever it appears, from prop or server flag.
  const isExact = exactMatch || entity._exactMatch || !!meta.exact_seed_match;

  const primary = meta.fullname || entity.value || "Unknown account";
  const secondary = truncate(meta.title || meta.bio || "", 80);
  const isLive = entity.data_mode === "live";
  const link = safeUrl(entity.source_url);
  // A discovered contact email is a high-value finding (often the whole point of the
  // search) — surface it right on the card. meta.email is set by GitHub/Gravatar and by
  // the stealth-browser fallback that reads a Facebook profile's public Intro box.
  const email = typeof meta.email === "string" && meta.email.includes("@") ? meta.email : null;

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
      {/* Row 1: re-iterate checkbox + platform + Live chip */}
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 min-w-0">
          {onToggleReiterate && (
            <input
              type="checkbox"
              checked={reiterateChecked}
              onChange={() => onToggleReiterate(entity.entity_id)}
              onClick={(e) => e.stopPropagation()}
              title="Select for re-iterate"
              className="accent-cyan-400 shrink-0"
            />
          )}
          <PlatformLogo platform={platform} width={12} height={12} />
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
          {(entity.data_mode === "agentic_web" || meta.agentic_source) && (
            <span className="text-[10px] font-mono uppercase tracking-wide text-[#00f2fe] border border-[#00f2fe]/40 bg-[#00f2fe]/10 rounded px-1.5 py-0.5" title="Discovered via autonomous AI browser exploration">
              🤖 Agentic
            </span>
          )}
        </span>
      </div>

      {/* Row 2: primary display + clickable link to the actual discovered page */}
      <div className="mt-1.5 flex items-center gap-2 min-w-0">
        <span className="text-sm font-medium text-slate-100 truncate min-w-0">
          {primary}
        </span>
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(e) => e.stopPropagation()}
            title={link}
            className="shrink-0 text-[11px] text-cyan-400 hover:text-cyan-300 hover:underline"
          >
            Open ↗
          </a>
        )}
      </div>

      {/* Row 3: secondary (title | bio) */}
      {secondary && (
        <div className="mt-0.5 text-xs text-slate-500 line-clamp-2">
          {secondary}
        </div>
      )}

      {/* Row 3b: discovered contact email (high-value PII — made prominent + copyable) */}
      {email && (
        <div className="mt-1.5 flex items-center gap-1.5 min-w-0">
          <span className="text-[11px] shrink-0" aria-hidden>✉</span>
          <a
            href={`mailto:${email}`}
            onClick={(e) => e.stopPropagation()}
            title={meta.browser_enriched ? `${email} (recovered via browser)` : email}
            className="text-[12px] font-mono text-amber-300 hover:text-amber-200 hover:underline truncate min-w-0"
          >
            {email}
          </a>
          {meta.browser_enriched && (
            <span className="text-[9px] font-mono uppercase tracking-wide text-amber-400/70 border border-amber-400/30 rounded px-1 py-0.5 shrink-0" title="Public contact email read from the profile page in a real browser">
              🌐 browser
            </span>
          )}
        </div>
      )}

      {/* Row 4: tier badge */}
      <div className="mt-2">
        <ConfidenceBadge tier={tier} />
      </div>
    </button>
  );
}
