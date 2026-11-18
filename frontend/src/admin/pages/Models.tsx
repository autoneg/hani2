import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Copy, FlaskConical, ListOrdered, Plus, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row, Tile } from "../Row";
import { LayerPicker, lq, useLayer } from "../layer";
import { Select } from "../controls/Select";
import { TextField } from "../controls/TextField";
import { ErrorNote, Note, SaveBar, Spinner } from "../schema";
import { toast } from "../toast";
import { useConnections } from "./Connections";

export const MODEL_ENTRIES = [
  { id: "models-test", label: "Test the chains", hint: "Which entry each purpose uses now", keywords: "resolve available" },
  { id: "models-default", label: "Default model chain", hint: "Tried in order for every purpose", keywords: "provider model list fallback order" },
  { id: "models-assistant", label: "Assistant model chain", keywords: "assistant autopilot" },
  { id: "models-opponent", label: "LLM opponent model chain", keywords: "opponent negotiator" },
  { id: "models-tools", label: "Tools model chain", keywords: "tool llm" },
  { id: "models-text", label: "Offer extraction and message writing chain", keywords: "text extraction generation" },
  { id: "models-judge", label: "Evaluation judge model chain", keywords: "judge evaluation" },
];

interface Entry {
  connection?: string;
  provider?: string;
  model: string;
  params?: Record<string, any>;
  label?: string;
}
type Chains = Record<string, Entry[]>;

const ORDER = ["default", "assistant", "opponent", "tools", "text", "judge"];

/** "a:b" (connection or provider : model) → an entry. */
function toEntry(x: any, names: string[]): Entry {
  if (typeof x !== "string") return { ...x };
  const i = x.indexOf(":");
  const head = x.slice(0, i).trim();
  const model = x.slice(i + 1).trim();
  return names.includes(head) ? { connection: head, model } : { provider: head, model };
}

const paramsText = (p?: Record<string, any>) => Object.entries(p ?? {}).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
function parseParams(t: string): Record<string, any> {
  const out: Record<string, any> = {};
  t.split(",").map((s) => s.trim()).filter(Boolean).forEach((kv) => {
    const [k, ...rest] = kv.split("=");
    const raw = rest.join("=").trim();
    if (!k.trim()) return;
    try {
      out[k.trim()] = JSON.parse(raw);
    } catch {
      out[k.trim()] = raw;
    }
  });
  return out;
}

const SOURCE_LABEL = (s: string) =>
  s === "legacy" ? "the old single-model settings" : s === "start" ? "the start-time list (--models / HANI2_MODELS)" : s === "settings" ? "the settings folder" : s.startsWith("project:") ? `project ${s.slice(8)}` : s.startsWith("study:") ? `study ${s.slice(6)}` : s || "nowhere";

