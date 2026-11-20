import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, FlaskConical, Plug, Plus, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row, Tile } from "../Row";
import { Select } from "../controls/Select";
import { TextField } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";

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
  offered: boolean;
  not_offered: string;
  harness: string;
}

export interface HarnessInfo {
  id: string;
  label: string;
  completion: boolean;
  assistant_tools: boolean;
  function_calling: boolean;
  purposes: string[] | null;
  auth: string[];
  auth_reason: string;
  upstreams: Record<string, string>;
  default_upstream: string;
  extra: string;
  sources: string[];
  status: { found: boolean; path?: string; version?: string; error?: string };
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
  label?: string;
  auth_methods: string[];
  upstream?: string;
  disabled?: string;
  harness?: { id: string; status: HarnessInfo["status"]; assistant_tools: boolean; purposes: string[] | null; upstream: string; default_model: string; auth_reason: string };
}

export const AUTH_LABELS: Record<string, string> = {
  api_key: "API key (stored here)",
  api_key_env: "API key in an environment variable",
  subscription: "Subscription sign-in (not offered)",
  none: "No sign-in",
};

export const CONNECTION_ENTRIES = [
  { id: "connections-list", label: "Connections", hint: "Status, test, remove", keywords: "provider api key harness" },
  { id: "connection-add", label: "Add a connection", hint: "Anthropic, OpenAI, Ollama, a harness, …", keywords: "new provider key ollama harness claude code codex pi" },
  { id: "harnesses", label: "Harnesses", hint: "Claude Code, Codex and pi: installed, sign-in, purposes", keywords: "harness claude code codex pi agent sdk cli" },
  { id: "providers-table", label: "Providers and sign-in methods", hint: "Which provider supports which sign-in, and which are not offered", keywords: "auth oauth subscription copilot chatgpt" },
];

export function useConnections() {
  const [list, setList] = useState<ConnectionInfo[] | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [harnesses, setHarnesses] = useState<HarnessInfo[]>([]);
  const load = () =>
    Promise.all([api("/api/admin/connections"), api("/api/admin/providers")])
      .then(([c, p]) => {
        setList(c.connections);
        setProviders(p.providers);
        setHarnesses(p.harnesses ?? []);
      })
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  return { list, providers, harnesses, reload: load };
}

