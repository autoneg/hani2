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
export function FormItemsEditor({ text, onText, form, kind = "form" }: { text: string; onText: (t: string) => void; form?: string; kind?: "form" | "set" }) {
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
  // published instruments whose scored items were edited, removed or left out: their scale may no longer
  // match the source. A set whose items in the form all belong to another published set that is complete
  // and unchanged (TAM usefulness, short and full, share two items) is not flagged.
  const notices = useMemo(() => {
    const byId = new Map(qs.map((q) => [String(q.id), q]));
    const sourced = lib.filter((s) => s.read_only);
    const scoredOf = (s: QSet) => s.questions.filter((q) => q.scale || q.reverse);
    const changedOf = (s: QSet) => scoredOf(s).filter((q) => !byId.has(String(q.id)) || stable(byId.get(String(q.id))) !== stable(q));
    const intact = sourced.filter((s) => scoredOf(s).length > 0 && changedOf(s).length === 0);
    const coveredIds = new Set(intact.flatMap((s) => s.questions.map((q) => String(q.id))));
    const out: { set: QSet; scales: string[] }[] = [];
    for (const s of sourced) {
      const present = scoredOf(s).filter((q) => byId.has(String(q.id)));
      if (!present.length) continue;
      const changed = changedOf(s);
      if (!changed.length) continue;
      if (!intact.includes(s) && present.every((q) => coveredIds.has(String(q.id))) && present.every((q) => stable(byId.get(String(q.id))) === stable(q))) continue;
      out.push({ set: s, scales: [...new Set(changed.map((q) => String(q.scale || "")).filter(Boolean))] });
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
      {kind === "set" ? (
        <SetFields data={data} onChange={update} />
      ) : (
        <div className="grid gap-2 sm:grid-cols-[6rem_1fr] sm:items-center">
          <span className="text-xs text-muted">Title</span>
          <TextField label="Form title" className="w-full" value={data.title ?? ""} onChange={(v) => update({ ...data, title: v })} />
          <span className="text-xs text-muted">Intro</span>
          <TextArea label="Form intro" rows={2} value={data.intro ?? ""} onChange={(v) => update({ ...data, intro: v })} />
        </div>
      )}
      {notices.map(({ set, scales }) => (
        <div key={set.id} className="flex items-start gap-2 rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn" data-scale-notice={set.id}>
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          <span>
            Scored items of {set.title} were edited, removed or left out{scales.length ? ` (${scales.map((x) => `scale_${x}`).join(", ")})` : ""}: the scale score may no longer match the published instrument.
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
                  {q.requires ? ` · ${REQUIRES_LABEL[q.requires] ?? `requires ${q.requires}`}` : ""}
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
      {(form === "pre_questionnaire" || data.participant_type) && (
        <ParticipantType value={data.participant_type} questions={qs} onChange={(v) => {
          const next = { ...data };
          if (v) next.participant_type = v;
          else delete next.participant_type;
          update(next);
        }} />
      )}
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

const SET_FORMS: [string, string][] = [["pre_questionnaire", "Pre-questionnaire"], ["per_negotiation", "After each negotiation"], ["post_session", "Post-session"]];

/** The header of a questionnaire library set: id, title, description, reference, based on, the forms it
 *  suits and the parties it asks about (``tags``). */
function SetFields({ data, onChange }: { data: any; onChange: (d: any) => void }) {
  const put = (k: string, v: any) => {
    const n = { ...data };
    if (v === undefined || v === "" || (Array.isArray(v) && !v.length && k !== "tags")) delete n[k];
    else n[k] = v;
    onChange(n);
  };
  const list = (k: string): string[] => (Array.isArray(data[k]) ? data[k].map(String) : data[k] ? [String(data[k])] : []);
  const toggle = (k: string, x: string, on: boolean) => {
    const cur = list(k);
    const order = k === "forms" ? SET_FORMS.map((f) => f[0]) : ["assistant", "opponent"];
    put(k, order.filter((y) => (y === x ? on : cur.includes(y))));
  };
  return (
    <div className="grid gap-2 text-xs sm:grid-cols-[6rem_1fr] sm:items-center" data-set-fields>
      <span className="text-muted">Id</span>
      <TextField label="Set id" className="w-64" mono commit="blur" value={data.id ?? ""} onChange={(v) => put("id", v.trim())} />
      <span className="text-muted">Title</span>
      <TextField label="Set title" className="w-full" value={data.title ?? ""} onChange={(v) => put("title", v)} />
      <span className="text-muted">Description</span>
      <TextArea label="Set description" rows={2} value={data.description ?? ""} onChange={(v) => put("description", v)} />
      <span className="text-muted">Reference</span>
      <TextField label="Set reference" className="w-full" value={data.reference ?? ""} onChange={(v) => put("reference", v)} />
      <span className="text-muted">Based on</span>
      <TextField label="Set based on" className="w-full" placeholder="The published source it adapts, if any" value={data.based_on ?? ""} onChange={(v) => put("based_on", v)} />
      <span className="text-muted">Meant for</span>
      <div className="flex flex-wrap gap-3">
        {SET_FORMS.map(([k, l]) => (
          <label key={k} className="inline-flex items-center gap-1.5">
            <input type="checkbox" aria-label={`Meant for ${l}`} checked={list("forms").includes(k)} onChange={(e) => toggle("forms", k, e.target.checked)} /> {l}
          </label>
        ))}
      </div>
      <span className="text-muted">About</span>
      <div className="flex flex-wrap items-center gap-3">
        {[["assistant", "The Assistant"], ["opponent", "The opponent"]].map(([k, l]) => (
          <label key={k} className="inline-flex items-center gap-1.5">
            <input type="checkbox" aria-label={`About ${l}`} checked={list("tags").includes(k)} onChange={(e) => toggle("tags", k, e.target.checked)} /> {l}
          </label>
        ))}
        <span className="text-muted">Both: write {"{{agent}}"} for the party and ask the items only when it took part. Neither: about the participant, the task or the system.</span>
      </div>
    </div>
  );
}

const REQUIRES_LABEL: Record<string, string> = { support_agent: "only with an Assistant", agent: "only with the party asked about" };

/** ``options`` as text, one per line (participants see and record the text of the option). */
const optionsText = (opts: any[]) => opts.map((o: any) => (o && typeof o === "object" ? String(o.value ?? o.label ?? "") : String(o))).join("\n");
const parseOptions = (t: string) => t.split("\n").map((x) => x.trim()).filter(Boolean);

function ItemFields({ q, onChange }: { q: any; onChange: (q: any) => void }) {
  const set = (k: string, v: any) => {
    const n = { ...q };
    if (v === undefined || v === "" || v === null) delete n[k];
    else n[k] = v;
    onChange(n);
  };
  const labels: Record<string, string> = q.labels ?? {};
  const max = q.type === "likert5" ? 5 : q.type === "likert7" ? 7 : 0;
  const [optText, setOptText] = useState(Array.isArray(q.options) ? optionsText(q.options) : "");
  const numeric = q.type !== "text";
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
      <span className="text-muted">Asked</span>
      <Select label={`When ${q.id} is asked`} value={q.requires ?? ""} onChange={(v) => set("requires", v)} options={[{ value: "", label: "Always" }, { value: "support_agent", label: "Only when an Assistant took part" }, { value: "agent", label: "Only when the party it asks about ({{agent}}) took part" }]} />
      {max > 0 && (
        <>
          <span className="text-muted">Labels</span>
          <div className="flex flex-wrap items-center gap-2">
            {Array.from({ length: max }, (_, j) => j + 1).map((k) => (
              <label key={k} className="inline-flex items-center gap-1">
                {k}:
                <TextField
                  label={`Label ${k} of ${q.id}`}
                  className={k === 1 || k === max ? "w-40" : "w-28"}
                  placeholder={k === 1 || k === max ? "" : "(none)"}
                  value={labels[k] ?? (labels as any)[String(k)] ?? ""}
                  onChange={(v) => {
                    const l: any = { ...labels };
                    delete l[String(k)];
                    delete l[k];
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
          <div>
            <TextArea label={`Options of ${q.id}`} rows={4} placeholder="One option per line" value={optText} onChange={(v) => (setOptText(v), set("options", parseOptions(v)))} />
            <span className="text-[11px] text-muted">One per line, in order: a scored choice counts 1 for the first option, 2 for the second, and so on.</span>
          </div>
        </>
      )}
      {numeric && (
        <>
          <span className="text-muted">Scoring</span>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-1">
              Scale
              <TextField label={`Scale of ${q.id}`} className="w-36" mono commit="blur" placeholder="(not scored)" value={q.scale ?? ""} onChange={(v) => set("scale", v.trim() || undefined)} />
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" aria-label={`Reversed: ${q.id}`} checked={!!q.reverse} onChange={(e) => set("reverse", e.target.checked || undefined)} /> Reversed
            </label>
            <label className="inline-flex items-center gap-1">
              Better is
              <Select label={`Direction of ${q.id}`} value={q.direction ?? ""} onChange={(v) => set("direction", v)} options={[{ value: "", label: q.scale ? "Higher (default)" : "Not ranked (default)" }, { value: "higher", label: "Higher" }, { value: "lower", label: "Lower" }]} />
            </label>
            {q.type !== "select" && (
              <label className="inline-flex items-center gap-1" title="The answer range used for scoring and normalising (the type gives the default)">
                Range
                <NumberBox label={`Lowest answer of ${q.id}`} value={q.min} onChange={(v) => set("min", v)} />
                to
                <NumberBox label={`Highest answer of ${q.id}`} value={q.max} onChange={(v) => set("max", v)} />
              </label>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function NumberBox({ label, value, onChange }: { label: string; value: any; onChange: (v: number | undefined) => void }) {
  return <TextField label={label} className="w-14" mono commit="blur" placeholder="auto" value={value == null ? "" : String(value)} onChange={(v) => onChange(v.trim() === "" || Number.isNaN(Number(v)) ? undefined : Number(v))} />;
}

/** ``participant_type`` of a pre-questionnaire: the question whose answer is the participant's type,
 *  and how answers map to types (unmapped answers are used as they are). */
function ParticipantType({ value, questions, onChange }: { value: any; questions: any[]; onChange: (v: any) => void }) {
  const cfg = typeof value === "string" ? { question: value } : value ?? null;
  const map: Record<string, string> = cfg?.map ?? {};
  const qid = cfg?.question ?? (cfg ? "expertise" : "");
  const q = questions.find((x) => String(x.id) === qid);
  const answers: string[] = q?.type === "select" ? (q.options ?? []).map((o: any) => String(o && typeof o === "object" ? o.value : o)) : q?.type === "yes_no" ? ["yes", "no"] : Object.keys(map);
  const put = (n: any) => onChange(n && (n.question || Object.keys(n.map ?? {}).length) ? n : null);
  return (
    <div className="rounded-lg border border-line px-3 py-2 text-xs" data-participant-type>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Participant type</span>
        <Select label="Question that gives the participant type" value={cfg ? qid : ""} onChange={(v) => put(v ? { ...(cfg ?? {}), question: v } : null)} options={[{ value: "", label: "None" }, ...questions.map((x) => ({ value: String(x.id), label: String(x.id) }))]} />
        <span className="text-muted">The answer is the participant's type (boards can be split by it).</span>
      </div>
      {cfg && answers.length > 0 && (
        <div className="mt-2 grid gap-1.5 sm:grid-cols-[10rem_1fr] sm:items-center">
          {answers.map((a) => (
            <div key={a} className="contents">
              <span className="truncate text-muted" title={a}>{a} →</span>
              <TextField label={`Type for ${a}`} className="w-48" placeholder={a} value={map[a] ?? ""} onChange={(v) => {
                const m = { ...map };
                if (v) m[a] = v;
                else delete m[a];
                put({ ...cfg, question: qid, ...(Object.keys(m).length ? { map: m } : { map: undefined }) });
              }} />
            </div>
          ))}
        </div>
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
