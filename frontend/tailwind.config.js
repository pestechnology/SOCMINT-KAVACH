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
        ink: "#0E1117",     // deepest bg — page background
        surface: "#161B27", // panel bg — cards, sidebars
        lifted: "#1E2235",  // raised element bg — inputs, inner cards
        edge: "#2A3148",    // borders, dividers
        dim: "#8693A8",     // muted text / secondary labels (brightened for readability)
        body: "#CBD5E0",    // primary body text
        head: "#EDF2F7",    // headings, important values
        amber: "#D4900A",   // PRIMARY ACCENT — HIGH confidence, links, CTA
        amberlt: "#E8A820", // amber hover state
        emerald: "#27AE60", // verified, complete, chain ok
        steel: "#5B9BD5",   // MEDIUM confidence (brightened for dark-bg contrast)
        rust: "#E08A4A",    // LOW confidence (brightened for dark-bg contrast)
        crimson: "#C0392B", // REJECT, errors
      },
      fontFamily: {
        display: ["var(--font-display)", "Space Grotesk", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
        sans: ["var(--font-display)", "Space Grotesk", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
