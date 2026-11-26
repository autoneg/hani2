import { useEffect, useMemo, useState } from "react";
import { Layers, Save, X } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { Row } from "../Row";
import { lq, shortPath, type Layer } from "../layer";
import { toast } from "../toast";
import type { Choice } from "./types";

/** Which opponents / Assistants participants face at a layer: a multi-select over groups and single classes. */
export function PoolPicker({ kind, layer, choices, title, id }: { kind: "opponent" | "assistant"; layer: Layer; choices: Choice[]; title: string; id: string }) {
  const [d, setD] = useState<any>(undefined);
  const [sel, setSel] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [dirty, setDirty] = useState(false);
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
    const all = [...humans, ...choices.filter((c) => c.group), ...choices.filter((c) => !c.group)];
    const extra: Choice[] = sel.filter((s) => !all.some((c) => c.value === s)).map((s) => ({ value: s, label: s }));
    return [...extra, ...all].filter((c) => !q || `${c.value} ${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  }, [choices, q, sel, kind]);
  if (d === undefined) return null;
  if (d === null) return null;
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
      <Row label="Chosen here" hint={sel.length ? `${d.effective?.length ?? "?"} ${kind === "opponent" ? "opponent" : "Assistant"}${d.effective?.length === 1 ? "" : "s"} after expanding the groups` : `Nothing chosen in this layer: inherited ${d.inherited?.length ? d.inherited.join(", ") : "default"}`} wide>
        <div className="flex flex-wrap gap-1.5">
          {sel.length === 0 && <span className="text-sm text-muted">—</span>}
          {sel.map((s) => (
            <span key={s} className="chip py-1 text-[0.8rem]">
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
            <button className="btn-primary" disabled={!dirty} onClick={save}>
              <Save size={15} /> Save pool
            </button>
          </Row>
        </>
      )}
    </Group>
  );
}
