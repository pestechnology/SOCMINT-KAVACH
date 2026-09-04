// components/ui/ConfidenceBadge.jsx
// §3.3 — tier chip. HIGH->emerald "Strong match", MEDIUM->amber "Possible match",
// LOW/REJECT->crimson "Not linked". Raw score is de-emphasized (§3.3, §9.1).
// Text colors use theme-aware CSS vars (globals.css) so the label darkens in light mode;
// the translucent bg/border tints read fine on both themes.
const CONFIG = {
  HIGH:   { label: "Strong match",   color: "var(--tone-emerald)", bg: "rgba(111,174,134,0.12)",  border: "rgba(111,174,134,0.35)" },
  MEDIUM: { label: "Possible match", color: "var(--tone-amber)",   bg: "rgba(203,169,106,0.12)",  border: "rgba(203,169,106,0.35)" },
  LOW:    { label: "Not linked",     color: "var(--tone-rose)",    bg: "rgba(207,128,128,0.12)", border: "rgba(207,128,128,0.35)" },
  REJECT: { label: "Not linked",     color: "var(--tone-rose)",    bg: "rgba(207,128,128,0.12)", border: "rgba(207,128,128,0.35)" },
  // UNVERIFIED: the account exists under a matching handle, but NOTHING was ever
  // retrieved from its page (no name, bio, photo or title). It contributed no evidence
  // of its own, so it must not wear the cluster's "Strong match" badge — claiming a
  // match we never corroborated is exactly the over-claiming this product refuses.
  // Deliberately neutral (slate), not red: it is not a rejected link, it is unchecked.
  UNVERIFIED: { label: "Unverified", color: "rgb(148,163,184)", bg: "rgba(148,163,184,0.10)", border: "rgba(148,163,184,0.30)" },
};

export default function ConfidenceBadge({ tier = "LOW", score = null, className = "" }) {
  const cfg = CONFIG[tier] || CONFIG.LOW;
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className="inline-block rounded-md px-2 py-0.5 text-[11px] font-medium"
        style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}
      >
        {cfg.label}
      </span>
      {score != null && (
        <span className="text-xs text-slate-500 font-mono">· {Math.round(score)}/100</span>
      )}
    </span>
  );
}
