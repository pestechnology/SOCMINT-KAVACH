// components/ui/ConfidenceBadge.jsx
// §3.3 — tier chip. HIGH->emerald "Strong match", MEDIUM->amber "Possible match",
// LOW/REJECT->crimson "Not linked". Raw score is de-emphasized (§3.3, §9.1).
const CONFIG = {
  HIGH:   { label: "Strong match",   color: "#00ff88", bg: "rgba(0,255,136,0.12)",  border: "rgba(0,255,136,0.35)" },
  MEDIUM: { label: "Possible match", color: "#ffb703", bg: "rgba(255,183,3,0.12)",  border: "rgba(255,183,3,0.35)" },
  LOW:    { label: "Not linked",     color: "#ff3366", bg: "rgba(255,51,102,0.12)", border: "rgba(255,51,102,0.35)" },
  REJECT: { label: "Not linked",     color: "#ff3366", bg: "rgba(255,51,102,0.12)", border: "rgba(255,51,102,0.35)" },
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
