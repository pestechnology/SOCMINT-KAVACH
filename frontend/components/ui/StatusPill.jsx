// components/ui/StatusPill.jsx
// §3.2 — investigation status indicator. Obeys the §1.7 semantic color map:
// running/pending -> cyan (+pulse), complete -> emerald, error -> crimson.
const CONFIG = {
  running:  { color: "#00f2fe", label: "In progress", pulse: true },
  pending:  { color: "#00f2fe", label: "In progress", pulse: true },
  complete: { color: "#00ff88", label: "Complete",    pulse: false },
  error:    { color: "#ff3366", label: "Error",       pulse: false },
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
