import { useEffect, useMemo, useState } from "react";
import { EyeOff, Layers, Save, Undo2, Wrench, X } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { Disclosure } from "../Disclosure";
import { useNav } from "../Nav";
import { lq, type Layer } from "../layer";
import { Select } from "../controls/Select";
import { Stepper } from "../controls/Stepper";
import { Toggle } from "../controls/Toggle";
import { Spinner } from "../schema";
import { toast } from "../toast";
import { SOURCE_LABEL } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

const VIEW_LABEL: Record<string, [string, string]> = {
  full: ["Full", "The full view: every pane"],
  simple: ["Simple", "The simple view: one tool column"],
  focus: ["Focus", "The focus view: the negotiation only"],
};
const PANE_LABEL: Record<string, string> = { upper: "Upper", lower: "Lower", side: "Side" };
const TIMING: Record<string, string> = { always: "when the page opens", load: "when the scenario is loaded", start: "when the negotiation starts", end: "when the negotiation ends", agent: "only when the Assistant adds it" };
type Field = "pane" | "visible" | "order";
type One = Partial<Record<Field, any>>;
type Placement = Record<string, One>;

/** ``GET /api/admin/library/tools/placement``. */
interface PlacementData {
  layer: string;
  views: string[];
  panes: string[];
  tools: Record<string, { effective: Placement; here: Record<string, any> | null }>;
}

const loadPlacement = (layer: Layer) => api<PlacementData>(`/api/admin/library/tools/placement${lq(layer)}`);

/** A layer's own entry as one mapping per view (keys for every view are spread into each view). */
function perView(here: Record<string, any> | null, views: string[]): Placement {
  const flat: One = {};
  for (const k of ["pane", "visible", "order"] as Field[]) if (here && k in here) flat[k] = here[k];
  return Object.fromEntries(views.map((v) => [v, { ...flat, ...(here?.[v] ?? {}) }]));
}

const short = (p: One | undefined) => (!p ? "—" : p.visible === false ? "hidden" : `${PANE_LABEL[p.pane] ?? p.pane} · ${p.order}`);