function EntryRow({ e, i, n, conns, set, move, dup, del }: { e: Entry; i: number; n: number; conns: { value: string; label: string }[]; set: (e: Entry) => void; move: (d: number) => void; dup: () => void; del: () => void }) {
  const [res, setRes] = useState<any>(null);
  const target = e.connection ? e.connection : e.provider ? `provider:${e.provider}` : "";
  const test = async () => {
    try {
      setRes(await api("/api/admin/models/test-entry", { body: { entry: e } }));
    } catch (err: any) {
      setRes({ status: "none", error: err.message });
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2.5" data-setting={`entry-${i}`}>
      <span className="w-6 shrink-0 text-right font-mono text-xs text-muted">{i + 1}.</span>
      <Select
        label={`Entry ${i + 1} connection`}
        value={target}
        onChange={(v) => set(v.startsWith("provider:") ? { ...e, connection: undefined, provider: v.slice(9) } : { ...e, connection: v, provider: undefined })}
        options={conns}
        className="w-44 [&>select]:w-full"
      />
      <TextField label={`Entry ${i + 1} model`} value={e.model} onChange={(v) => set({ ...e, model: v })} className="w-52" mono placeholder="model id" />
      <TextField label={`Entry ${i + 1} parameters`} value={paramsText(e.params)} onChange={(v) => set({ ...e, params: parseParams(v) })} commit="blur" className="w-56" mono placeholder="temperature=0.2, max_tokens=800" />
      <TextField label={`Entry ${i + 1} label`} value={e.label ?? ""} onChange={(v) => set({ ...e, label: v || undefined })} className="w-28" placeholder="label" />
      <span className="ml-auto flex items-center gap-0.5">
        {res && (
          <span className={`mr-1 max-w-[16rem] truncate text-xs ${res.status === "none" ? "text-bad" : "text-good"}`} title={res.error || res.skipped?.map((s: any) => s.reason).join("; ")}>
            {res.status === "none" ? res.error || res.skipped?.[0]?.reason || "not available" : res.status === "ok" ? "available" : "credentials present"}
          </span>
        )}
        <button className="btn-ghost px-1.5" aria-label="Test this entry" title="Test this entry" onClick={test}><FlaskConical size={14} /></button>
        <button className="btn-ghost px-1.5" aria-label="Move up" title="Move up" disabled={i === 0} onClick={() => move(-1)}><ArrowUp size={14} /></button>
        <button className="btn-ghost px-1.5" aria-label="Move down" title="Move down" disabled={i === n - 1} onClick={() => move(1)}><ArrowDown size={14} /></button>
        <button className="btn-ghost px-1.5" aria-label="Duplicate" title="Duplicate (same model, other parameters)" onClick={dup}><Copy size={14} /></button>
        <button className="btn-ghost px-1.5 text-bad" aria-label="Remove entry" title="Remove entry" onClick={del}><Trash2 size={14} /></button>
      </span>
    </div>
  );
}

export function Models() {
  const { layer } = useLayer();
  const { list, providers } = useConnections();
  const [data, setData] = useState<any>(null);
  const [draft, setDraft] = useState<Chains>({});
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<any>(null);
  const names = (list ?? []).map((c) => c.name);
  const load = useCallback(() => {
    setError(null);
    return api(`/api/admin/models${lq(layer)}`)
      .then((d) => {
        setData(d);
        const own: Chains = {};
        const raw = Array.isArray(d.own) ? { default: d.own } : d.own ?? {};
        Object.entries(raw).forEach(([k, v]: any) => (own[k] = (typeof v === "string" ? v.split(",") : v).map((x: any) => toEntry(x, names))));
        setDraft(own);
        setDirty(false);
        setResolved(null);
      })
      .catch((e) => setError(e.message));
  }, [layer.id, names.join(",")]);
  useEffect(() => {
    if (list) load();
  }, [load, list]);
  const connOpts = [
    ...(list ?? []).map((c) => ({ value: c.name, label: `${c.name}${c.implicit ? " (implicit)" : ""}${c.credentials ? "" : " — not ready"}` })),
    ...providers.map((p) => ({ value: `provider:${p.id}`, label: `first ${p.label} connection` })),
  ];
  const change = (p: string, entries: Entry[] | null) => {
    setDraft((d) => {
      const n = { ...d };
      if (entries === null) delete n[p];
      else n[p] = entries;
      return n;
    });
    setDirty(true);
  };
  const save = async () => {
    try {
      await api(`/api/admin/models${lq(layer)}`, { method: "PUT", body: draft });
      toast(`Saved to ${layer.label}. New sessions use it.`);
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const testAll = async () => {
    try {
      setResolved(await api(`/api/admin/models/resolve${lq(layer)}`, { body: dirty ? { chains: draft } : {} }));
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  if (error) return <><LayerPicker /><ErrorNote>{error}</ErrorNote></>;
  if (!data || !list) return <><LayerPicker /><Spinner /></>;
  return (
    <>
      <LayerPicker note="A study's chain beats its project's, which beats the start-time list (--models), which beats the settings folder's, which beats the old single-model settings." />
      {data.start && <Note>This server was started with the model list <code className="font-mono">{data.start}</code>: it replaces the settings folder's chains, but a project's or study's own chain still wins.</Note>}
      <Group
        title="Test the chains"
        id="setting-models-test"
        actions={<button className="btn-secondary text-xs" onClick={testAll}><FlaskConical size={13} /> {dirty ? "Test unsaved chains" : "Test chains"}</button>}
        footer="Each purpose uses the first available entry of its chain. A session chooses once and keeps its choice; if a call fails hard (connection, sign-in, model not found, rate limit) it moves on to the next entry, and that is recorded."
      >
        {!resolved && <Row label="Which entry each purpose uses now" hint="Checks every provider (short time-out); results are cached for a few minutes." />}
        {resolved &&
          Object.entries(resolved.purposes).map(([p, r]: any) => (
            <Row
              key={p}
              icon={<span className={`mt-1.5 inline-block h-2.5 w-2.5 rounded-full ${r.status === "none" ? "bg-bad" : r.status === "ok" ? "bg-good" : "bg-warn"}`} />}
              label={data.purposes[p] ?? p}
              hint={
                <>
                  {r.status === "none" ? <span className="text-bad">{r.error}</span> : <>#{r.position} of {SOURCE_LABEL(r.source)}{r.status === "unverified" ? " (credentials present, not checked)" : ""}</>}
                  {r.skipped?.map((s: any) => (
                    <span key={s.position} className="block">skipped #{s.position} {s.entry}: {s.reason}</span>
                  ))}
                </>
              }
            >
              <span className="font-mono text-xs text-ink">{r.connection ? `${r.connection}:${r.model}` : "—"}</span>
            </Row>
          ))}
      </Group>
      {ORDER.map((p) => {
        const own = draft[p];
        const eff = data.effective[p];
        const inh = data.inherited[p];
        return (
          <Group
            key={p}
            id={`setting-models-${p}`}
            title={data.purposes[p] ?? p}
            actions={
              own ? (
                <button className="btn-ghost text-xs text-bad" onClick={() => change(p, null)}>{layer.kind === "settings" ? "Remove this chain" : "Use the inherited chain"}</button>
              ) : (
                <button className="btn-ghost text-xs" onClick={() => change(p, (p === "default" && inh?.source !== "legacy" ? inh?.entries ?? [] : []).map((e: any) => ({ ...e, base: undefined })) as Entry[])}>
                  <Plus size={13} /> Set a chain here
                </button>
              )
            }
            footer={p === "default" ? "Every purpose without its own chain uses this one." : undefined}
          >
            {own ? (
              <>
                {own.length === 0 && <Row label="No entries yet" hint="Add the models to try, in order." />}
                {own.map((e, i) => (
                  <EntryRow
                    key={i}
                    e={e}
                    i={i}
                    n={own.length}
                    conns={connOpts}
                    set={(x) => change(p, own.map((y, j) => (j === i ? x : y)))}
                    move={(d) => {
                      const a = [...own];
                      [a[i], a[i + d]] = [a[i + d], a[i]];
                      change(p, a);
                    }}
                    dup={() => change(p, [...own.slice(0, i + 1), JSON.parse(JSON.stringify(e)), ...own.slice(i + 1)])}
                    del={() => change(p, own.filter((_, j) => j !== i))}
                  />
                ))}
                <div className="px-4 py-2">
                  <button className="btn-ghost text-xs" onClick={() => change(p, [...own, { connection: list[0]?.name, model: "" }])}>
                    <Plus size={13} /> Add entry
                  </button>
                </div>
              </>
            ) : (
              <Row
                icon={<Tile icon={ListOrdered} color="bg-muted" />}
                label={eff?.entries?.length ? `In effect: from ${SOURCE_LABEL(eff.source)}` : "No chain"}
                hint={(eff?.entries ?? []).map((e: any, i: number) => `${i + 1}. ${e.connection ?? e.provider}:${e.model}${e.params && Object.keys(e.params).length ? ` (${paramsText(e.params)})` : ""}`).join("   ") || (p === "default" ? "Each purpose uses its own chain or the old settings." : "Uses the default chain.")}
              />
            )}
          </Group>
        );
      })}
      <SaveBar dirty={dirty} save={save} discard={load} where={layer.label} />
    </>
  );
}