function Dot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return <span aria-hidden className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${ok ? "bg-good" : warn ? "bg-warn" : "bg-bad"}`} />;
}

function ConnectionRow({ c, reload }: { c: ConnectionInfo; reload: () => void }) {
  const [test, setTest] = useState<any>(null);
  const [busy, setBusy] = useState(false);
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
    c.disabled ? "disabled" : c.auth === "api_key" ? `key ${c.api_key || "missing"}` : c.auth === "api_key_env" ? `key from $${c.api_key_env}${c.api_key_env_set ? "" : " (not set)"}` : "no sign-in";
  const h = c.harness;
  const ok = test ? test.ok : c.credentials;
  return (
    <Row
      icon={
        <span className="relative">
          <Tile icon={Plug} color={c.implicit ? "bg-muted" : "bg-you"} />
          <span className="absolute -bottom-0.5 -right-0.5 rounded-full ring-2 ring-surface">
            <Dot ok={ok} />
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
          {[AUTH_LABELS[c.auth] ?? c.auth, how, h ? `calls ${h.upstream}` : "", h ? (h.status.found ? h.status.version : "not installed") : "", h ? (h.assistant_tools ? "completion + Assistant functions" : "completion only") : "", h?.purposes ? `only: ${h.purposes.join(", ")}` : "", c.base].filter(Boolean).join(" · ")}
          {!c.credentials && c.credentials_reason && <span className="text-bad"> · {c.credentials_reason}</span>}
          {test && (
            <span className={test.ok ? "text-good" : "text-bad"}>
              {" "}· {test.ok ? test.reply !== undefined ? `works: ${test.model} replied "${test.reply}"` : `works${test.models?.length ? `: ${test.models.length} models (${test.models.slice(0, 4).join(", ")}${test.models.length > 4 ? ", …" : ""})` : test.verified === false ? " (credentials present)" : ""}` : test.reason}
            </span>
          )}
        </>
      }
    >
      <button className="btn-ghost text-xs" onClick={run} disabled={busy}>
        <FlaskConical size={13} /> {busy ? "Testing…" : "Test"}
      </button>
      {!c.implicit && (
        <button
          className="btn-ghost px-2 text-bad"
          aria-label={`Remove ${c.name}`}
          onClick={async () => {
            if (confirm(`Remove the connection ${c.name}? Its key and sign-in are deleted.`)) {
              await api(`/api/admin/connections/${encodeURIComponent(c.name)}`, { method: "DELETE" }).then(reload).catch((e) => toast(e.message, "error"));
            }
          }}
        >
          <Trash2 size={15} />
        </button>
      )}
    </Row>
  );
}

function AddConnection({ providers, harnesses, names, onAdded }: { providers: ProviderInfo[]; harnesses: HarnessInfo[]; names: string[]; onAdded: (name: string) => void }) {
  const offered = providers.filter((x) => x.offered);
  const [pid, setPid] = useState("anthropic");
  const p = offered.find((x) => x.id === pid);
  const h = harnesses.find((x) => x.id === p?.harness);
  const [auth, setAuth] = useState("");
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [env, setEnv] = useState("");
  const [base, setBase] = useState("");
  const [lp, setLp] = useState("");
  const [up, setUp] = useState("");
  useEffect(() => {
    if (!p) return;
    setAuth(p.auth[0]);
    setEnv(p.env);
    setBase("");
    setUp(h?.default_upstream ?? "");
    let n = pid.replace(/_/g, "-");
    for (let i = 2; names.includes(n); i++) n = `${pid.replace(/_/g, "-")}-${i}`;
    setName(n);
  }, [pid, providers.length, harnesses.length]);
  useEffect(() => {
    if (!h) return;
    if (up === "ollama") setAuth("none");
    else if (auth === "none") setAuth("api_key");
  }, [up]);
  if (!p) return null;
  const authOptions = h ? (up === "ollama" ? ["none"] : ["api_key", "api_key_env"]) : p.auth;
  const add = async () => {
    try {
      await api("/api/admin/connections", {
        body: { name, provider: pid, auth, api_key: auth === "api_key" ? key : undefined, api_key_env: auth === "api_key_env" ? env : undefined, base_url: base || undefined, litellm_provider: lp || undefined, upstream: h ? up : undefined },
      });
      toast(`Added ${name}`);
      setKey("");
      onAdded(name);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const ready = name && (auth !== "api_key" || key) && (!p.needs_base_url || base) && (pid !== "litellm" || lp);
  const local = h && up === "ollama";
  return (
    <Group title="Add a connection" id="setting-connection-add" footer="Keys are stored only in the settings folder (readable by the server's user only) and are never shown again, sent to the browser, or written to results and recordings.">
      <Row label="Provider" hint={p.help}>
        <Select label="Provider" value={pid} onChange={setPid} options={offered.map((x) => ({ value: x.id, label: x.harness ? `Harness: ${x.label}` : x.label }))} />
      </Row>
      {h && (
        <Row label="Calls" hint={`The model provider ${h.label} calls. ${h.auth_reason}`}>
          <Select label="Upstream provider" value={up} onChange={setUp} options={Object.entries(h.upstreams).map(([v, l]) => ({ value: v, label: l }))} />
        </Row>
      )}
      <Row label="Sign-in" hint={h ? (local ? "A local server needs no key." : "API key only.") : p.no_subscription ? `No subscription sign-in: ${p.no_subscription}` : undefined}>
        <Select label="Sign-in method" value={auth} onChange={setAuth} options={authOptions.map((a) => ({ value: a, label: AUTH_LABELS[a] ?? a }))} />
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
      {(!h || local) && (
        <Row label="Address" hint={p.needs_base_url ? "Required" : `Optional; default ${local ? "http://localhost:11434" : p.base_url || "the provider's"}`}>
          <TextField label="Base URL" value={base} onChange={setBase} className="w-72" mono placeholder={local ? "http://localhost:11434" : p.base_url || "https://…"} />
        </Row>
      )}
      {p.notes && <Row label="Note" hint={p.notes} />}
      <Row label="">
        <button className="btn-primary" disabled={!ready} onClick={add}>
          <Plus size={15} /> Add connection
        </button>
      </Row>
    </Group>
  );
}

function Harnesses({ harnesses }: { harnesses: HarnessInfo[] }) {
  if (!harnesses.length) return null;
  return (
    <Group
      title="Harnesses"
      id="setting-harnesses"
      footer="A harness connection calls the model through an installed agent harness instead of the API. It signs in with an API key only, runs with its own empty configuration and working folder, and has every built-in tool turned off: only HANI2's own functions are offered."
    >
      {harnesses.map((h) => (
        <Row
          key={h.id}
          icon={<Tile icon={Bot} color={h.status.found ? "bg-you" : "bg-muted"} />}
          label={
            <>
              {h.label} <span className="ml-1 font-mono text-xs text-muted">{h.id}</span>
            </>
          }
          hint={
            <>
              <span className={h.status.found ? "text-good" : "text-bad"}>{h.status.found ? `Found: ${h.status.version || h.status.path}` : `Not available: ${h.status.error || "not installed"}`}</span>
              <span className="block">Sign-in: API key only. {h.auth_reason}</span>
              <span className="block">Calls: {Object.values(h.upstreams).join(", ")}</span>
              <span className="block">Purposes: {h.purposes ? `${h.purposes.join(", ")} only (never participant-facing)` : "every purpose"}{h.function_calling && !h.assistant_tools ? "; can call functions, but not for the Assistant" : ""}</span>
              {h.sources.length > 0 && <span className="block opacity-80">Checked against: {h.sources.join("; ")}</span>}
            </>
          }
        >
          <div className="flex flex-wrap justify-end gap-1">
            <span className="rounded bg-sunken px-1.5 py-0.5 text-[0.7rem] text-muted">completion</span>
            <span className={`rounded px-1.5 py-0.5 text-[0.7rem] ${h.assistant_tools ? "bg-sunken text-muted" : "bg-bad/10 text-bad"}`}>{h.assistant_tools ? "Assistant functions" : "no Assistant functions"}</span>
          </div>
        </Row>
      ))}
    </Group>
  );
}

function ProvidersTable({ providers }: { providers: ProviderInfo[] }) {
  return (
    <Group title="Providers and sign-in methods" id="setting-providers-table" footer="Any provider litellm supports can be used through 'Other litellm provider'. Subscription sign-ins (ChatGPT plans, GitHub Copilot) are not offered: the providers' terms do not clearly allow a third-party application to use them to serve other people.">
      {providers.filter((p) => !p.harness).map((p) => (
        <Row
          key={p.id}
          label={
            <>
              {p.label} <span className="ml-1 font-mono text-xs text-muted">{p.id}</span>
            </>
          }
          hint={
            <>
              {p.offered ? p.notes || p.help : p.not_offered}
              {p.offered && p.no_subscription && <span className="block">Subscription: {p.no_subscription}</span>}
              {p.sources.length > 0 && <span className="block opacity-80">Checked against: {p.sources.join("; ")}</span>}
            </>
          }
        >
          <div className="flex flex-wrap justify-end gap-1">
            {!p.offered && <span className="rounded bg-bad/10 px-1.5 py-0.5 text-[0.7rem] text-bad">not offered</span>}
            {["api_key_env", "api_key", "none"].filter((a) => p.auth.includes(a)).map((a) => (
              <span key={a} className="rounded bg-sunken px-1.5 py-0.5 text-[0.7rem] text-muted">{a === "api_key_env" ? "key (env)" : a === "api_key" ? "key" : a}</span>
            ))}
          </div>
        </Row>
      ))}
    </Group>
  );
}

export function Connections() {
  const { list, providers, harnesses, reload } = useConnections();
  const [implicit, setImplicit] = useState(false);
  const shown = useMemo(() => (list ?? []).filter((c) => implicit || !c.implicit), [list, implicit]);
  if (!list) return <Spinner />;
  return (
    <>
      <Note>Connections live in the shared settings folder for every project and study. Model chains (Models page) pick connections by name.</Note>
      <Group
        title={`Connections (${shown.length})`}
        id="setting-connections-list"
        actions={
          <label className="flex items-center gap-2 text-xs text-muted">
            Show implicit <Toggle label="Show implicit connections" value={implicit} onChange={setImplicit} />
          </label>
        }
        footer="Implicit connections exist without being added: one per provider, reading the provider's usual environment variable (and the local Ollama server). Harness connections are never implicit."
      >
        {shown.length === 0 && <Row label="No connections yet" hint="Add one below, or show the implicit ones." />}
        {shown.map((c) => (
          <ConnectionRow key={c.name} c={c} reload={reload} />
        ))}
      </Group>
      <AddConnection providers={providers} harnesses={harnesses} names={list.map((c) => c.name)} onAdded={() => reload()} />
      <Harnesses harnesses={harnesses} />
      <ProvidersTable providers={providers} />
    </>
  );
}
