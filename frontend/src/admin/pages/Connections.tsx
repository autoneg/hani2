import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FlaskConical, LogIn, LogOut, Plug, Plus, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row, Tile } from "../Row";
import { Select } from "../controls/Select";
import { TextField } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { Note, Spinner } from "../schema";
import { copyText, toast } from "../toast";

export interface ProviderInfo {
  id: string;
  label: string;
  auth: string[];
  env: string;
  base_url: string;
  help: string;
  no_subscription: string;
  notes: string;
  sources: string[];
  examples: string[];
  needs_base_url: boolean;
  featured: boolean;
}

export interface ConnectionInfo {
  name: string;
  provider: string;
  provider_label: string;
  auth: string;
  base: string;
  implicit: boolean;
  credentials: boolean;
  credentials_reason: string;
  api_key?: string;
  api_key_env?: string;
  api_key_env_set?: boolean;
  signed_in?: boolean;
  label?: string;
  auth_methods: string[];
}

export const AUTH_LABELS: Record<string, string> = {
  api_key: "API key (stored here)",
  api_key_env: "API key in an environment variable",
  subscription: "Subscription sign-in",
  none: "No sign-in",
};

export const CONNECTION_ENTRIES = [
  { id: "connections-list", label: "Connections", hint: "Status, test, sign in, remove", keywords: "provider api key login subscription" },
  { id: "connection-add", label: "Add a connection", hint: "Anthropic, OpenAI, Ollama, GitHub Copilot, …", keywords: "new provider key ollama copilot chatgpt" },
  { id: "providers-table", label: "Providers and sign-in methods", hint: "Which provider supports API keys or subscriptions", keywords: "auth oauth device" },
];

export function useConnections() {
  const [list, setList] = useState<ConnectionInfo[] | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const load = () =>
    Promise.all([api("/api/admin/connections"), api("/api/admin/providers")])
      .then(([c, p]) => {
        setList(c.connections);
        setProviders(p.providers);
      })
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  return { list, providers, reload: load };
}

