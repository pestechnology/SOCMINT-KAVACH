// components/ui/PivotPill.jsx
// §3.5 — clickable evidence chip. Cyan gradient outline; fills solid on hover.
export default function PivotPill({ icon = null, children, onClick, active = false, className = "" }) {
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      onClick={onClick}
      className={`
        group inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1
        text-[11px] font-mono
        border transition-all duration-200
        ${active
          ? "text-black border-transparent bg-gradient-to-r from-cyan-400 to-purple-400"
          : "text-cyan-400 border-[rgba(0,242,254,0.35)] bg-[rgba(0,242,254,0.08)] hover:text-black hover:border-transparent hover:bg-gradient-to-r hover:from-cyan-400 hover:to-purple-400"}
        ${onClick ? "cursor-pointer" : ""}
        ${className}
      `}
    >
      {icon && <span aria-hidden>{icon}</span>}
      <span>{children}</span>
    </Tag>
  );
}
