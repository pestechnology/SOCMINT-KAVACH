// components/ui/Label.jsx
// §3.7 — field label. Mono uppercase xs, distinguishes inputs.
export default function Label({ className = "", children, ...rest }) {
  return (
    <label
      className={`block text-[11px] font-mono uppercase tracking-wide text-slate-300 mb-1.5 ${className}`}
      {...rest}
    >
      {children}
    </label>
  );
}
