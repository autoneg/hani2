import { useEffect, useState } from "react";
import { KeyRound, Loader2, LogIn, Play } from "lucide-react";
import { api, type AppConfig } from "../api";
import { Brand, ThemeButton } from "../negotiate/Header";
import { navigate, withBase } from "../router";
import { Gauge } from "../ui/Gauge";
import { Markdown } from "../ui/Markdown";

export function useConfig() {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  useEffect(() => {
    api<AppConfig>("/api/config").then(setCfg).catch(() => {});
  }, []);
  return cfg;
}

function Shell({ children, cfg }: { children: React.ReactNode; cfg: AppConfig | null }) {
  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-ink p-10 text-surface lg:flex">
        <Brand title={cfg?.title ?? "HANI2"} />
        <div className="max-w-md">
          <p className="text-3xl font-semibold leading-tight tracking-tight">
            Negotiate with an AI partner. See what every offer is worth before you decide.
          </p>
          <div className="mt-10 flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.04] p-5" aria-hidden>
            {[
              ["Partner offers", 0.34, "partner"],
              ["You counter", 0.71, "you"],
              ["Agreement", 0.58, "you"],
            ].map(([l, v, p]) => (
              <div key={l as string}>
                <div className="mb-1.5 text-xs text-white/60">{l}</div>
                <div style={{ ["--ink" as any]: "229 233 241", ["--sunken" as any]: "52 62 82" }}>
                  <Gauge value={v as number} reserved={0.4} party={p as any} />
                </div>
              </div>
            ))}
            <div className="text-xs text-white/50">The line marks what you get with no deal.</div>
          </div>
        </div>
        <div className="text-xs text-white/40">{cfg?.subtitle}</div>
      </aside>
      <main className="flex flex-col">
        <div className="flex items-center justify-between p-4 lg:justify-end">
          <div className="lg:hidden">
            <Brand title={cfg?.title ?? "HANI2"} />
          </div>
          <ThemeButton />
        </div>
        <div className="flex flex-1 items-center justify-center px-5 pb-16">
          <div className="w-full max-w-sm">{children}</div>
        </div>
      </main>
    </div>
  );
}

const Err = ({ msg }: { msg: string | null }) => (msg ? <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{msg}</div> : null);

function next() {
  const n = new URLSearchParams(location.search).get("next");
  return n && n.startsWith("/") ? n : "/app";
}

export function LoginPage() {
  const cfg = useConfig();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(new URLSearchParams(location.search).get("error") ? "Sign-in with that provider did not complete. Try again." : null);
  const [busy, setBusy] = useState(false);
  const pw = cfg && cfg.auth_mode !== "oauth";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("/api/auth/login", { body: { username: u, password: p } });
      const me = await api("/api/auth/me");
      navigate(me.needs_consent ? "/consent" : next());
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (cfg?.auth_mode === "none") navigate("/app", true);
  }, [cfg]);
  return (
    <Shell cfg={cfg}>
      <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
      <p className="mb-6 mt-1 text-sm text-muted">Use the account your study organiser gave you.</p>
      <div className="flex flex-col gap-3">
        <Err msg={err} />
        {pw && (
          <form className="flex flex-col gap-3" onSubmit={submit}>
            <label>
              <span className="label">Username</span>
              <input className="field py-2" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} autoFocus required />
            </label>
            <label>
              <span className="label">Password</span>
              <input className="field py-2" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required />
            </label>
            <button className="btn-primary mt-1 py-2.5" disabled={busy}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Log in
            </button>
          </form>
        )}
        {cfg && cfg.oauth_providers.length > 0 && (
          <>
            {pw && <div className="my-1 text-center text-xs text-muted">or</div>}
            {cfg.oauth_providers.map((prov) => (
              <a key={prov} className="btn-secondary py-2.5" href={withBase(`/api/oauth/${prov}/login`)}>
                <KeyRound size={16} />
                Continue with {prov === "github" ? "GitHub" : prov === "google" ? "Google" : prov}
              </a>
            ))}
          </>
        )}
        <div className="mt-4 flex flex-col gap-2 border-t border-line pt-4 text-sm">
          {cfg?.allow_registration && (
            <p className="text-muted">
              No account?{" "}
              <a className="font-medium text-you hover:underline" href={withBase("/register")} onClick={(e) => { e.preventDefault(); navigate("/register"); }}>
                Create one
              </a>
            </p>
          )}
          {cfg?.playground && (
            <a className="inline-flex items-center gap-1.5 font-medium text-you hover:underline" href={withBase("/play")}>
              <Play size={14} /> Try the playground without an account
            </a>
          )}
        </div>
      </div>
    </Shell>
  );
}

