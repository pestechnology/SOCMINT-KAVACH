"use client";
// A light/dark theme switch. Sets `data-theme` on <html> (globals.css does the rest via
// CSS variables) and persists to localStorage. A tiny inline script in layout.js applies
// the saved theme before paint, so this component only handles the interactive toggle.
import { useEffect, useState } from "react";

export default function ThemeToggle({ className = "" }) {
  // Start "dark" to match SSR (no localStorage read during render → no hydration mismatch);
  // the effect syncs to the persisted choice on mount.
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    let t = "dark";
    try {
      t = localStorage.getItem("vertex-theme")
        || document.documentElement.getAttribute("data-theme")
        || "dark";
    } catch { /* localStorage blocked */ }
    setTheme(t === "light" ? "light" : "dark");
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("vertex-theme", next);
    } catch { /* ignore */ }
  }

  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={!isDark}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Light mode" : "Dark mode"}
      className={`relative inline-flex h-7 w-[52px] shrink-0 items-center rounded-full border border-slate-700 bg-slate-800/70 transition-colors hover:border-cyan-400/60 ${className}`}
    >
      <span
        className="absolute flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-[11px] leading-none shadow-md transition-transform duration-200 ease-out"
        style={{ transform: isDark ? "translateX(3px)" : "translateX(27px)" }}
        aria-hidden
      >
        {isDark ? "🌙" : "☀️"}
      </span>
    </button>
  );
}
