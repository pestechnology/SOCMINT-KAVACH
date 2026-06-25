import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VERTEX — SOCMINT Investigator",
  description: "SOCMINT/OSINT suspect profiling tool",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-100 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
