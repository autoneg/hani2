import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Bot,
  ChartColumn,
  Download,
  FileText,
  Loader2,
  Plane,
  RefreshCw,
  Save,
  Settings,
  Sparkles,
  Trash2,
  Trophy,
  UserPlus,
  Users,
} from "lucide-react";
import { api } from "../api";
import { Brand, ThemeButton } from "../negotiate/Header";
import { navigate } from "../router";
import { useStore } from "../store";
import { Plot } from "../ui/Plot";
import { Renderer } from "../ui/Renderer";

type Section = "overview" | "results" | "analytics" | "users" | "server" | "llm" | "agent" | "autopilot" | "texts";
const NAV: [Section, string, any][] = [
  ["overview", "Live sessions", Activity],
  ["results", "Results", Trophy],
  ["analytics", "Event analytics", ChartColumn],
  ["users", "Users", Users],
  ["server", "Server & studies", Settings],
  ["llm", "Language model", Sparkles],
  ["agent", "Support agent", Bot],
  ["autopilot", "Autopilot", Plane],
  ["texts", "Texts", FileText],
];

const toast = (message: string, level: "success" | "error" = "success") => useStore.getState().pushToast({ message, level });

/* ---------------- small form kit ---------------- */
function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5 border-b border-line/70 py-3 sm:grid-cols-[minmax(0,15rem)_1fr] sm:gap-6">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
const Check = ({ v, on }: { v: any; on: (x: boolean) => void }) => <input type="checkbox" role="switch" className="h-4 w-4 accent-[rgb(var(--you))]" checked={!!v} onChange={(e) => on(e.target.checked)} />;
const Text = ({ v, on, ph, type = "text" }: { v: any; on: (x: any) => void; ph?: string; type?: string }) => (
  <input className="field max-w-md" type={type} value={v ?? ""} placeholder={ph} onChange={(e) => on(type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} />
);
const Sel = ({ v, on, opts }: { v: any; on: (x: any) => void; opts: (string | [string, string])[] }) => (
  <select className="field max-w-xs" value={v ?? ""} onChange={(e) => on(e.target.value)}>
    {opts.map((o) => (Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o}>{o}</option>))}
  </select>
);
const List = ({ v, on, ph }: { v: any[]; on: (x: string[]) => void; ph?: string }) => (
  <input className="field max-w-xl" defaultValue={(v || []).join(", ")} placeholder={ph} onBlur={(e) => on(e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} />
);

function useSettings(kind: string) {
  const [data, setData] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    api(`/api/admin/settings/${kind}`).then(setData);
  }, [kind]);
  const set = useCallback((path: string, value: any) => {
    setDirty(true);
    setData((d: any) => {
      const out = structuredClone(d);
      const keys = path.split(".");
      let o = out;
      keys.slice(0, -1).forEach((k) => (o = o[k] ??= {}));
      o[keys[keys.length - 1]] = value;
      return out;
    });
  }, []);
  const save = async () => {
    await api(`/api/admin/settings/${kind}`, { method: "PUT", body: data });
    setDirty(false);
    toast("Saved. New sessions use these settings.");
  };
  return { data, set, save, dirty };
}

function SaveBar({ dirty, save }: { dirty: boolean; save: () => void }) {
  return (
    <div className="sticky bottom-0 mt-4 flex items-center justify-end gap-3 border-t border-line bg-paper/90 py-3 backdrop-blur">
      {dirty && <span className="text-xs text-muted">Unsaved changes</span>}
      <button className="btn-primary" onClick={save} disabled={!dirty}>
        <Save size={15} /> Save
      </button>
    </div>
  );
}

