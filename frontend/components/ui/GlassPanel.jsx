// components/ui/GlassPanel.jsx
// §3.1 — base glass container. Every panel in the redesign composes this.
export default function GlassPanel({ className = "", children, ...rest }) {
  return (
    <div
      className={`
        rounded-xl backdrop-blur-md
        bg-[var(--bg-glass)] border border-[var(--border-glass)]
        shadow-[0_8px_32px_0_rgba(0,0,0,0.37)]
        transition-colors duration-300
        hover:border-[rgba(107,169,189,0.4)]
        ${className}
      `}
      {...rest}
    >
      {children}
    </div>
  );
}
