import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Plus, Trash2, TriangleAlert } from "lucide-react";
import { api } from "../../api";
import { Select } from "../controls/Select";
import { TextArea, TextField } from "../controls/TextField";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import type { QSet } from "./QuestionnaireLibrary";

const TYPES = ["likert5", "likert7", "yes_no", "select", "text"];
const TYPE_LABEL: Record<string, string> = { likert5: "1–5 scale", likert7: "1–7 scale", yes_no: "Yes / no", select: "Choice (options)", text: "Free text" };

/** JSON with sorted keys: compares two questions whatever their key order. */
const stable = (v: any): string =>
  Array.isArray(v) ? `[${v.map(stable).join(",")}]` : v && typeof v === "object" ? `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(",")}}` : JSON.stringify(v);

/** The items of a form file, edited as a list: reorder, remove, edit, add (from any set, or blank).
 *  The YAML text stays the single source of truth: it is parsed on the server, and every edit is
 *  dumped back into it (``/api/admin/questionnaires/parse`` and ``/dump``), so the page's checks,
 *  preview and Save are those of the YAML editor. */
export function FormItemsEditor({ text, onText }: { text: string; onText: (t: string) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [lib, setLib] = useState<QSet[]>([]);
  const dumped = useRef<string | null>(null);
  useEffect(() => {
    api("/api/admin/questionnaire-library").then((r) => setLib(r.sets)).catch(() => setLib([]));
  }, []);
  useEffect(() => {
    if (text === dumped.current) return;
    const t = window.setTimeout(() => {
      api("/api/admin/questionnaires/parse", { body: { text } })
        .then((r) => (setData(r.data), setError("")))
        .catch((e) => (setData(null), setError(e.message)));
    }, 150);
    return () => window.clearTimeout(t);
  }, [text]);
  const seq = useRef(0);
  const update = async (next: any) => {
    setData(next);
    const mine = ++seq.current;
    try {
      const r = await api("/api/admin/questionnaires/dump", { body: { data: next } });
      if (mine !== seq.current) return; // a later edit is on its way
      dumped.current = r.text;
      onText(r.text);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const qs: any[] = Array.isArray(data?.questions) ? data.questions : [];
  const setQs = (list: any[]) => {
    const next = { ...data, questions: list };
    if (list.length && next.enabled === false) delete next.enabled; // adding items switches the form back on
    update(next);
  };
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= qs.length) return;
    const list = [...qs];
    [list[i], list[j]] = [list[j], list[i]];
    setQs(list);
    if (open === i) setOpen(j);
  };
  const remove = (i: number) => {
    setQs(qs.filter((_, k) => k !== i));
    setOpen(null);
  };
  const edit = (i: number, q: any) => setQs(qs.map((x, k) => (k === i ? q : x)));
  const freshId = (base: string) => {
    const have = new Set(qs.map((q) => String(q.id)));
    let n = qs.length + 1;
    while (have.has(`${base}${n}`)) n++;
    return `${base}${n}`;
  };
  const addBlank = () => {
    setQs([...qs, { id: freshId("q"), text: "New question", type: "likert7", required: true, labels: { 1: "Not at all", 7: "Very much" } }]);
    setOpen(qs.length);
  };
  const addFrom = (q: any) => {
    if (qs.some((x) => x.id === q.id)) return toast(`${q.id} is already in the form`, "error");
    setQs([...qs, JSON.parse(JSON.stringify(q))]);
  };
  // published instruments whose scored items were edited or removed: their scale may no longer match the source
  const notices = useMemo(() => {
    const byId = new Map(qs.map((q) => [String(q.id), q]));
    const out: { set: QSet; scales: string[] }[] = [];
    for (const s of lib) {
      if (!s.read_only) continue;
      const scored = s.questions.filter((q) => q.scale || q.reverse);
      if (!scored.some((q) => byId.has(String(q.id)))) continue;
      const changed = scored.filter((q) => !byId.has(String(q.id)) || stable(byId.get(String(q.id))) !== stable(q));
      if (changed.length) out.push({ set: s, scales: [...new Set(changed.map((q) => String(q.scale || "")).filter(Boolean))] });
    }
    return out;
  }, [qs, lib]);
  if (error)
    return (
      <div className="px-4 py-3">
        <Note tone="warn">The form does not parse, so it can only be edited as YAML for now: {error}</Note>
      </div>
    );
  if (!data) return <Spinner />;
  return (
    <div className="flex flex-col gap-3 px-4 py-3" id="setting-form-items">
      {data.enabled === false && <Note>This form is switched off here. Adding an item switches it back on.</Note>}
      <div className="grid gap-2 sm:grid-cols-[6rem_1fr] sm:items-center">
        <span className="text-xs text-muted">Title</span>
        <TextField label="Form title" className="w-full" value={data.title ?? ""} onChange={(v) => update({ ...data, title: v })} />
        <span className="text-xs text-muted">Intro</span>
        <TextArea label="Form intro" rows={2} value={data.intro ?? ""} onChange={(v) => update({ ...data, intro: v })} />
      </div>
      {notices.map(({ set, scales }) => (
        <div key={set.id} className="flex items-start gap-2 rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn" data-scale-notice={set.id}>
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          <span>
            Items of {set.title} were edited or removed{scales.length ? ` (${scales.map((x) => `scale_${x}`).join(", ")})` : ""}: the scale score may no longer match the published instrument.
          </span>
        </div>
      ))}
      <ol className="flex flex-col divide-y divide-line rounded-lg border border-line" aria-label="Form items">
        {qs.map((q, i) => (
          <li key={`${i}-${q.id}`} data-item={q.id}>
            <div className="flex items-start gap-2 px-3 py-2">
              <span className="mt-0.5 w-6 shrink-0 text-right text-xs text-muted">{i + 1}.</span>
              <button className="min-w-0 flex-1 text-left" aria-expanded={open === i} onClick={() => setOpen(open === i ? null : i)}>
                <span className="text-sm">
                  {open === i ? <ChevronDown size={13} className="mr-1 inline" /> : <ChevronRight size={13} className="mr-1 inline" />}
                  {q.text || <em className="text-muted">no text</em>}
                </span>
                <span className="block text-xs text-muted">
                  <code>{q.id}</code> · {TYPE_LABEL[q.type] ?? q.type}
                  {q.required ? "" : " · optional"}
                  {q.scale ? ` · scale ${q.scale}` : ""}
                  {q.reverse ? " (reversed)" : ""}
                </span>
              </button>
              <div className="flex shrink-0 gap-0.5">
                <button className="btn-ghost px-1.5" aria-label={`Move ${q.id} up`} title="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                  <ArrowUp size={14} />
                </button>
                <button className="btn-ghost px-1.5" aria-label={`Move ${q.id} down`} title="Move down" disabled={i === qs.length - 1} onClick={() => move(i, 1)}>
                  <ArrowDown size={14} />
                </button>
                <button className="btn-ghost px-1.5 text-bad" aria-label={`Remove ${q.id}`} title="Remove" onClick={() => remove(i)}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            {open === i && <ItemFields q={q} onChange={(nq) => edit(i, nq)} />}
          </li>
        ))}
        {!qs.length && <li className="px-3 py-2 text-sm text-muted">No items yet.</li>}
      </ol>
      <div className="flex flex-wrap items-end gap-2">
        <button className="btn-ghost text-xs" onClick={addBlank}>
          <Plus size={13} /> New item
        </button>
        <AddFromSet lib={lib} have={new Set(qs.map((q) => String(q.id)))} onAdd={addFrom} />
      </div>
      <p className="text-[11px] text-muted">Editing items rewrites the file in a standard layout and drops YAML comments; switch to YAML to keep them.</p>
    </div>
  );
}

function ItemFields({ q, onChange }: { q: any; onChange: (q: any) => void }) {
  const set = (k: string, v: any) => {
    const n = { ...q };
    if (v === undefined || v === "") delete n[k];
    else n[k] = v;
    onChange(n);
  };
  const labels: Record<string, string> = q.labels ?? {};
  const max = q.type === "likert5" ? 5 : q.type === "likert7" ? 7 : 0;
  const options: string = Array.isArray(q.options) ? q.options.map((o: any) => (typeof o === "object" ? o.value ?? o.label : o)).join("\n") : "";
  return (
    <div className="grid gap-2 border-t border-line/60 bg-paper/40 px-3 py-3 text-xs sm:grid-cols-[6rem_1fr] sm:items-center">
      <span className="text-muted">Id</span>
      <TextField label={`Id of ${q.id}`} className="w-64" mono commit="blur" value={q.id ?? ""} onChange={(v) => set("id", v.trim())} />
      <span className="text-muted">Text</span>
      <TextArea label={`Text of ${q.id}`} rows={2} value={q.text ?? ""} onChange={(v) => set("text", v)} />
      <span className="text-muted">Type</span>
      <Select label={`Type of ${q.id}`} value={q.type} onChange={(v) => set("type", v)} options={TYPES.map((t) => ({ value: t, label: TYPE_LABEL[t] }))} />
      <span className="text-muted">Required</span>
      <label className="inline-flex items-center gap-1.5">
        <input type="checkbox" aria-label={`Required: ${q.id}`} checked={!!q.required} onChange={(e) => set("required", e.target.checked)} /> Participants must answer
      </label>
      {max > 0 && (
        <>
          <span className="text-muted">Labels</span>
          <div className="flex flex-wrap items-center gap-2">
            {[1, max].map((k) => (
              <label key={k} className="inline-flex items-center gap-1">
                {k}:
                <TextField
                  label={`Label ${k} of ${q.id}`}
                  className="w-44"
                  value={labels[k] ?? (labels as any)[String(k)] ?? ""}
                  onChange={(v) => {
                    const l: any = { ...labels };
                    delete l[String(k)];
                    if (v) l[k] = v;
                    set("labels", Object.keys(l).length ? l : undefined);
                  }}
                />
              </label>
            ))}
          </div>
        </>
      )}
      {q.type === "select" && (
        <>
          <span className="text-muted">Options</span>
          <TextArea label={`Options of ${q.id}`} rows={4} placeholder="One option per line" value={options} onChange={(v) => set("options", v.split("\n").map((x) => x.trim()).filter(Boolean))} />
        </>
      )}
      {(q.scale || q.reverse) && (
        <>
          <span className="text-muted">Scoring</span>
          <span>
            Counts towards <code>scale_{q.scale}</code>
            {q.reverse ? ", reversed" : ""}.{" "}
            <button className="text-you hover:underline" onClick={() => onChange({ ...q, scale: undefined, reverse: undefined })}>
              Stop scoring it
            </button>
          </span>
        </>
      )}
    </div>
  );
}

function AddFromSet({ lib, have, onAdd }: { lib: QSet[]; have: Set<string>; onAdd: (q: any) => void }) {
  const [sid, setSid] = useState("");
  const [qid, setQid] = useState("");
  const s = lib.find((x) => x.id === sid);
  const free = (s?.questions ?? []).filter((q) => !have.has(String(q.id)));
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <Select label="Set to add an item from" value={sid} onChange={(v) => (setSid(v), setQid(""))} options={[{ value: "", label: "Add an item from a set…" }, ...lib.map((x) => ({ value: x.id, label: x.title }))]} />
      {s && (
        <>
          <Select label="Item to add" value={qid} onChange={setQid} options={[{ value: "", label: free.length ? "Pick an item…" : "All its items are in the form" }, ...free.map((q) => ({ value: String(q.id), label: `${q.id}: ${String(q.text).slice(0, 60)}` }))]} />
          <button
            className="btn-ghost text-xs"
            disabled={!qid}
            onClick={() => {
              const q = free.find((x) => String(x.id) === qid);
              if (q) onAdd(q);
              setQid("");
            }}
          >
            <Plus size={13} /> Add item
          </button>
        </>
      )}
    </div>
  );
}