const H = ({ children, sub }: { children: React.ReactNode; sub?: string }) => (
  <div className="mb-4">
    <h2 className="text-xl font-semibold tracking-tight">{children}</h2>
    {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
  </div>
);

/* ---------------- sections ---------------- */
function Overview() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sum, setSum] = useState<any>(null);
  const load = () => {
    api("/api/admin/sessions").then(setRows);
    api("/api/admin/events/summary").then(setSum);
  };
  useEffect(() => {
    load();
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <>
      <H sub="Everyone with a session on this server right now. Refreshes every 5 seconds.">Live sessions</H>
      {sum && (
        <Renderer
          components={[
            {
              type: "stats",
              children: [
                { type: "stat", label: "Open sessions", value: rows?.length ?? 0 },
                { type: "stat", label: "Negotiating now", value: rows?.filter((r) => r.phase === "running").length ?? 0 },
                { type: "stat", label: "Recorded sessions", value: sum.n_sessions },
                { type: "stat", label: "Logged events", value: sum.n_events },
              ],
            },
          ]}
          ctx={{ onInput: () => {}, onAction: () => {} }}
        />
      )}
      <div className="mt-4">
        {rows === null ? (
          <Loader2 className="animate-spin text-muted" />
        ) : (
          <Renderer components={[{ type: "table", rows, columns: ["user", "mode", "phase", "round", "scenario", "opponent", "support_agent", "connections", "idle"], searchable: true }]} ctx={{ onInput: () => {}, onAction: () => {} }} />
        )}
      </div>
    </>
  );
}

function Results() {
  const [data, setData] = useState<any>(null);
  const [cols, setCols] = useState<string[]>([]);
  useEffect(() => {
    api("/api/admin/results").then((d) => {
      setData(d);
      setCols(d.default_columns.filter((c: string) => d.columns.includes(c)));
    });
  }, []);
  if (!data) return <Loader2 className="animate-spin text-muted" />;
  return (
    <>
      <div className="flex items-start justify-between">
        <H sub={`${data.rows.length} negotiations from every participant.`}>Results</H>
        <a className="btn-secondary" href="/api/admin/results.csv">
          <Download size={15} /> Download CSV
        </a>
      </div>
      {data.leaderboard.length > 0 && (
        <section className="panel mb-4 p-4">
          <div className="mb-2 font-semibold">Leaderboard</div>
          <Renderer
            components={[{ type: "table", rows: data.leaderboard, columns: ["user", "score", "negotiations", "mean_utility"], formats: { score: "float", mean_utility: "percent" }, page_size: 10 }]}
            ctx={{ onInput: () => {}, onAction: () => {} }}
          />
        </section>
      )}
      <section className="panel p-4">
        <Renderer
          components={[
            { type: "card", title: "Choose columns", collapsible: true, collapsed: true, children: [{ type: "multiselect", name: "cols", options: data.columns.map((c: string) => ({ label: c, value: c })), value: cols }] },
            { type: "table", rows: [...data.rows].reverse(), columns: cols, searchable: true, formats: { human_utility: "percent", agent_utility: "percent", human_advantage: "percent" } },
          ]}
          ctx={{ onInput: (_, v) => setCols(v), onAction: () => {} }}
        />
      </section>
    </>
  );
}

function Analytics() {
  const [sum, setSum] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [f, setF] = useState({ user: "", types: "", since: "", until: "" });
  const load = () => {
    api("/api/admin/events/summary").then(setSum);
    const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as any).toString();
    api(`/api/admin/events?limit=2000&${q}`).then(setEvents);
  };
  useEffect(load, []);
  const types = sum ? Object.keys(sum.by_type) : [];
  return (
    <>
      <div className="flex items-start justify-between">
        <H sub="Everything participants and support agents did, as logged by the server.">Event analytics</H>
        <a className="btn-secondary" href="/api/admin/events.csv">
          <Download size={15} /> Export CSV
        </a>
      </div>
      {sum && (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="panel p-4">
            <div className="mb-1 text-sm font-semibold">Events by type</div>
            <Plot
              height={300}
              figure={{
                data: [{ type: "bar", orientation: "h", y: types, x: types.map((t) => sum.by_type[t]), marker: { color: "#3B4BDB" } }],
                layout: { margin: { l: 130, r: 10, t: 10, b: 30 }, yaxis: { automargin: true } },
              }}
            />
          </section>
          <section className="panel p-4">
            <div className="mb-1 text-sm font-semibold">Activity over time (per hour)</div>
            <Plot
              height={300}
              figure={{
                data: [{ type: "scatter", mode: "lines", fill: "tozeroy", x: sum.by_hour.map((r: any) => r.hour + ":00"), y: sum.by_hour.map((r: any) => r.count), line: { color: "#D9821B" } }],
                layout: { margin: { l: 40, r: 10, t: 10, b: 40 } },
              }}
            />
          </section>
        </div>
      )}
      <section className="panel mt-4 p-4">
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label>
            <span className="label">User</span>
            <select className="field w-40" value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })}>
              <option value="">Everyone</option>
              {(sum?.users ?? []).map((u: string) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">Event type</span>
            <select className="field w-44" value={f.types} onChange={(e) => setF({ ...f, types: e.target.value })}>
              <option value="">All types</option>
              {types.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="label">From</span>
            <input className="field" type="date" value={f.since} onChange={(e) => setF({ ...f, since: e.target.value })} />
          </label>
          <label>
            <span className="label">Until</span>
            <input className="field" type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} />
          </label>
          <button className="btn-primary" onClick={load}>
            <RefreshCw size={14} /> Apply
          </button>
        </div>
        <Renderer components={[{ type: "table", rows: events, columns: ["timestamp", "user", "event_type", "component", "action", "value", "scenario_id", "utility_value"], searchable: true, page_size: 50 }]} ctx={{ onInput: () => {}, onAction: () => {} }} />
      </section>
      {sum?.sessions?.length > 0 && (
        <section className="panel mt-4 p-4">
          <div className="mb-2 text-sm font-semibold">Recorded sessions</div>
          <Renderer components={[{ type: "table", rows: sum.sessions, columns: ["start_time", "end_time", "user", "mode", "experiment", "user_agent"], searchable: true }]} ctx={{ onInput: () => {}, onAction: () => {} }} />
        </section>
      )}
    </>
  );
}

