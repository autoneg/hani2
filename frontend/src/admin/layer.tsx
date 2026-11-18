import { createContext, useContext, useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { api } from "../api";
import { Select } from "./controls/Select";

/** A settings layer: the shared settings folder, a project, or a study. */
export interface Layer {
  id: string; // settings | project:P | study:P/S
  kind: "settings" | "project" | "study";
  label: string;
  project?: string;
  study?: string;
  path?: string;
}

export interface LayerInfo {
  layers: Layer[];
  bound: string | null;
  default_study: string | null;
}

const SETTINGS: Layer = { id: "settings", kind: "settings", label: "All projects (settings folder)" };

export const LayerContext = createContext<{ layer: Layer; setLayer: (id: string) => void; info: LayerInfo; reload: () => void }>({
  layer: SETTINGS,
  setLayer: () => {},
  info: { layers: [SETTINGS], bound: null, default_study: null },
  reload: () => {},
});
export const useLayer = () => useContext(LayerContext);

/** ``?layer=…`` for an API call (always explicit, never taken from the page URL). */
export const lq = (layer: Layer | string, sep = "?") => `${sep}layer=${encodeURIComponent(typeof layer === "string" ? layer : layer.id)}`;

/** The study a layer belongs to (``P/S``), if any. */
export const layerStudy = (l: Layer) => (l.kind === "study" ? `${l.project}/${l.study}` : null);

export function useLayerState() {
  const [info, setInfo] = useState<LayerInfo>({ layers: [SETTINGS], bound: null, default_study: null });
  const [id, setId] = useState<string | null>(null);
  const load = () =>
    api<LayerInfo>("/api/admin/layers")
      .then((d) => {
        setInfo(d);
        setId((cur) => cur ?? d.bound ?? "settings");
      })
      .catch(() => setId((cur) => cur ?? "settings"));
  useEffect(() => {
    load();
  }, []);
  const layer = info.layers.find((l) => l.id === id) ?? (id && id !== "settings" ? parseLayer(id) : SETTINGS);
  return { layer, setLayer: setId, info, reload: load, ready: id !== null };
}

export function parseLayer(id: string): Layer {
  if (id.startsWith("project:")) return { id, kind: "project", project: id.slice(8), label: `Project ${id.slice(8)}` };
  if (id.startsWith("study:")) {
    const [p, s] = id.slice(6).split("/");
    return { id, kind: "study", project: p, study: s, label: `Study ${p}/${s}` };
  }
  return SETTINGS;
}

/** "Save to: [layer]" — shown at the top of every page whose settings can live in a layer. */
export function LayerPicker({ note, allow }: { note?: React.ReactNode; allow?: Layer["kind"][] }) {
  const { layer, setLayer, info } = useLayer();
  const layers = info.layers.filter((l) => !allow || allow.includes(l.kind));
  const opts = layers.map((l) => ({ value: l.id, label: l.kind === "settings" ? l.label : l.kind === "project" ? `Project ${l.project}` : `Study ${l.project}/${l.study}` }));
  const bound = info.bound && info.bound !== layer.id ? info.layers.find((l) => l.id === info.bound) : null;
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-you/25 bg-you/[0.06] px-3.5 py-2.5" role="group" aria-label="Layer">
      <Layers size={16} className="shrink-0 text-you" />
      <span className="text-sm font-medium">Edit and save in</span>
      <Select label="Layer to edit" value={layer.id} onChange={setLayer} options={opts} />
      <span className="min-w-0 flex-1 basis-full text-xs text-muted sm:basis-auto">
        {note ??
          (layer.kind === "settings"
            ? "Shared by every project and study, unless a project or study sets its own value."
            : layer.kind === "project"
              ? `Applies to every study of ${layer.project} that does not set its own value.`
              : "Applies to this study only.")}
        {bound && <> This console is open in study <b className="text-ink">{bound.project}/{bound.study}</b>.</>}
      </span>
    </div>
  );
}

/** A path shown relative to the HANI2 home (settings/…, projects/…) when it is inside it. */
export const shortPath = (p?: string | null) => (p ? p.replace(/^.*?\/((settings|projects|experiments|db)\/)/, "$1") : "");
