// components/ui/Input.jsx
// §3.7 — text input. Cyan focus ring + subtle glow.
export default function Input({ className = "", ...rest }) {
  return (
    <input
      className={`
        w-full rounded-lg bg-slate-900/80 border border-slate-700
        px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500
        outline-none transition-colors duration-200
        focus:border-cyan-400 focus:shadow-[0_0_0_3px_rgba(107,169,189,0.15)]
        ${className}
      `}
      {...rest}
    />
  );
}
