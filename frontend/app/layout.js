/* app/layout.js
   CHANGED: load Space Grotesk + JetBrains Mono via next/font/google and expose them
   as the --font-display / --font-mono CSS variables on <html>.
   DECISION: variables (not direct className) so Tailwind font-display/font-mono and the
   .display/.mono utility classes both resolve to the same loaded fonts. */
import "./globals.css";
import { Space_Grotesk, JetBrains_Mono } from "next/font/google";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-display",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata = {
  title: "VERTEX — SOCMINT Intelligence Platform",
  description: "SOCMINT / OSINT subject-profiling platform",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${jetbrainsMono.variable}`}>
      <head>
        {/* Redesign fonts (§2.2): Outfit + JetBrains Mono via CDN. next/font above
            stays loaded as a fallback so nothing goes unstyled mid-migration. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap"
          rel="stylesheet"
        />
        {/* Apply the saved theme before paint to avoid a light/dark flash on load.
            Dark is the default (:root), so we only need to stamp 'light' explicitly. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{if(localStorage.getItem('vertex-theme')==='light')document.documentElement.setAttribute('data-theme','light');}catch(e){}})();",
          }}
        />
      </head>
      <body className="min-h-screen font-display antialiased">
        {/* Ambient background layers (§2.3) — fixed, behind content */}
        <div className="glow-bg" />
        <div className="grid-overlay" />
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
