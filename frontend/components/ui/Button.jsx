// components/ui/Button.jsx
// §3.6 — primary (cyan->purple), secondary (outline), success (emerald->cyan).
const VARIANTS = {
  primary:
    "text-black font-semibold bg-gradient-to-r from-cyan-400 to-purple-400 " +
    "shadow-[0_4px_20px_-4px_rgba(107,169,189,0.5)] hover:-translate-y-0.5",
  secondary:
    "bg-slate-800/80 text-slate-100 border border-white/15 " +
    "hover:border-cyan-400 hover:-translate-y-px",
  success:
    "text-black font-semibold bg-gradient-to-r from-emerald-400 to-cyan-400 " +
    "shadow-[0_4px_20px_-4px_rgba(111,174,134,0.5)] hover:-translate-y-0.5",
};

export default function Button({
  variant = "primary",
  className = "",
  type = "button",
  disabled = false,
  children,
  ...rest
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      className={`
        inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5
        text-sm transition-all duration-200
        disabled:opacity-50 disabled:pointer-events-none disabled:translate-y-0
        ${VARIANTS[variant] || VARIANTS.primary}
        ${className}
      `}
      {...rest}
    >
      {children}
    </button>
  );
}
