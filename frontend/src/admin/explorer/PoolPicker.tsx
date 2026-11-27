import { useEffect, useMemo, useState } from "react";
import { Layers, Save, X } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row } from "../Row";
import { lq, shortPath, type Layer } from "../layer";
import { toast } from "../toast";
import { MODE_LABEL, allowedHumans, poolEntryProblem } from "../modes";
import type { Choice } from "./types";

/** The declared mode (``study_mode`` of the study or its project; ``null``: derived from the pool) and
 *  the project's kind at a project or study layer; the settings layer has neither. */
function useLayerMode(layer: Layer, version: unknown) {
  const [m, setM] = useState<{ mode: string | null; kind: string } | null>(null);
  useEffect(() => {
    if (layer.kind === "settings" || !layer.project) return setM(null);
    const url = `/api/admin/projects/${encodeURIComponent(layer.project)}${layer.kind === "study" ? `/studies/${encodeURIComponent(layer.study ?? "")}` : ""}`;
    api(url)
      .then((r: any) => setM({ mode: r?.study_mode_effective?.declared ?? null, kind: r?.editor?.kind ?? "none" }))
      .catch(() => setM(null));
  }, [layer.id, version]);
  return m;
}

/** Which opponents / Assistants participants face at a layer: a multi-select over groups and single classes. */
export function PoolPicker({ kind, layer, choices, title, id }: { kind: "opponent" | "assistant"; layer: Layer; choices: Choice[]; title: string; id: string }) {
  const [d, setD] = useState<any>(undefined);
  const [sel, setSel] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [dirty, setDirty] = useState(false);
  const lm = useLayerMode(layer, d);
  // the declared mode limits what an opponent pool offers (Solo: no person; Paired: the right person only)
  const mode = kind === "opponent" ? lm?.mode ?? null : null;
  const pkind = lm?.kind ?? "none";
  const load = () =>
    api(`/api/admin/pools/${kind}${lq(layer)}`)
      .then((r) => (setD(r), setSel(r.items ?? []), setDirty(false)))
      .catch((e) => (toast(e.message, "error"), setD(null)));
  useEffect(() => {
    load();
  }, [layer.id]);
  const opts = useMemo(() => {
    // opponents may also be other participants: alone, or with their own Assistant
    const humans: Choice[] = kind === "opponent"
      ? [
          { value: "human", label: "human", hint: "Another participant (without an Assistant)" },
          { value: "human+assistant", label: "human+assistant", hint: "Another participant with an Assistant" },
        ]
      : [];
    const offered = (c: Choice) => kind !== "opponent" || !poolEntryProblem(c.value, mode, pkind);
    const all = [...humans, ...choices.filter((c) => c.group), ...choices.filter((c) => !c.group)].filter(offered);
    // what is chosen stays listed (to be removed), even when the mode does not offer it
    const extra: Choice[] = sel.filter((s) => !all.some((c) => c.value === s)).map((s) => ({ value: s, label: s }));
    return [...extra, ...all].filter((c) => !q || `${c.value} ${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  }, [choices, q, sel, kind, mode, pkind]);
  if (d === undefined) return null;
  if (d === null) return null;
  const bad = kind === "opponent" ? sel.map((s) => [s, poolEntryProblem(s, mode, pkind)] as const).filter(([, why]) => why) : [];
  const humansHere = allowedHumans(mode, pkind);
  const modeHint = kind !== "opponent" || mode === null ? null
    : mode === "paired" ? `${MODE_LABEL.paired} study: only ${humansHere!.join(" or ")} is offered`
    : `${MODE_LABEL[mode as "solo" | "mixed"] ?? mode} study: ${mode === "solo" ? "no human entry is offered" : "every entry is offered"}`;
  const toggle = (v: string) => (setSel(sel.includes(v) ? sel.filter((x) => x !== v) : [...sel, v]), setDirty(true));
  const save = async () => {
    try {
      const r = await api(`/api/admin/pools/${kind}${lq(layer)}`, { method: "PUT", body: { items: sel } });
      setD(r);
      setSel(r.items ?? sel);
      setDirty(false);
      toast(`Saved to ${layer.label}`);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <Group title={title} id={`setting-${id}`} footer={<>{d.note ? `${d.note}. ` : ""}{d.file && <>Stored in <code>{shortPath(d.file)}</code>{d.key ? <> as <code>{d.key}</code></> : null}. </>}A URL's <code>?{kind === "opponent" ? "opponents" : "assistants"}=</code> or <code>?group=</code>, an environment variable or an outside system's schedule still win.</>}>
      <Row label="Chosen here" help={kind === "opponent" ? "opponents.pool" : undefined} hint={sel.length ? `${d.effective?.length ?? "?"} ${kind === "opponent" ? "opponent" : "Assistant"}${d.effective?.length === 1 ? "" : "s"} after expanding the groups` : `Nothing chosen in this layer: inherited ${d.inherited?.length ? d.inherited.join(", ") : "default"}`} wide>
        <div className="flex flex-wrap gap-1.5">
          {sel.length === 0 && <span className="text-sm text-muted">—</span>}
          {sel.map((s) => (
            <span key={s} className={`chip py-1 text-[0.8rem] ${bad.some(([b]) => b === s) ? "border-bad text-bad" : ""}`} title={bad.find(([b]) => b === s)?.[1]} data-pool-entry={s}>
              {(s.startsWith(":") || s.startsWith("@")) && <Layers size={12} className="text-you" />}
              {s}
              {d.editable && (
                <button aria-label={`Remove ${s}`} className="text-muted hover:text-bad" onClick={() => toggle(s)}>
                  <X size={12} />
                </button>
              )}
            </span>
          ))}
        </div>
      </Row>
      {modeHint && <div className="px-4 pb-1 text-xs text-muted" data-pool-mode={mode}>{modeHint} (the Mode of {layer.kind === "study" ? "this study or its project" : "this project"}).</div>}
      {bad.length > 0 && (
        <div className="px-4 py-1 text-sm text-bad" role="alert" data-pool-problem>
          {bad.map(([s, why]) => <div key={s}>{s}: {why}. Remove it to save.</div>)}
        </div>
      )}
      {d.editable && (
        <>
          <Row label="Add groups or single classes" wide>
            <input aria-label="Filter choices" type="search" className="mb-2 w-full rounded-md border border-line bg-surface px-2 py-1 text-sm focus:border-you focus:outline-none" placeholder={`Search ${choices.length} groups and classes`} value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="scroll-thin max-h-56 overflow-y-auto rounded-lg border border-line/70" role="listbox" aria-multiselectable aria-label="Pool choices">
              {opts.slice(0, 200).map((c) => (
                <label key={c.value} className="flex cursor-pointer items-start gap-2 border-b border-line/50 px-3 py-1.5 text-sm last:border-0 hover:bg-sunken/60">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--you))]" checked={sel.includes(c.value)} onChange={() => toggle(c.value)} />
                  <span className="min-w-0">
                    <span className={c.group ? "font-medium" : ""}>{c.value}</span>
                    {(c.hint || c.label !== c.value) && <span className="block truncate text-xs text-muted">{c.hint ?? c.label}</span>}
                  </span>
                </label>
              ))}
              {opts.length > 200 && <div className="px-3 py-1.5 text-xs text-muted">{opts.length - 200} more; search to narrow</div>}
            </div>
          </Row>
          <Row label="">
            {dirty && <span className="text-xs text-muted">Unsaved</span>}
            <button className="btn-primary" disabled={!dirty || bad.length > 0} onClick={save}>
              <Save size={15} /> Save pool
            </button>
          </Row>
        </>
      )}
    </Group>
  );
}