function UsersSection() {
  const [rows, setRows] = useState<any[]>([]);
  const [n, setN] = useState({ username: "", password: "", email: "", is_admin: false });
  const load = () => api("/api/admin/users").then(setRows);
  useEffect(() => {
    load();
  }, []);
  return (
    <>
      <H sub="Accounts that can log in to the app.">Users</H>
      <form
        className="panel mb-4 flex flex-wrap items-end gap-2 p-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api("/api/admin/users", { body: n });
            toast(`Created ${n.username}`);
            setN({ username: "", password: "", email: "", is_admin: false });
            load();
          } catch (err: any) {
            toast(err.message, "error");
          }
        }}
      >
        <label>
          <span className="label">Username</span>
          <input className="field w-40" value={n.username} onChange={(e) => setN({ ...n, username: e.target.value })} required />
        </label>
        <label>
          <span className="label">Password</span>
          <input className="field w-40" type="password" value={n.password} onChange={(e) => setN({ ...n, password: e.target.value })} required />
        </label>
        <label>
          <span className="label">Email</span>
          <input className="field w-52" type="email" value={n.email} onChange={(e) => setN({ ...n, email: e.target.value })} />
        </label>
        <label className="mb-2 flex items-center gap-1.5 text-sm">
          <Check v={n.is_admin} on={(v) => setN({ ...n, is_admin: v })} /> Admin
        </label>
        <button className="btn-primary">
          <UserPlus size={15} /> Add user
        </button>
      </form>
      <div className="panel divide-y divide-line">
        {rows.map((u) => (
          <div key={u.username} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
            <div className="min-w-[10rem] flex-1">
              <div className="text-sm font-medium">
                {u.username} {u.is_admin && <span className="ml-1 rounded bg-bad/10 px-1.5 text-xs text-bad">admin</span>}
              </div>
              <div className="text-xs text-muted">{[u.full_name, u.email, u.oauth && `via ${u.oauth}`, u.consented ? "consented" : "no consent yet"].filter(Boolean).join(", ")}</div>
            </div>
            {u.username !== "admin" && (
              <button className="btn-ghost text-xs" onClick={async () => { await api(`/api/admin/users/${u.username}`, { method: "PATCH", body: { is_admin: !u.is_admin } }); load(); }}>
                {u.is_admin ? "Remove admin" : "Make admin"}
              </button>
            )}
            <button
              className="btn-ghost text-xs"
              onClick={async () => {
                const p = prompt(`New password for ${u.username}`);
                if (p) {
                  await api(`/api/admin/users/${u.username}`, { method: "PATCH", body: { password: p } });
                  toast("Password changed");
                }
              }}
            >
              Set password
            </button>
            {u.username !== "admin" && (
              <button
                className="btn-ghost px-2 text-bad"
                aria-label={`Delete ${u.username}`}
                onClick={async () => {
                  if (confirm(`Delete ${u.username}? Their results are kept.`)) {
                    await api(`/api/admin/users/${u.username}`, { method: "DELETE" });
                    load();
                  }
                }}
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function ServerSection({ meta }: { meta: any }) {
  const { data: d, set, save, dirty } = useSettings("env");
  if (!d) return <Loader2 className="animate-spin text-muted" />;
  const disabled: string[] = d.tools?.disabled ?? [];
  return (
    <>
      <H sub="Stored in env.json. Changes apply to sessions started after saving.">Server and studies</H>
      <section className="panel px-4">
        <Row label="Title">
          <Text v={d.title} on={(v) => set("title", v)} />
        </Row>
        <Row label="Subtitle">
          <Text v={d.subtitle} on={(v) => set("subtitle", v)} />
        </Row>
        <Row label="Sign-in" hint="Password, OAuth, both, or no sign-in at all">
          <Sel v={d.auth.mode} on={(v) => set("auth.mode", v)} opts={[["password", "Username and password"], ["oauth", "OAuth only"], ["dual", "Password and OAuth"], ["none", "No sign-in"]]} />
        </Row>
        <Row label="People can create accounts">
          <Check v={d.auth.allow_registration} on={(v) => set("auth.allow_registration", v)} />
        </Row>
        <Row label="Require consent" hint="Participants accept consent.md before negotiating">
          <Check v={d.auth.enforce_consent} on={(v) => set("auth.enforce_consent", v)} />
        </Row>
        <Row label="Playground" hint="Open /play without an account">
          <Check v={d.playground?.enabled} on={(v) => set("playground.enabled", v)} />
        </Row>
        <Row label="Admin emails" hint="OAuth users with these emails are admins">
          <List v={d.admin?.emails} on={(v) => set("admin.emails", v)} ph="a@uni.edu, b@uni.edu" />
        </Row>
        <Row label="OAuth redirect base" hint="Public URL of this server, e.g. https://negotiate.example.org">
          <Text v={d.oauth?.redirect_uri} on={(v) => set("oauth.redirect_uri", v)} />
        </Row>
        {["github", "google"].map((p) => (
          <Row key={p} label={`${p === "github" ? "GitHub" : "Google"} OAuth`} hint="Client id and secret">
            <div className="flex flex-wrap gap-2">
              <Text v={d.oauth?.providers?.[p]?.key} on={(v) => set(`oauth.providers.${p}.key`, v)} ph="client id" />
              <Text v={d.oauth?.providers?.[p]?.secret} on={(v) => set(`oauth.providers.${p}.secret`, v)} ph="client secret" type="password" />
            </div>
          </Row>
        ))}
      </section>
      <h3 className="mb-1 mt-6 font-semibold">Negotiation defaults</h3>
      <section className="panel px-4">
        <Row label="Rounds">
          <Text type="number" v={d.negotiation?.n_steps} on={(v) => set("negotiation.n_steps", v)} />
        </Row>
        <Row label="Time limit (seconds)" hint="Empty for no limit">
          <Text type="number" v={d.negotiation?.time_limit} on={(v) => set("negotiation.time_limit", v)} />
        </Row>
        <Row label="Opponent agents" hint="The negotiators participants face: names and groups such as :template, :notext, :llm, :negmas, :classic">
          <List
            v={d.opponents?.length ? d.opponents : d.agents}
            on={(v) => {
              set("opponents", v);
              if (d.agents?.length) set("agents", []);
            }}
            ph=":template"
          />
        </Row>
        {meta && (
          <Row label="Available opponent groups">
            <div className="flex flex-col gap-1 text-xs text-muted">
              {Object.entries(meta.opponent_groups ?? meta.agent_groups).map(([g, l]: any) => (
                <div key={g}>
                  <b className="text-ink">:{g}</b> {l.length} negotiators
                </div>
              ))}
            </div>
          </Row>
        )}
      </section>
      <h3 className="mb-1 mt-6 font-semibold">Tools</h3>
      <section className="panel px-4">
        <Row label="Enlarged tools open as" hint="Each tool has an enlarge button; Put back returns it to its pane">
          <Sel v={d.tools?.maximize ?? "window"} on={(v) => set("tools.maximize", v)} opts={[["window", "A large window"], ["fullscreen", "The full screen"], ["off", "Not allowed"]]} />
        </Row>
        <Row label="Participants see opponent utilities" hint="Lets everyone switch on the opponent's utility in the Utility Plot and Trace">
          <Check v={d.tools?.show_opponent_utility} on={(v) => set("tools.show_opponent_utility", v)} />
        </Row>
        {meta?.tools.map((t: any) => {
          const adminOnly = d.tools?.overrides?.[t.name]?.admin_only ?? t.admin_only;
          return (
            <Row key={t.name} label={t.name} hint={t.description}>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
                <label className="flex items-center gap-2">
                  <Check v={!disabled.includes(t.name)} on={(v) => set("tools.disabled", v ? disabled.filter((x) => x !== t.name) : [...disabled, t.name])} />
                  Offered
                </label>
                <label className="flex items-center gap-2" title="Off: every participant gets this tool">
                  <Check v={adminOnly} on={(v) => set(`tools.overrides.${t.name}.admin_only`, v)} />
                  Admins only
                </label>
                <span className="text-xs text-muted">
                  {t.pane} pane, appears at {t.timing}
                </span>
              </div>
            </Row>
          );
        })}
        <Row label="Extra tools" hint="Python classes, e.g. my_pkg.tools:MyTool">
          <List v={d.tools?.extra} on={(v) => set("tools.extra", v)} />
        </Row>
      </section>
      <SaveBar dirty={dirty} save={save} />
    </>
  );
}

function LLMSection() {
  const { data: d, set, save, dirty } = useSettings("llm");
  const [status, setStatus] = useState<any>(null);
  useEffect(() => {
    api("/api/admin/llm/status").then(setStatus).catch(() => {});
  }, []);
  if (!d) return <Loader2 className="animate-spin text-muted" />;
  return (
    <>
      <H sub="Used by the LLM offer tool, message writing, offer extraction and LLM opponent agents.">Language model</H>
      {status && (
        <div className={`mb-4 rounded-lg px-3 py-2 text-sm ${status.configured ? "bg-good/10 text-good" : "bg-warn/10 text-warn"}`}>
          {status.configured ? `Ready: ${status.provider} / ${status.model}` : `Not configured: set ${status.api_key_env} or use Ollama.`}
        </div>
      )}
      <section className="panel px-4">
        <Row label="Provider">
          <Sel v={d.provider} on={(v) => set("provider", v)} opts={["ollama", "openai", "anthropic", "gemini", "azure", "groq", "mistral", "openrouter"]} />
        </Row>
        <Row label="Model">
          <Text v={d.model} on={(v) => set("model", v)} ph="qwen3:4b-instruct" />
        </Row>
        <Row label="Ollama address">
          <Text v={d.ollama_base_url} on={(v) => set("ollama_base_url", v)} />
        </Row>
        <Row label="API key variable" hint="The name of the environment variable that holds the key">
          <Text v={d.api_key_env} on={(v) => set("api_key_env", v)} />
        </Row>
        <Row label="Temperature">
          <Text type="number" v={d.temperature} on={(v) => set("temperature", v)} />
        </Row>
        <Row label="Max tokens">
          <Text type="number" v={d.max_tokens} on={(v) => set("max_tokens", v)} />
        </Row>
        {["extraction_prompt", "generation_prompt", "instruction_prompt"].map((k) =>
          d[k] !== undefined ? (
            <Row key={k} label={k.replace("_", " ").replace(/^./, (c) => c.toUpperCase())} hint="Placeholders in {braces} are filled in">
              <textarea className="field font-mono text-xs" rows={8} value={d[k] ?? ""} onChange={(e) => set(k, e.target.value)} />
            </Row>
          ) : null,
        )}
      </section>
      <SaveBar dirty={dirty} save={save} />
    </>
  );
}

function AgentSection({ meta }: { meta: any }) {
  const { data: d, set, save, dirty } = useSettings("support_agent");
  if (!d) return <Loader2 className="animate-spin text-muted" />;
  return (
    <>
      <H sub="The support agent (the assistant beside each participant). Participants can narrow these permissions, never widen them.">Support agent</H>
      <section className="panel px-4">
        <Row label="Who gets the support agent">
          <Sel v={d.mode} on={(v) => set("mode", v)} opts={[["on", "Everyone"], ["auto", "Admins only"], ["off", "Nobody"]]} />
        </Row>
        <Row label="Agent class" hint="module:Class of your own agent; empty for the built-in one">
          <Text v={d.agent_class} on={(v) => set("agent_class", v || null)} ph="my_agent:MyAgent" />
        </Row>
        <Row label="Provider / model">
          <div className="flex flex-wrap gap-2">
            <Sel v={d.provider} on={(v) => set("provider", v)} opts={["ollama", "openai", "anthropic", "gemini", "azure", "groq", "mistral", "openrouter"]} />
            <Text v={d.model} on={(v) => set("model", v)} />
          </div>
        </Row>
        <Row label="API base" hint="e.g. http://localhost:11434 for a local server">
          <Text v={d.api_base} on={(v) => set("api_base", v || null)} />
        </Row>
        <Row label="API key variable">
          <Text v={d.api_key_env} on={(v) => set("api_key_env", v)} />
        </Row>
        <Row label="Temperature / max tokens / tool steps">
          <div className="flex flex-wrap gap-2">
            <Text type="number" v={d.temperature} on={(v) => set("temperature", v)} />
            <Text type="number" v={d.max_tokens} on={(v) => set("max_tokens", v)} />
            <Text type="number" v={d.max_tool_iterations} on={(v) => set("max_tool_iterations", v)} />
          </div>
        </Row>
        <Row label="Highest autonomy" hint="Suggest: points at buttons. Semi: sends counter-offers, asks before accept/end. Full: acts.">
          <Sel v={d.autonomy} on={(v) => set("autonomy", v)} opts={[["suggest", "Suggest"], ["semi", "Semi"], ["full", "Full"]]} />
        </Row>
        <Row label="Abilities granted">
          <div className="grid gap-1.5 sm:grid-cols-2">
            {Object.entries(meta?.capabilities ?? {}).map(([k, c]: any) => (
              <label key={k} className="flex items-start gap-2 text-sm" title={c.description}>
                <Check v={d.capabilities?.[k]} on={(v) => set(`capabilities.${k}`, v)} />
                <span>
                  {c.label}
                  <span className="block text-xs text-muted">{c.description}</span>
                </span>
              </label>
            ))}
          </div>
        </Row>
        <Row label="Speaks up unprompted when">
          <div className="flex flex-col gap-1.5 text-sm">
            {[
              ["on_negotiation_started", "a negotiation starts"],
              ["on_action_requested", "it is the participant's turn"],
              ["on_negotiation_ended", "a negotiation ends"],
            ].map(([k, l]) => (
              <label key={k} className="flex items-center gap-2">
                <Check v={d.proactive?.[k]} on={(v) => set(`proactive.${k}`, v)} /> {l}
              </label>
            ))}
          </div>
        </Row>
        <Row label="System prompt">
          <textarea className="field text-xs" rows={12} value={d.system_prompt ?? ""} onChange={(e) => set("system_prompt", e.target.value)} />
        </Row>
      </section>
      <SaveBar dirty={dirty} save={save} />
    </>
  );
}

function AutopilotSection({ meta }: { meta: any }) {
  const { data: d, set, save, dirty } = useSettings("autopilot");
  if (!d) return <Loader2 className="animate-spin text-muted" />;
  const drivers: string[] = meta?.autopilot_drivers ?? [];
  const allowed: string[] | null = d.allowed_drivers;
  return (
    <>
      <H sub="Let an agent make every decision for the participant.">Autopilot</H>
      <section className="panel px-4">
        <Row label="Autopilot allowed">
          <Check v={d.allowed} on={(v) => set("allowed", v)} />
        </Row>
        <Row label="Default driver">
          <Sel v={d.driver} on={(v) => set("driver", v)} opts={drivers} />
        </Row>
        <Row label="Participants choose the driver" hint="Default: only in the playground">
          <Sel v={d.user_can_choose === null || d.user_can_choose === undefined ? "default" : d.user_can_choose ? "yes" : "no"} on={(v) => set("user_can_choose", v === "default" ? null : v === "yes")} opts={[["default", "Playground only"], ["yes", "Yes"], ["no", "No"]]} />
        </Row>
        <Row label="Drivers offered" hint="None ticked offers all">
          <div className="grid gap-1 sm:grid-cols-2">
            {drivers.map((x) => (
              <label key={x} className="flex items-center gap-2 text-sm">
                <Check v={allowed?.includes(x)} on={(v) => set("allowed_drivers", v ? [...(allowed ?? []), x] : (allowed ?? []).filter((y) => y !== x))} /> {x}
              </label>
            ))}
          </div>
        </Row>
        <Row label="Pause between steps (s)">
          <Text type="number" v={d.step_delay} on={(v) => set("step_delay", v)} />
        </Row>
      </section>
      <SaveBar dirty={dirty} save={save} />
    </>
  );
}

function TextsSection() {
  const [which, setWhich] = useState<"consent" | "announcements" | "scenario_order">("announcements");
  const [text, setText] = useState("");
  useEffect(() => {
    api(`/api/admin/settings/${which}`).then((r) => setText(r.text));
  }, [which]);
  return (
    <>
      <H sub="Markdown shown to participants, and the order of scenario types (one per line).">Texts</H>
      <div className="mb-3 inline-flex rounded-lg bg-sunken p-0.5">
        {[
          ["announcements", "Welcome text"],
          ["consent", "Consent form"],
          ["scenario_order", "Scenario order"],
        ].map(([k, l]) => (
          <button key={k} className={`rounded-md px-3 py-1.5 text-sm ${which === k ? "bg-surface shadow-lift" : "text-muted"}`} onClick={() => setWhich(k as any)}>
            {l}
          </button>
        ))}
      </div>
      <textarea className="field min-h-[50vh] font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="mt-3 flex justify-end">
        <button
          className="btn-primary"
          onClick={async () => {
            await api(`/api/admin/settings/${which}`, { method: "PUT", body: { text } });
            toast("Saved");
          }}
        >
          <Save size={15} /> Save
        </button>
      </div>
    </>
  );
}

export function AdminPage() {
  const [section, setSection] = useState<Section>(() => (location.hash.slice(1) as Section) || "overview");
  const [meta, setMeta] = useState<any>(null);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  useEffect(() => {
    api("/api/auth/me").then((m) => {
      if (!m.user) navigate("/login?next=/admin", true);
      else setAllowed(!!m.is_admin);
    });
    api("/api/admin/meta").then(setMeta).catch(() => {});
  }, []);
  useEffect(() => {
    history.replaceState(null, "", `#${section}`);
  }, [section]);
  const body = useMemo(() => {
    switch (section) {
      case "overview": return <Overview />;
      case "results": return <Results />;
      case "analytics": return <Analytics />;
      case "users": return <UsersSection />;
      case "server": return <ServerSection meta={meta} />;
      case "llm": return <LLMSection />;
      case "agent": return <AgentSection meta={meta} />;
      case "autopilot": return <AutopilotSection meta={meta} />;
      case "texts": return <TextsSection />;
    }
  }, [section, meta]);
  if (allowed === false)
    return <div className="flex h-screen items-center justify-center text-sm text-muted">This page is for administrators.</div>;
  return (
    <div className="flex min-h-[100dvh] flex-col lg:flex-row">
      <nav className="flex shrink-0 flex-col border-b border-line bg-surface lg:h-[100dvh] lg:w-60 lg:border-b-0 lg:border-r" aria-label="Administration">
        <div className="flex items-center justify-between p-4">
          <Brand />
          <ThemeButton />
        </div>
        <div className="scroll-thin flex gap-0.5 overflow-x-auto px-2 pb-2 lg:flex-col lg:overflow-visible">
          {NAV.map(([k, l, I]) => (
            <button key={k} aria-current={section === k} onClick={() => setSection(k)} className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm ${section === k ? "bg-sunken font-medium text-ink" : "text-muted hover:bg-sunken/60 hover:text-ink"}`}>
              <I size={16} /> {l}
            </button>
          ))}
        </div>
        <div className="mt-auto hidden p-3 lg:block">
          <a className="btn-ghost w-full justify-start" href="/app" onClick={(e) => { e.preventDefault(); navigate("/app"); }}>
            <ArrowLeft size={15} /> Back to negotiating
          </a>
        </div>
      </nav>
      <main className="scroll-thin min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8 lg:h-[100dvh]">
        <div className="mx-auto max-w-6xl">{body}</div>
      </main>
    </div>
  );
}
