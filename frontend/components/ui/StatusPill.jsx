// components/ui/StatusPill.jsx
// §3.2 — investigation status indicator. Obeys the §1.7 semantic color map:
// running/pending -> cyan (+pulse), complete -> emerald, error -> crimson.
// Theme-aware text tones (globals.css) so the pill label + dot darken in light mode.
const CONFIG = {
  running:  { color: "var(--tone-cyan)",    label: "In progress", pulse: true },
  pending:  { color: "var(--tone-cyan)",    label: "In progress", pulse: true },
  complete: { color: "var(--tone-emerald)", label: "Complete",    pulse: false },
  error:    { color: "var(--tone-rose)",    label: "Error",       pulse: false },
};

export default function StatusPill({ status = "pending", className = "" }) {
  const cfg = CONFIG[status] || CONFIG.pending;
  return (
    <span
      className={`inline-flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider ${className}`}
      style={{ color: cfg.color }}
    >
      {cfg.pulse ? (
        <span className="pulse-dot" />
      ) : (
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: "currentColor", boxShadow: "0 0 8px currentColor" }}
        />
      )}
      {cfg.label}
    </span>
  );
}
