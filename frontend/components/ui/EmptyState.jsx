// components/ui/EmptyState.jsx
// §3.8 — centered empty placeholder. Never render a bare dash/null (§5.4, §9.5).
export default function EmptyState({ icon = "🔍", title, description, className = "", children }) {
  return (
    <div className={`flex flex-col items-center justify-center text-center py-10 px-4 ${className}`}>
      <div className="text-[48px] leading-none mb-3 opacity-80" aria-hidden>{icon}</div>
      {title && <div className="text-slate-200 font-semibold text-sm">{title}</div>}
      {description && <div className="text-slate-500 text-xs mt-1 max-w-xs">{description}</div>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}
