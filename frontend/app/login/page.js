/* app/login/page.js
   CHANGED: full rewrite to the two-panel "Case Room" sign-in — no floating card; left
   panel is brand + animated CSS correlation graph + capability lines + IT Act notice.
   DECISION: capture the typed username into localStorage('vertex_user') here (NOT in
   api.js) so the registry nav can show it — api.js behavior is untouched. */
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login"); // login | register
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const fn = mode === "login" ? api.login : api.register;
      const res = await fn(username, password);
      setToken(res.token);
      try { localStorage.setItem("vertex_user", username); } catch (_) {}
      router.replace("/cases");
    } catch (err) {
      setError(
        mode === "login"
          ? "Authentication failed — invalid credentials."
          : err.message || "Registration failed."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* LEFT PANEL */}
      <div className="hidden md:flex w-1/2 bg-ink relative flex-col justify-center px-12">
        <div>
          <div className="display text-head" style={{ fontSize: 40, fontWeight: 600, lineHeight: 1 }}>
            VERTEX<span className="text-amber">.</span>
          </div>
          <div className="mono text-dim" style={{ fontSize: 11, letterSpacing: "0.1em", marginTop: 6 }}>
            SOCMINT INTELLIGENCE PLATFORM
          </div>

          {/* animated correlation graph — pure CSS */}
          <svg width="260" height="170" viewBox="0 0 260 170" className="mt-10" aria-hidden>
            <line className="lg-edge" x1="34" y1="92" x2="96" y2="36" style={{ animationDelay: "0s" }} />
            <line className="lg-edge" x1="96" y1="36" x2="186" y2="58" style={{ animationDelay: "0.6s" }} />
            <line className="lg-edge" x1="96" y1="36" x2="124" y2="118" style={{ animationDelay: "1.2s" }} />
            <line className="lg-edge" x1="124" y1="118" x2="214" y2="128" style={{ animationDelay: "1.8s" }} />
            <circle className="lg-node" cx="34" cy="92" r="6" style={{ animationDelay: "0s" }} />
            <circle className="lg-node" cx="96" cy="36" r="9" style={{ animationDelay: "0.4s" }} />
            <circle className="lg-node" cx="186" cy="58" r="7" style={{ animationDelay: "0.8s" }} />
            <circle className="lg-node" cx="124" cy="118" r="8" style={{ animationDelay: "1.2s" }} />
            <circle className="lg-node" cx="214" cy="128" r="6" style={{ animationDelay: "1.6s" }} />
          </svg>

          <div className="mt-8 space-y-1">
            {[
              "12-signal correlation engine",
              "BSA-63 court-admissible PDF output",
              "SHA-256 tamper-evident audit chain",
            ].map((t) => (
              <div key={t} className="mono text-amber" style={{ fontSize: 10 }}>
                ↳ {t}
              </div>
            ))}
          </div>
        </div>

        <div className="absolute bottom-8 left-12 right-12 mono text-dim" style={{ fontSize: 9, lineHeight: 1.5 }}>
          All sessions are logged. Unauthorised access is an offence under Section 43/66, IT Act 2000.
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="w-full md:w-1/2 bg-surface md:border-l border-edge flex items-center justify-center px-6">
        <form onSubmit={submit} className="w-full" style={{ maxWidth: 360, padding: 48 }}>
          {/* mobile brand */}
          <div className="md:hidden display text-head mb-6" style={{ fontSize: 28, fontWeight: 600 }}>
            VERTEX<span className="text-amber">.</span>
          </div>

          <div className="display text-dim mb-6" style={{ fontSize: 14 }}>
            {mode === "login" ? "Sign in to continue" : "Create an investigator account"}
          </div>

          {error && (
            <div
              className="display text-crimson mb-4"
              style={{ fontSize: 11, background: "rgba(192,57,43,0.15)", borderLeft: "2px solid #C0392B", padding: "8px 12px" }}
            >
              {error}
            </div>
          )}

          <Field label="USERNAME" value={username} onChange={setUsername} autoFocus />
          <Field label="PASSWORD" value={password} onChange={setPassword} type="password" />

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="mono w-full disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              border: "1.5px solid #D4900A", color: "#D4900A", background: "transparent",
              fontSize: 12, letterSpacing: "0.08em", padding: 11, borderRadius: 2, marginTop: 8,
            }}
            onMouseEnter={(e) => { if (!e.currentTarget.disabled) { e.currentTarget.style.background = "rgba(212,144,10,0.10)"; e.currentTarget.style.color = "#E8A820"; } }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#D4900A"; }}
          >
            {busy ? "WORKING…" : "AUTHENTICATE"}
          </button>

          <button
            type="button"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
            className="mono text-dim block w-full text-center mt-4"
            style={{ fontSize: 10 }}
          >
            {mode === "login" ? "No account? " : "Have an account? "}
            <span className="text-amber">{mode === "login" ? "Register" : "Sign in"}</span>
          </button>
        </form>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", autoFocus = false }) {
  return (
    <div className="mb-4">
      <label className="mono text-dim block mb-1" style={{ fontSize: 9, letterSpacing: "0.1em" }}>
        {label}
      </label>
      <input
        type={type}
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        className="mono w-full text-head bg-lifted"
        style={{ border: "1px solid #2A3148", borderRadius: 2, fontSize: 13, padding: "10px 12px", outline: "none" }}
        onFocus={(e) => (e.currentTarget.style.borderColor = "#D4900A")}
        onBlur={(e) => (e.currentTarget.style.borderColor = "#2A3148")}
      />
    </div>
  );
}