export function RegisterPage() {
  const cfg = useConfig();
  const [consent, setConsent] = useState("");
  const [f, setF] = useState({ full_name: "", username: "", email: "", confirm_email: "", password: "", confirm: "", consent: false });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/api/consent").then((r) => setConsent(r.markdown)).catch(() => {});
  }, []);
  const set = (k: string, v: any) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (consent && !f.consent) return setErr("Please accept the consent form to register.");
    setBusy(true);
    setErr(null);
    try {
      await api("/api/auth/register", { body: f });
      navigate("/app");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Shell cfg={cfg}>
      <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
      <p className="mb-5 mt-1 text-sm text-muted">Your results are saved under this account.</p>
      <form className="flex flex-col gap-3" onSubmit={submit}>
        <Err msg={err} />
        <label>
          <span className="label">Full name</span>
          <input className="field py-2" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} required autoComplete="name" />
        </label>
        <label>
          <span className="label">Username</span>
          <input className="field py-2" value={f.username} onChange={(e) => set("username", e.target.value)} required autoComplete="username" />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label>
            <span className="label">Email</span>
            <input className="field py-2" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} autoComplete="email" />
          </label>
          <label>
            <span className="label">Repeat email</span>
            <input className="field py-2" type="email" value={f.confirm_email} onChange={(e) => set("confirm_email", e.target.value)} />
          </label>
          <label>
            <span className="label">Password</span>
            <input className="field py-2" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} required autoComplete="new-password" />
          </label>
          <label>
            <span className="label">Repeat password</span>
            <input className="field py-2" type="password" value={f.confirm} onChange={(e) => set("confirm", e.target.value)} required autoComplete="new-password" />
          </label>
        </div>
        {consent && (
          <details className="rounded-lg border border-line bg-sunken/60 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium">Read the consent form</summary>
            <div className="scroll-thin mt-2 max-h-56 overflow-y-auto">
              <Markdown text={consent} size="sm" />
            </div>
          </details>
        )}
        {consent && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--you))]" checked={f.consent} onChange={(e) => set("consent", e.target.checked)} />
            I have read the consent form and agree to take part.
          </label>
        )}
        <button className="btn-primary mt-1 py-2.5" disabled={busy}>
          {busy && <Loader2 size={16} className="animate-spin" />} Create account
        </button>
        <p className="text-sm text-muted">
          Have an account?{" "}
          <a className="font-medium text-you hover:underline" href={withBase("/login")} onClick={(e) => { e.preventDefault(); navigate("/login"); }}>
            Log in
          </a>
        </p>
      </form>
    </Shell>
  );
}

export function ConsentPage() {
  const cfg = useConfig();
  const [md, setMd] = useState("");
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api("/api/consent").then((r) => setMd(r.markdown)).catch(() => {});
  }, []);
  return (
    <Shell cfg={cfg}>
      <h1 className="text-2xl font-semibold tracking-tight">Before you start</h1>
      <div className="scroll-thin my-4 max-h-[45vh] overflow-y-auto rounded-lg border border-line bg-surface p-4">
        <Markdown text={md} size="sm" />
      </div>
      <form
        className="flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/api/consent", { body: { agree, full_name: name } });
            navigate("/app");
          } catch (e: any) {
            setErr(e.message);
          }
        }}
      >
        <Err msg={err} />
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--you))]" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          I have read the information above and agree to take part.
        </label>
        <label>
          <span className="label">Full name (as your signature)</span>
          <input className="field py-2" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="btn-primary py-2.5" disabled={!agree || !name.trim()}>
          Agree and continue
        </button>
      </form>
    </Shell>
  );
}
