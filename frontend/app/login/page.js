/* app/login/page.js
   REDESIGN §4.1 — two-column sign-in: brand block (left 60%) + glass sign-in
   panel (right 40%). Plain-English copy ("Sign in" / "Create account", not
   "AUTHENTICATE"). Toggle swaps only the submit fn + labels, no full re-render.
   PRESERVED: api.login/register wiring, setToken(res.token), vertex_user, and
   router.replace("/cases") are byte-for-byte the pre-redesign behavior (§1.1). */
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import GlassPanel from "@/components/ui/GlassPanel";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Label from "@/components/ui/Label";

const BULLETS = [
  "20-signal correlation engine",
  "BSA §63 court-admissible evidence",
  "SHA-256 tamper-evident audit chain",
];

export default function Login() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login"); // login | register
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isLogin = mode === "login";

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const fn = isLogin ? api.login : api.register;
      const res = await fn(username, password);
      setToken(res.token);
      try { localStorage.setItem("vertex_user", username); } catch (_) {}
      router.replace("/cases");
    } catch (err) {
      setError(
        isLogin
          ? "Sign-in failed — please check your username and password."
          : err.message || "Could not create the account."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen lg:flex">
      {/* LEFT — brand block (60%) */}
      <div className="hidden lg:flex lg:w-3/5 relative flex-col justify-center px-14">
        <div>
          <h1
            className="font-display font-bold text-slate-100 leading-none"
            style={{ fontSize: 48 }}
          >
            VERTEX<span className="text-cyan-400">.</span>
          </h1>
          <div className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-slate-500">
            SOCMINT Intelligence Platform · CIDECODE 2026
          </div>

          <div className="mt-10 space-y-1.5">
            {BULLETS.map((t) => (
              <div key={t} className="font-mono text-[12px] text-slate-400">
                <span className="text-cyan-400">↳</span> {t}
              </div>
            ))}
          </div>
        </div>

        <div className="absolute bottom-10 left-14 right-14 text-[11px] leading-relaxed text-slate-500">
          All sessions are logged. Unauthorised access is an offence under
          Section 43/66, IT Act 2000.
        </div>
      </div>

      {/* RIGHT — sign-in panel (40%) */}
      <div className="w-full lg:w-2/5 flex items-center justify-center px-6 py-12">
        <GlassPanel className="w-full max-w-md p-8">
          {/* mobile brand */}
          <div className="lg:hidden font-display font-bold text-slate-100 mb-6" style={{ fontSize: 30 }}>
            VERTEX<span className="text-cyan-400">.</span>
          </div>

          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-slate-500 mb-6">
            {isLogin ? "Sign in to continue" : "Create an account"}
          </div>

          {error && (
            <div
              className="mb-5 rounded-lg px-3 py-2 text-[13px]"
              style={{
                color: "#ff3366",
                background: "rgba(255,51,102,0.12)",
                border: "1px solid rgba(255,51,102,0.35)",
              }}
            >
              {error}
            </div>
          )}

          <form onSubmit={submit}>
            <div className="mb-4">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                autoFocus
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="mb-6">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                autoComplete={isLogin ? "current-password" : "new-password"}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={busy || !username || !password}
            >
              {busy
                ? isLogin ? "Signing in…" : "Creating account…"
                : isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => { setMode(isLogin ? "register" : "login"); setError(""); }}
            className="block w-full text-center mt-5 text-[12px] text-slate-400"
          >
            {isLogin ? "No account? " : "Have an account? "}
            <span className="text-cyan-400">{isLogin ? "Register" : "Sign in"}</span>
          </button>
        </GlassPanel>
      </div>
    </div>
  );
}