/** Where one tool goes in each view, at the chosen layer. */
export function PlacementEditor({ tool, layer, onSaved }: { tool: string; layer: Layer; onSaved?: () => void }) {
  const [d, setD] = useState<PlacementData | null>(null);
  const [draft, setDraft] = useState<Placement>({});
  const [dirty, setDirty] = useState(false);
  const load = () =>
    loadPlacement(layer).then((r) => {
      setD(r);
      setDraft(perView(r.tools[tool]?.here ?? null, r.views));
      setDirty(false);
    });
  useEffect(() => {
    load().catch((e) => toast(e.message, "error"));
  }, [tool, layer.id]);
  if (!d) return <Spinner />;
  const t = d.tools[tool];
  if (!t) return <InfoRow label="Tool" value={`${tool} is not available at ${layer.label}`} />;
  const set = (v: string, k: Field, x: any) => {
    setDraft((cur) => {
      const n = { ...cur, [v]: { ...cur[v] } };
      if (x === undefined) delete n[v][k];
      else n[v][k] = x;
      return n;
    });
    setDirty(true);
  };
  const body = () => {
    const out: Record<string, One> = {};
    for (const v of d.views) if (Object.keys(draft[v] ?? {}).length) out[v] = draft[v];
    return Object.keys(out).length ? out : null;
  };
  const save = async (value: Record<string, One> | null) => {
    try {
      const r = await api<PlacementData>(`/api/admin/library/tools/placement${lq(layer)}`, { method: "PUT", body: { [tool]: value } });
      setD(r);
      setDraft(perView(r.tools[tool]?.here ?? null, r.views));
      setDirty(false);
      toast(value ? `Placement of ${tool} saved to ${layer.label}` : `${tool} uses the inherited placement`);
      onSaved?.();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const has = (v: string, k: Field) => draft[v] && k in draft[v];
  const val = (v: string, k: Field) => (has(v, k) ? draft[v][k] : t.effective[v]?.[k]);
  return (
    <>
      <Group title={tool} footer={`Values marked “set here” are this layer's (tools.yaml of ${layer.label}); the others are inherited. The order sorts the tools of a pane, smaller first.`}>
        <InfoRow label="In effect" value={d.views.map((v) => `${VIEW_LABEL[v]?.[0] ?? v}: ${short(t.effective[v])}`).join(" · ")} />
      </Group>
      {d.views.map((v) => (
        <Group key={v} title={`${VIEW_LABEL[v]?.[0] ?? v} view`} footer={VIEW_LABEL[v]?.[1]} id={`setting-placement-${v}`}>
          <Row label="Shown" hint={val(v, "visible") ? "The tool is in this view" : "Hidden in this view"} overridden={has(v, "visible")} onReset={() => set(v, "visible", undefined)}>
            <Toggle label={`Shown in the ${v} view`} value={!!val(v, "visible")} onChange={(x) => set(v, "visible", x)} />
          </Row>
          <Row label="Pane" overridden={has(v, "pane")} onReset={() => set(v, "pane", undefined)}>
            <Select label={`Pane in the ${v} view`} value={val(v, "pane") ?? ""} onChange={(x) => set(v, "pane", x)} options={d.panes.map((p) => ({ value: p, label: PANE_LABEL[p] ?? p }))} />
          </Row>
          <Row label="Order" hint="Position in the pane" overridden={has(v, "order")} onReset={() => set(v, "order", undefined)}>
            <Stepper label={`Order in the ${v} view`} value={val(v, "order") ?? null} step={1} onChange={(x) => set(v, "order", x ?? undefined)} />
          </Row>
        </Group>
      ))}
      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
        <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved · saves to ${layer.label}` : t.here ? `Set in ${layer.label}` : `Inherited at ${layer.label}`}</span>
        {t.here && (
          <button className="btn-secondary" onClick={() => save(null)}>
            <Undo2 size={14} /> Inherit
          </button>
        )}
        <button className="btn-primary" disabled={!dirty} onClick={() => save(body())}>
          <Save size={15} /> Save
        </button>
      </div>
    </>
  );
}

/** Every tool in every view at a glance; a row opens its editor. */
function PlacementOverview({ layer, items, reload }: { layer: Layer; items: ExItem[]; reload: () => void }) {
  const [d, setD] = useState<PlacementData | null>(null);
  const nav = useNav();
  const load = () => loadPlacement(layer).then(setD).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, [layer.id]);
  if (!d) return null;
  const open = (tool: string) => nav.push({ title: `${tool}: placement`, render: () => <PlacementEditor tool={tool} layer={layer} onSaved={() => (load(), reload())} /> });
  const names = Object.keys(d.tools);
  const nHere = names.filter((n) => d.tools[n].here).length;
  return (
    <Group title="Placement in each view" id="setting-tool-placement" footer={`${nHere ? `${nHere} tool${nHere === 1 ? "" : "s"} placed at ${layer.label} (bold)` : `Nothing placed at ${layer.label}: every tool keeps its inherited place`}. Sessions move the tools when the view changes; a participant's own arrangement is kept per view.`}>
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="px-4 py-2 font-medium">Tool</th>
              {d.views.map((v) => <th key={v} className="px-3 py-2 font-medium">{VIEW_LABEL[v]?.[0] ?? v}</th>)}
            </tr>
          </thead>
          <tbody>
            {names.map((n) => {
              const t = d.tools[n];
              const here = perView(t.here, d.views);
              return (
                <tr key={n} className="cursor-pointer border-t border-line/70 hover:bg-sunken/60" onClick={() => open(n)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && open(n)} aria-label={`Placement of ${n}`}>
                  <td className="px-4 py-1.5">
                    <span className={t.here ? "font-semibold" : ""}>{n}</span>
                    {items.find((i) => i.id === n)?.raw.offered === false && <span className="ml-1.5 text-[0.68rem] text-muted">not offered</span>}
                  </td>
                  {d.views.map((v) => {
                    const p = t.effective[v];
                    const mine = Object.keys(here[v] ?? {}).length > 0;
                    return (
                      <td key={v} className={`whitespace-nowrap px-3 py-1.5 ${p?.visible === false ? "text-muted" : ""} ${mine ? "font-semibold text-you" : ""}`}>
                        {p?.visible === false && <EyeOff size={12} className="mr-1 inline" />}
                        {short(p)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Group>
  );
}

/** Which tools and tool groups sessions are offered at the layer (``tools.yaml`` → ``offer``). */
function Offer({ layer, groups, items, reload }: { layer: Layer; groups: ExGroup[]; items: ExItem[]; reload: () => void }) {
  const [d, setD] = useState<any>(null);
  const [sel, setSel] = useState<string[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [q, setQ] = useState("");
  const load = () =>
    api(`/api/admin/library/tools/offer${lq(layer)}`)
      .then((r) => (setD(r), setSel(r.here), setDirty(false)))
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, [layer.id]);
  const opts = useMemo(() => {
    const gs = groups.filter((g) => g.active !== false).map((g) => ({ value: `@${g.key}`, hint: `${g.expanded?.length ?? 0} tools · ${g.description || g.origin || ""}`, group: true }));
    const ts = items.map((i) => ({ value: i.id, hint: i.raw.description, group: false }));
    return [...gs, ...ts].filter((c) => !q || `${c.value} ${c.hint ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  }, [groups, items, q]);
  if (!d) return null;
  const choose = sel !== null;
  const toggle = (v: string) => {
    const cur = sel ?? [];
    setSel(cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
    setDirty(true);
  };
  const save = async () => {
    try {
      const r = await api(`/api/admin/library/tools/offer${lq(layer)}`, { method: "PUT", body: { offer: sel } });
      setD(r);
      setSel(r.here);
      setDirty(false);
      toast(sel === null ? `${layer.label} inherits the tools offered` : `Tools offered saved to ${layer.label}`);
      reload();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <Group title="Tools offered to sessions" id="setting-tool-offer" footer={<>The tools and tool groups sessions of this layer get (<code>tools.yaml</code> → <code>offer</code>). Tool settings (env.json) can still switch a tool off.</>}>
      <Row label="Offer" hint={choose ? "Chosen at this layer" : d.effective ? `Inherited: ${d.effective.join(", ")}` : "Inherited: every tool"}>
        <Select label="Tools offered" value={choose ? "choose" : "inherit"} onChange={(v) => (setSel(v === "choose" ? (d.here ?? d.effective ?? d.tools) : null), setDirty(true))} options={[{ value: "inherit", label: "Inherit" }, { value: "choose", label: "Choose here" }]} />
      </Row>
      {choose && (
        <>
          <Row label="Chosen" wide>
            <div className="flex flex-wrap gap-1.5">
              {!sel!.length && <span className="text-sm text-muted">Nothing: no tool is offered</span>}
              {sel!.map((s) => (
                <span key={s} className="chip py-1 text-[0.8rem]">
                  {s.startsWith("@") && <Layers size={12} className="text-you" />}
                  {s}
                  <button aria-label={`Remove ${s}`} className="text-muted hover:text-bad" onClick={() => toggle(s)}>
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          </Row>
          <Row label="Add tools or tool groups" wide>
            <input aria-label="Filter tools" type="search" className="mb-2 w-full rounded-md border border-line bg-surface px-2 py-1 text-sm focus:border-you focus:outline-none" placeholder="Search tools and groups" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="scroll-thin max-h-56 overflow-y-auto rounded-lg border border-line/70" role="listbox" aria-multiselectable aria-label="Tools to offer">
              {opts.map((c) => (
                <label key={c.value} className="flex cursor-pointer items-start gap-2 border-b border-line/50 px-3 py-1.5 text-sm last:border-0 hover:bg-sunken/60">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--you))]" checked={sel!.includes(c.value)} onChange={() => toggle(c.value)} />
                  <span className="min-w-0">
                    <span className={c.group ? "font-medium" : ""}>{c.value}</span>
                    {c.hint && <span className="block truncate text-xs text-muted">{c.hint}</span>}
                  </span>
                </label>
              ))}
            </div>
          </Row>
        </>
      )}
      <Row label="Offered now" hint={`${d.tools.length} of ${items.length} tools`} wide>
        <div className="flex flex-wrap gap-1">{d.tools.map((t: string) => <span key={t} className="chip">{t}</span>)}</div>
      </Row>
      {dirty && (
        <Row label="">
          <span className="text-xs text-muted">Unsaved</span>
          <button className="btn-primary" onClick={save}>
            <Save size={15} /> Save
          </button>
        </Row>
      )}
    </Group>
  );
}

/** A tool's own details: pane, timing, who gets it, its place in each view. */
function ToolDetails({ item, layer }: { item: ExItem; layer: Layer }) {
  const t = item.raw;
  const nav = useNav();
  return (
    <>
      <Group title="How it appears">
        <InfoRow label="Default pane" value={PANE_LABEL[t.pane] ?? t.pane} />
        <InfoRow label="Appears" value={TIMING[t.timing] ?? t.timing} />
        <InfoRow label="Who gets it" value={t.admin_only ? "admins only" : t.guest ? "everyone, guests too" : "participants with an account"} />
        <InfoRow label="On by default" value={t.enabled ? "yes" : "no (participants switch it on)"} />
        <InfoRow label="Offered here" value={t.offered ? "yes" : "no"} hint="Tools offered to sessions, on the Tools page" />
        <InfoRow label="Built-in groups" value={(t.tool_groups ?? []).join(", ") || "none"} />
        <InfoRow label="Origin" value={t.origin || SOURCE_LABEL[t.source]} />
      </Group>
      <Group title="Placement in each view">
        {Object.entries(t.placement ?? {}).map(([v, p]: any) => <InfoRow key={v} label={VIEW_LABEL[v]?.[0] ?? v} value={short(p)} />)}
        <Disclosure id="tool-placement-edit" icon={<Wrench size={16} className="text-you" />} label="Change the placement" hint={`Saved to ${layer.label}`} title={`${t.name}: placement`} onClick={() => nav.push({ title: `${t.name}: placement`, render: () => <PlacementEditor tool={t.name} layer={layer} /> })} />
      </Group>
    </>
  );
}

export const toolsAdapter: Adapter = {
  kind: "tools",
  noun: "tool",
  nouns: "tools",
  groupNoun: "group",
  groupNouns: "tool groups",
  icon: Wrench,
  color: "bg-warn",
  code: true,
  accept: ".py,.zip",
  linkHint: "/srv/tools/my_tool.py or pkg.mod:Tool",
  uploadHint: "A .py file or a .zip of one; every Tool class found is added under its name.",
  subtitle: (t) => [SOURCE_LABEL[t.source] ?? t.source, `${PANE_LABEL[t.pane] ?? t.pane} pane`, t.offered ? null : "not offered", t.groups.length ? `in ${t.groups.filter((g: string) => g !== "all").slice(0, 3).join(", ")}` : null, t.description].filter(Boolean).join(" · "),
  badge: (t) => (t.admin_only ? "admins" : t.source === "uploaded" || t.source === "linked" ? t.source : undefined),
  ItemExtra: ({ item, layer }) => <ToolDetails item={item} layer={layer} />,
  Extra: ({ layer, groups, items, reload }) => (
    <>
      <Offer layer={layer} groups={groups} items={items} reload={reload} />
      <PlacementOverview layer={layer} items={items} reload={reload} />
    </>
  ),
};
