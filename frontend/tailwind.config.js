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
