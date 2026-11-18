import { api, apiForm } from "../../api";
import { lq, type Layer } from "../layer";
import type { EntryInfo, ExGroup, ExItem, Kind, LibItem } from "./types";

/** The library API (docs/reference/library-api.md): one set of calls for every kind. */
const BASE = "/api/admin/library";
const enc = encodeURIComponent;

export const SOURCE_LABEL: Record<string, string> = { builtin: "built in", registered: "registered", uploaded: "uploaded", linked: "linked" };

/** ``@name`` / ``:name`` name a group; a bare entry may too (when a group has that name). */
export const isRef = (e: string) => e.startsWith("@") || e.startsWith(":");
export const refName = (e: string) => (isRef(e) ? e.slice(1).trim() : e.trim());

export async function listItems(kind: Kind, layer: Layer): Promise<LibItem[]> {
  return (await api<{ items: LibItem[] }>(`${BASE}/${kind}${lq(layer)}`)).items;
}

const layerLabel = (id: string | null | undefined) =>
  !id ? "" : id === "settings" ? "the settings folder" : id === "results" ? "an outside system's files" : id.startsWith("project:") ? `project ${id.slice(8)}` : id.startsWith("study:") ? `study ${id.slice(6)}` : id;

export async function listGroups(kind: Kind, layer: Layer): Promise<ExGroup[]> {
  const r = await api<{ groups: any[] }>(`${BASE}/${kind}/groups${lq(layer)}`);
  return r.groups
    .filter((g) => !(g.source === "builtin" && kind === "opponents" && g.name === "hani")) // old alias of :classic
    .map((g) => {
      const builtin = g.source === "builtin" || g.source === "custom";
      return {
        key: g.name,
        entries: g.entries ?? [],
        expanded: g.expanded ?? [],
        description: g.description || (g.source === "custom" ? "scenario_order.txt (edit it in Texts → Custom order)" : undefined),
        origin: builtin ? (g.source === "custom" ? "scenario_order.txt" : undefined) : g.layer === layer.id ? "this layer" : `from ${layerLabel(g.layer)}`,
        editable: !!g.editable,
        inherited: !builtin && !g.editable,
        active: g.active !== false,
        builtin,
        raw: g,
      } as ExGroup;
    })
    .map((g, i) => ({ g, i }))
    // this layer's first, then inherited ones, then the built-in ones (each in the API's order)
    .sort((a, b) => rank(a.g) - rank(b.g) || a.i - b.i)
    .map((x) => x.g);
}
const rank = (g: ExGroup) => (g.editable ? 0 : g.inherited ? 1 : 2);

export async function saveGroup(kind: Kind, layer: Layer, key: string, entries: string[], extra: Record<string, any> = {}) {
  return api<{ ok: boolean; expanded: string[]; warnings?: string[] }>(`${BASE}/${kind}/groups/${enc(key)}${lq(layer)}`, { method: "PUT", body: { entries, ...extra } });
}

export const deleteGroup = (kind: Kind, layer: Layer, key: string) => api(`${BASE}/${kind}/groups/${enc(key)}${lq(layer)}`, { method: "DELETE" });

export const removeItem = (kind: Kind, layer: Layer, name: string) => api<{ how: string; trash?: string }>(`${BASE}/${kind}/items/${enc(name)}${lq(layer)}`, { method: "DELETE" });

export interface AddResult {
  ok: boolean;
  items: { name: string; source: string; layer: string; spec?: string; n_scenarios?: number }[];
  warnings: string[];
  notice?: string | null;
}

export function upload(kind: Kind, layer: Layer, file: File, fields: Record<string, string | boolean | undefined>) {
  const f = new FormData();
  f.append("file", file, file.name);
  f.append("layer", layer.id);
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== "" && v !== false) f.append(k, v === true ? "true" : String(v));
  return apiForm<AddResult>(`${BASE}/${kind}/upload`, f);
}

export const link = (kind: Kind, layer: Layer, body: Record<string, any>) => api<AddResult>(`${BASE}/${kind}/link${lq(layer)}`, { body });

const described = new Map<string, EntryInfo>();

/** What each entry is (cached per kind, layer and entry; cleared when the library changes). */
export async function describe(kind: Kind, layer: Layer, entries: string[]): Promise<Record<string, EntryInfo>> {
  const key = (e: string) => `${kind}|${layer.id}|${e}`;
  const missing = entries.filter((e) => !described.has(key(e)));
  if (missing.length) {
    try {
      const r = await api<{ entries: EntryInfo[] }>(`${BASE}/${kind}/describe${lq(layer)}`, { body: missing });
      r.entries.forEach((d) => described.set(key(d.entry), d));
    } catch {
      /* descriptions are a nicety */
    }
  }
  return Object.fromEntries(entries.filter((e) => described.has(key(e))).map((e) => [e, described.get(key(e))!]));
}
export const forgetDescriptions = () => described.clear();

/** Items as the explorer lists them. */
export function toItems(items: LibItem[], subtitle?: (i: LibItem) => string, badge?: (i: LibItem) => string | undefined): ExItem[] {
  return items.map((i) => ({
    id: i.name,
    title: i.title && i.title !== i.name ? `${i.name} — ${i.title}` : i.name,
    subtitle: subtitle ? subtitle(i) : [SOURCE_LABEL[i.source] ?? i.source, i.groups.length ? `in ${i.groups.slice(0, 3).join(", ")}${i.groups.length > 3 ? "…" : ""}` : null, i.description].filter(Boolean).join(" · "),
    badge: badge ? badge(i) : i.source === "uploaded" || i.source === "linked" ? i.source : undefined,
    search: [i.spec, i.description, i.groups.join(" "), i.source].join(" "),
    raw: i,
  }));
}

/** Ways to refer to an item or a group inside a group. */
export function choices(items: ExItem[], groups: ExGroup[]) {
  const seen = new Set<string>();
  const gs = groups.filter((g) => g.active !== false && !seen.has(g.key.toLowerCase()) && seen.add(g.key.toLowerCase()));
  return [
    ...gs.map((g) => ({ value: `@${g.key}`, label: `@${g.key}`, hint: `${g.expanded?.length ?? g.entries.length} · ${g.description || g.origin || ""}`, group: true })),
    ...items.map((i) => ({ value: i.id, label: i.title, hint: i.subtitle })),
  ];
}

/** The group an entry names, if any (``@x``, ``:x``, or a bare name that is a group's). */
export function groupOf(entry: string, groups: ExGroup[], self?: string): ExGroup | undefined {
  const n = refName(entry).toLowerCase();
  if (!isRef(entry) && self && n === self.toLowerCase()) return undefined;
  return groups.find((g) => g.active !== false && g.key.toLowerCase() === n);
}
