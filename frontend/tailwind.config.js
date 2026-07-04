/* tailwind.config.js
   CHANGED: replaced the old ink/panel/accent palette with the "Case Room" tokens
   (warm amber on deep slate) and mapped Space Grotesk / JetBrains Mono to font-display
   and font-mono via the CSS variables set in layout.js.
   DECISION: default sans = display font so untagged text reads as Space Grotesk. */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx}",
    "./components/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Theme-aware slate scale: every `text-slate-*` / `bg-slate-*` / `border-slate-*`
        // in the app resolves through these CSS variables, so a single set of variables
        // (globals.css) drives BOTH light and dark. Dark values are Tailwind's exact stock
        // slate RGB channels, so dark mode is unchanged; light mode inverts them. The
        // `<alpha-value>` form preserves Tailwind opacity modifiers (e.g. bg-slate-800/70).
        slate: {
          50: "rgb(var(--slate-50) / <alpha-value>)",
          100: "rgb(var(--slate-100) / <alpha-value>)",
          200: "rgb(var(--slate-200) / <alpha-value>)",
          300: "rgb(var(--slate-300) / <alpha-value>)",
          400: "rgb(var(--slate-400) / <alpha-value>)",
          500: "rgb(var(--slate-500) / <alpha-value>)",
          600: "rgb(var(--slate-600) / <alpha-value>)",
          700: "rgb(var(--slate-700) / <alpha-value>)",
          800: "rgb(var(--slate-800) / <alpha-value>)",
          900: "rgb(var(--slate-900) / <alpha-value>)",
          950: "rgb(var(--slate-950) / <alpha-value>)",
        },
        // --- Redesign (§2.4) tokens: new cyan/emerald glass system ---
        ink: "#070a12",     // new primary bg (--bg-primary)
        panel: "#0f172a",   // secondary panel bg (--bg-secondary)
        // amber/crimson/emerald keep their DEFAULT (still used by un-rebuilt pages)
        // and gain a -400 shade matching the redesign semantic palette.
        amber: { DEFAULT: "#D4900A", 400: "#ffb703" },   // MEDIUM / possible
        crimson: { DEFAULT: "#C0392B", 400: "#ff3366" }, // REJECT / not linked / error
        emerald: { DEFAULT: "#27AE60", 400: "#00ff88" }, // HIGH / strong
        cyan: { 400: "#00f2fe" },                        // active / selected / running
        purple: { 400: "#4facfe" },                      // gradient partner for cyan
        // --- Legacy "Case Room" tokens kept working until pages are rebuilt ---
        surface: "#161B27", // panel bg — cards, sidebars
        lifted: "#1E2235",  // raised element bg — inputs, inner cards
        edge: "#2A3148",    // borders, dividers
        dim: "#8693A8",     // muted text / secondary labels
        body: "#CBD5E0",    // primary body text
        head: "#EDF2F7",    // headings, important values
        amberlt: "#E8A820", // amber hover state
        steel: "#5B9BD5",   // legacy MEDIUM confidence
        rust: "#E08A4A",    // legacy LOW confidence
      },
      fontFamily: {
        // Redesign fonts (Outfit + JetBrains Mono via CDN in layout.js), with the
        // next/font-loaded vars kept as fallbacks so nothing goes unstyled mid-migration.
        sans: ["Outfit", "var(--font-display)", "system-ui", "sans-serif"],
        display: ["Outfit", "var(--font-display)", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