function Dot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span aria-hidden className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${ok ? "bg-good" : warn ? "bg-warn" : "bg-bad"}`} />;
}

/** The device-code sign-in: shows the code and the address, polls until it is done. */
function DeviceLogin({ name, onDone }: { name: string; onDone: () => void }) {
  const [st, setSt] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  useEffect(() => {
    let alive = true;
    const poll = (ms: number) => {
      timer.current = window.setTimeout(async () => {
        try {
          const r = await api(`/api/admin/connections/${encodeURIComponent(name)}/login`);
          if (!alive) return;
          if (r.status === "connected") {
            toast(`Signed in: ${name}`);
            onDone();
            return;
          }
          if (r.status !== "pending") {
            setErr(`The sign-in ${r.status === "none" ? "was not started" : r.status === "denied" ? "was declined" : "expired"}.`);
            return;
          }
          poll((r.interval ?? 5) * 1000);
        } catch (e: any) {
          if (alive) setErr(e.message);
        }
      }, ms);
    };
    api(`/api/admin/connections/${encodeURIComponent(name)}/login`, { method: "POST" })
      .then((r) => {
        if (!alive) return;
        setSt(r);
        poll((r.interval ?? 5) * 1000);
      })
      .catch((e) => alive && setErr(e.message));
    return () => {
      alive = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [name]);
  if (err)
    return (
      <div className="flex items-center gap-2 text-sm text-bad">
        {err}
        <button className="btn-ghost text-xs" onClick={onDone}>Close</button>
      </div>
    );
  if (!st) return <span className="text-xs text-muted">Starting the sign-in…</span>;
  return (
    <div className="w-full rounded-lg border border-you/30 bg-you/[0.06] p-3 text-sm">
      <div className="mb-2 text-muted">
        Open <a className="font-medium text-you underline" href={st.verification_uri} target="_blank" rel="noreferrer">{st.verification_uri} <ExternalLink size={12} className="inline" /></a> and enter this code:
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button className="rounded-md border border-line bg-surface px-3 py-1.5 font-mono text-lg tracking-widest text-ink" title="Copy" onClick={() => copyText(st.user_code)}>
          {st.user_code}
        </button>
        <span className="text-xs text-muted">Waiting for you to confirm… Never share this code.</span>
        <button className="btn-ghost ml-auto text-xs" onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}

function ConnectionRow({ c, reload }: { c: ConnectionInfo; reload: () => void }) {
  const [test, setTest] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [login, setLogin] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      setTest(await api(`/api/admin/connections/${encodeURIComponent(c.name)}/test`, { body: {} }));
    } catch (e: any) {
      setTest({ ok: false, reason: e.message });
    }
    setBusy(false);
  };
  const how =
    c.auth === "api_key" ? `key ${c.api_key || "missing"}` : c.auth === "api_key_env" ? `key from $${c.api_key_env}${c.api_key_env_set ? "" : " (not set)"}` : c.auth === "subscription" ? (c.signed_in ? "signed in" : "not signed in") : "no sign-in";
  const ok = test ? test.ok : c.credentials;
  return (
    <Row
      icon={
        <span className="relative">
          <Tile icon={Plug} color={c.implicit ? "bg-muted" : "bg-you"} />
          <span className="absolute -bottom-0.5 -right-0.5 rounded-full ring-2 ring-surface">
            <Dot ok={ok} warn={!test && c.auth === "subscription"} />
          </span>
        </span>
      }
      label={
        <>
          <span className="font-medium">{c.name}</span>
          <span className="ml-1.5 rounded bg-sunken px-1.5 text-xs text-muted">{c.provider_label}</span>
          {c.implicit && <span className="ml-1 rounded bg-sunken px-1.5 text-xs text-muted">implicit</span>}
        </>
      }
      hint={
        <>
          {[AUTH_LABELS[c.auth] ?? c.auth, how, c.base].filter(Boolean).join(" · ")}
          {!c.credentials && c.credentials_reason && <span className="text-bad"> · {c.credentials_reason}</span>}
          {test && (
            <span className={test.ok ? "text-good" : "text-bad"}>
              {" "}· {test.ok ? `works${test.models?.length ? `: ${test.models.length} models (${test.models.slice(0, 4).join(", ")}${test.models.length > 4 ? ", …" : ""})` : test.verified === false ? " (credentials present)" : ""}` : test.reason}
            </span>
          )}
          {login && (
            <div className="mt-2">
              <DeviceLogin name={c.name} onDone={() => { setLogin(false); reload(); }} />
            </div>
          )}
        </>
      }
    >
      <button className="btn-ghost text-xs" onClick={run} disabled={busy}>
        <FlaskConical size={13} /> {busy ? "Testing…" : "Test"}
      </button>
      {c.auth === "subscription" && !c.implicit && (
        c.signed_in ? (
          <button className="btn-ghost text-xs" onClick={async () => { await api(`/api/admin/connections/${encodeURIComponent(c.name)}/login`, { method: "DELETE" }); reload(); }}>
            <LogOut size={13} /> Sign out
          </button>
        ) : (
          <button className="btn-ghost text-xs" onClick={() => setLogin(true)} disabled={login}>
            <LogIn size={13} /> Sign in
          </button>
        )
      )}
      {!c.implicit && (
        <button
          className="btn-ghost px-2 text-bad"
          aria-label={`Remove ${c.name}`}
          onClick={async () => {
            if (confirm(`Remove the connection ${c.name}? Its key and sign-in are deleted.`)) {
              await api(`/api/admin/connections/${encodeURIComponent(c.name)}`, { method: "DELETE" });
              reload();
            }
          }}
        >
          <Trash2 size={15} />
        </button>
      )}
    </Row>
  );
}

function AddConnection({ providers, names, onAdded }: { providers: ProviderInfo[]; names: string[]; onAdded: (name: string, subscription: boolean) => void }) {
  const [pid, setPid] = useState("anthropic");
  const p = providers.find((x) => x.id === pid);
  const [auth, setAuth] = useState("");
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [env, setEnv] = useState("");
  const [base, setBase] = useState("");
  const [lp, setLp] = useState("");
  useEffect(() => {
    if (!p) return;
    setAuth(p.auth[0]);
    setEnv(p.env);
    setBase("");
    let n = pid.replace(/_/g, "-");
    for (let i = 2; names.includes(n); i++) n = `${pid.replace(/_/g, "-")}-${i}`;
    setName(n);
  }, [pid, providers.length]);
  if (!p) return null;
  const add = async () => {
    try {
      await api("/api/admin/connections", {
        body: { name, provider: pid, auth, api_key: auth === "api_key" ? key : undefined, api_key_env: auth === "api_key_env" ? env : undefined, base_url: base || undefined, litellm_provider: lp || undefined },
      });
      toast(`Added ${name}`);
      setKey("");
      onAdded(name, auth === "subscription");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const ready = name && (auth !== "api_key" || key) && (!p.needs_base_url || base) && (pid !== "litellm" || lp);
  return (
    <Group title="Add a connection" id="setting-connection-add" footer="Keys are stored only in the settings folder (readable by the server's user only) and are never shown again, sent to the browser, or written to results and recordings.">
      <Row label="Provider" hint={p.help}>
        <Select label="Provider" value={pid} onChange={setPid} options={providers.map((x) => ({ value: x.id, label: x.label }))} />
      </Row>
      <Row label="Sign-in" hint={!p.auth.includes("subscription") && p.no_subscription ? `No subscription sign-in: ${p.no_subscription}` : auth === "subscription" ? "Sign in with a device code after adding. Serving study participants from a personal subscription may breach the provider's terms." : undefined}>
        <Select label="Sign-in method" value={auth} onChange={setAuth} options={p.auth.map((a) => ({ value: a, label: AUTH_LABELS[a] ?? a }))} />
      </Row>
      <Row label="Name" hint="Model chains refer to the connection by this name">
        <TextField label="Connection name" value={name} onChange={setName} className="w-56" mono />
      </Row>
      {auth === "api_key" && (
        <Row label="API key">
          <TextField label="API key" type="password" value={key} onChange={setKey} className="w-72" placeholder="paste the key" />
        </Row>
      )}
      {auth === "api_key_env" && (
        <Row label="Environment variable" hint="Set it in the server's environment">
          <TextField label="Environment variable" value={env} onChange={setEnv} className="w-56" mono />
        </Row>
      )}
      {pid === "litellm" && (
        <Row label="litellm provider" hint="e.g. together_ai, xai, fireworks_ai, vertex_ai">
          <TextField label="litellm provider" value={lp} onChange={setLp} className="w-56" mono />
        </Row>
      )}
      {auth !== "subscription" && (
        <Row label="Address" hint={p.needs_base_url ? "Required" : `Optional; default ${p.base_url || "the provider's"}`}>
          <TextField label="Base URL" value={base} onChange={setBase} className="w-72" mono placeholder={p.base_url || "https://…"} />
        </Row>
      )}
      {p.notes && <Row label="Note" hint={p.notes} />}
      <Row label="">
        <button className="btn-primary" disabled={!ready} onClick={add}>
          <Plus size={15} /> {auth === "subscription" ? "Add and sign in" : "Add connection"}
        </button>
      </Row>
    </Group>
  );
}

function ProvidersTable({ providers }: { providers: ProviderInfo[] }) {
  return (
    <Group title="Providers and sign-in methods" id="setting-providers-table" footer="Any provider litellm supports can be used through 'Other litellm provider'.">
      {providers.map((p) => (
        <Row
          key={p.id}
          label={
            <>
              {p.label} <span className="ml-1 font-mono text-xs text-muted">{p.id}</span>
            </>
          }
          hint={
            <>
              {p.notes || p.help}
              {!p.auth.includes("subscription") && p.no_subscription && <span className="block">Subscription: {p.no_subscription}</span>}
              {p.sources.length > 0 && <span className="block opacity-80">Checked against: {p.sources.join("; ")}</span>}
            </>
          }
        >
          <div className="flex flex-wrap justify-end gap-1">
            {["api_key_env", "api_key", "subscription", "none"].filter((a) => p.auth.includes(a)).map((a) => (
              <span key={a} className="rounded bg-sunken px-1.5 py-0.5 text-[0.7rem] text-muted">{a === "api_key_env" ? "key (env)" : a === "api_key" ? "key" : a}</span>
            ))}
          </div>
        </Row>
      ))}
    </Group>
  );
}

export function Connections() {
  const { list, providers, reload } = useConnections();
  const [implicit, setImplicit] = useState(false);
  const [login, setLogin] = useState<string | null>(null);
  const shown = useMemo(() => (list ?? []).filter((c) => implicit || !c.implicit), [list, implicit]);
  if (!list) return <Spinner />;
  return (
    <>
      <Note>Connections live in the shared settings folder for every project and study. Model chains (Models page) pick connections by name.</Note>
      {login && (
        <div className="mb-6">
          <DeviceLogin name={login} onDone={() => { setLogin(null); reload(); }} />
        </div>
      )}
      <Group
        title={`Connections (${shown.length})`}
        id="setting-connections-list"
        actions={
          <label className="flex items-center gap-2 text-xs text-muted">
            Show implicit <Toggle label="Show implicit connections" value={implicit} onChange={setImplicit} />
          </label>
        }
        footer="Implicit connections exist without being added: one per provider, reading the provider's usual environment variable (and the local Ollama server)."
      >
        {shown.length === 0 && <Row label="No connections yet" hint="Add one below, or show the implicit ones." />}
        {shown.map((c) => (
          <ConnectionRow key={c.name} c={c} reload={reload} />
        ))}
      </Group>
      <AddConnection providers={providers} names={list.map((c) => c.name)} onAdded={(n, sub) => { reload(); if (sub) setLogin(n); }} />
      <ProvidersTable providers={providers} />
    </>
  );
}
