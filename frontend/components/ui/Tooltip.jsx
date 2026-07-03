// components/ui/Tooltip.jsx
// §3.9 — hover tooltip. CSS group-hover, no JS/portal. Wrap any trigger.
export default function Tooltip({ content, children, className = "" }) {
  return (
    <span className={`relative inline-flex items-center group ${className}`}>
      {children ?? (
        <span
          className="inline-flex items-center justify-center w-4 h-4 rounded-full
            text-[10px] font-mono text-cyan-400 border border-cyan-400/50 cursor-help"
          aria-hidden
        >
          ?
        </span>
      )}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 bottom-full z-50 mb-2 -translate-x-1/2
          w-max max-w-[220px] rounded-md border border-[var(--border-glass)]
          bg-slate-900/95 px-2.5 py-1.5 text-[11px] leading-snug text-slate-200
          opacity-0 transition-opacity duration-150 group-hover:opacity-100"
      >
        {content}
      </span>
    </span>
  );
}
