import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Copy, FilePlus2, Lock, Pencil, Save, Search, Trash2, TriangleAlert, X } from "lucide-react";
import { api } from "../../api";
import { CopyField } from "../CopyField";
import { Group } from "../Group";
import { Segmented } from "../controls/Segmented";
import { TextArea } from "../controls/TextField";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { VALIDATED_SOURCE_TIP, ValidatedMark } from "../../ui/metricGroups";

/** A set as ``GET /api/admin/questionnaire-library`` lists it (hani2.questionnaire_library.entries). */
export interface QSet {
  id: string;
  title: string;
  description: string;
  reference: string;
  forms: string[];
  /** the parties its questions are about: assistant, opponent, both, or none (the participant, the task, the system) */
  tags: string[];
  questions: any[];
  n_questions: number;
  scales: string[];
  origin: "bundled" | "own" | "override";
  path: string;
  bundled_path?: string;
  read_only: boolean;
  source_citation: string;
  based_on: string;
  copied_from: string;
  validated?: boolean;
  validation_note?: string;
  url?: string;
  /** a source warning, for the admin only (never shown to participants) */
  warning: string;
  delete?: { command: string; file: string; effect: string };
}

const FORM_LABEL: Record<string, string> = { pre_questionnaire: "Pre", per_negotiation: "After each negotiation", post_session: "Post-session" };
const ORIGIN_LABEL: Record<QSet["origin"], string> = { bundled: "Bundled", own: "Your own", override: "Your own, overrides a bundled set" };
type Filter = "all" | "pre_questionnaire" | "per_negotiation" | "post_session";
type About = "all" | "assistant" | "opponent" | "none";
const ABOUT_LABEL = (tags: string[] = []) =>
  tags.includes("assistant") && tags.includes("opponent") ? "about the Assistant or the opponent ({{agent}})" : tags.includes("assistant") ? "about the Assistant" : tags.includes("opponent") ? "about the opponent" : "";
type Editing = { mode: "edit"; id: string; text: string } | { mode: "new"; text: string; from?: string };

const GROUPS: [string, string, (s: QSet) => boolean][] = [
  ["published", "Published instruments (read-only here; copy to adapt)", (s) => s.read_only],
  ["own", "Your own sets", (s) => !s.read_only && s.origin !== "bundled"],
  ["builtin", "Built-in sets (editing saves an override)", (s) => !s.read_only && s.origin === "bundled"],
];

export function QuestionnaireLibrary() {
  const [d, setD] = useState<any>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [about, setAbout] = useState<About>("all");
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const load = () => api("/api/admin/questionnaire-library").then(setD).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  const sets: QSet[] = d?.sets ?? [];
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return sets.filter((s) => {
      if (filter !== "all" && !s.forms.includes(filter)) return false;
      const tags = s.tags ?? [];
      if (about === "none" ? tags.length > 0 : about !== "all" && !tags.includes(about)) return false;
      const hay = [s.id, s.title, s.description, s.reference, s.based_on, ...s.scales, ...s.questions.map((x) => `${x.id} ${x.text}`)].join(" ").toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }, [sets, q, filter, about]);
  const edit = async (s: QSet) => {
    try {
      const r = await api(`/api/admin/questionnaire-library/${encodeURIComponent(s.id)}`);
      setEditing({ mode: "edit", id: s.id, text: r.text });
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const copy = async (s: QSet) => {
    try {
      const r = await api(`/api/admin/questionnaire-library/${encodeURIComponent(s.id)}/copy`);
      setEditing({ mode: "new", text: r.text, from: s.title });
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  if (!d) return <Spinner />;
  if (editing)
    return (
      <SetEditor
        editing={editing}
        set={editing.mode === "edit" ? sets.find((s) => s.id === editing.id) : undefined}
        ownDir={d.own_dir}
        onClose={() => setEditing(null)}
        onSaved={(id) => {
          setEditing(null);
          setOpen(id);
          load();
        }}
      />
    );
  return (
    <div id="questionnaire-explorer">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex min-w-[14rem] flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5">
          <Search size={14} className="text-muted" />
          <input className="w-full bg-transparent text-sm outline-none" placeholder="Search titles, ids, questions, scales…" aria-label="Search questionnaires" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button className="btn-primary text-sm" onClick={() => setEditing({ mode: "new", text: d.blank })}>
          <FilePlus2 size={14} /> New set
        </button>
      </div>
      <div className="mb-4 flex flex-wrap gap-3">
        <Segmented label="Meant for" value={filter} onChange={setFilter} options={[["all", "All forms"], ["pre_questionnaire", "Pre"], ["per_negotiation", "After each negotiation"], ["post_session", "Post-session"]]} />
        <Segmented label="About" value={about} onChange={setAbout} options={[["all", "Any party"], ["assistant", "The Assistant"], ["opponent", "The opponent"], ["none", "Neither"]]} />
      </div>
      {d.broken?.length > 0 && (
        <Note tone="warn">
          <TriangleAlert size={14} className="mr-1 inline" /> These files in the library folder are not question sets; fix or delete them:
          <ul className="mt-1 flex flex-col gap-1">
            {d.broken.map((b: any) => (
              <li key={b.path}>
                <span className="text-xs">{b.problem}</span>
                <CopyField value={b.command} label={`delete command for ${b.path}`} />
              </li>
            ))}
          </ul>
        </Note>
      )}
      {GROUPS.map(([key, title, test]) => {
        const items = shown.filter(test);
        if (!items.length) return null;
        return (
          <Group key={key} id={`questionnaire-group-${key}`} title={`${title} · ${items.length}`}>
            {items.map((s) => (
              <SetRow key={s.id} s={s} tip={d.validated_tooltip || VALIDATED_SOURCE_TIP} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)} onEdit={() => edit(s)} onCopy={() => copy(s)} />
            ))}
          </Group>
        );
      })}
      {!shown.length && <p className="px-1 text-sm text-muted">No set matches.</p>}
      <p className="mt-2 px-1 text-xs leading-relaxed text-muted">
        Sets you add or edit here are saved in <code>{d.own_dir}</code>. There is no delete button: each own set shows the file to remove.
      </p>
    </div>
  );
}

function SetRow({ s, tip, open, onToggle, onEdit, onCopy }: { s: QSet; tip: string; open: boolean; onToggle: () => void; onEdit: () => void; onCopy: () => void }) {
  return (
    <div data-set={s.id}>
      <button className="flex w-full items-start gap-2 px-4 py-2.5 text-left hover:bg-paper/60" aria-expanded={open} onClick={onToggle}>
        {open ? <ChevronDown size={15} className="mt-0.5 shrink-0" /> : <ChevronRight size={15} className="mt-0.5 shrink-0" />}
        <span className="min-w-0 flex-1">
          <span className="text-sm font-medium">{s.title}</span>
          {s.validated && <ValidatedMark tip={`${tip}${s.validation_note ? `: ${s.validation_note}` : ""}`} />}
          {s.warning && <TriangleAlert size={13} className="ml-1 inline text-warn" aria-label="Has a source warning" />}
          {s.read_only && <Lock size={12} className="ml-1 inline text-muted" aria-label="Read-only" />}
          <span className="ml-2 text-xs text-muted">
            <code>{s.id}</code> · {s.n_questions} question{s.n_questions === 1 ? "" : "s"} · {s.forms.map((f) => FORM_LABEL[f] ?? f).join(", ")}
            {ABOUT_LABEL(s.tags) && <span data-set-about={(s.tags ?? []).join(" ")}> · {ABOUT_LABEL(s.tags)}</span>} · <span data-origin={s.origin}>{ORIGIN_LABEL[s.origin]}</span>
          </span>
          <span className="block truncate text-xs text-muted">{s.description}</span>
        </span>
      </button>
      {open && <SetDetails s={s} onEdit={onEdit} onCopy={onCopy} />}
    </div>
  );
}

function SetDetails({ s, onEdit, onCopy }: { s: QSet; onEdit: () => void; onCopy: () => void }) {
  return (
    <div className="flex flex-col gap-3 border-t border-line/70 bg-paper/40 px-4 py-3 text-sm" data-set-details={s.id}>
      <div className="flex flex-wrap items-center gap-2">
        {s.read_only ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted">
            <Lock size={12} /> Reproduces a published instrument: read-only here. Copy it to adapt it, or edit its file by hand.
          </span>
        ) : (
          <button className="btn-ghost text-xs" onClick={onEdit}>
            <Pencil size={13} /> Edit{s.origin === "bundled" ? " (saves an override)" : ""}
          </button>
        )}
        <button className="btn-ghost text-xs" onClick={onCopy}>
          <Copy size={13} /> Copy as new
        </button>
      </div>
      {s.warning && (
        <Note tone="warn">
          <TriangleAlert size={14} className="mr-1 inline" /> {s.warning} <span className="text-xs opacity-80">(Shown to administrators only.)</span>
        </Note>
      )}
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-xs">
        {s.description && (
          <>
            <dt className="text-muted">Description</dt>
            <dd>{s.description}</dd>
          </>
        )}
        {(s.source_citation || s.reference) && (
          <>
            <dt className="text-muted">{s.read_only ? "Source" : "Reference"}</dt>
            <dd>
              {s.source_citation || s.reference}
              {s.url && (
                <>
                  {" "}
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-you hover:underline">
                    source
                  </a>
                </>
              )}
            </dd>
          </>
        )}
        {s.based_on && (
          <>
            <dt className="text-muted">Based on</dt>
            <dd>{s.based_on}</dd>
          </>
        )}
        {s.validated && s.validation_note && (
          <>
            <dt className="text-muted">Validation</dt>
            <dd>{s.validation_note}</dd>
          </>
        )}
        {s.scales.length > 0 && (
          <>
            <dt className="text-muted">Scales</dt>
            <dd className="flex flex-wrap gap-1">
              {s.scales.map((x) => (
                <code key={x} className="rounded bg-surface px-1">
                  scale_{x}
                </code>
              ))}
            </dd>
          </>
        )}
        <dt className="text-muted">Source</dt>
        <dd>{ORIGIN_LABEL[s.origin]}</dd>
        <dt className="text-muted">File</dt>
        <dd>
          <CopyField value={s.path} label={`file path of ${s.id}`} />
        </dd>
        {s.bundled_path && (
          <>
            <dt className="text-muted">Bundled file</dt>
            <dd>
              <CopyField value={s.bundled_path} label={`bundled file path of ${s.id}`} />
            </dd>
          </>
        )}
      </dl>
      {s.delete ? (
        <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs" data-delete-hint>
          <div className="mb-1 inline-flex items-center gap-1 font-medium">
            <Trash2 size={12} /> To delete, remove its file. {s.delete.effect}
          </div>
          <CopyField value={s.delete.command} label={`delete command for ${s.id}`} />
          <span className="mt-1 block text-muted">Then reload this page.</span>
        </div>
      ) : (
        <p className="text-xs text-muted">Bundled with HANI2: it cannot be deleted. A set of your own with the id <code>{s.id}</code> replaces it.</p>
      )}
      <QuestionTable questions={s.questions} />
    </div>
  );
}

export function QuestionTable({ questions }: { questions: any[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-muted">
          <tr>
            <th className="py-1 pr-2">#</th>
            <th className="py-1 pr-2">Id</th>
            <th className="py-1 pr-2">Type</th>
            <th className="py-1 pr-2">Question</th>
            <th className="py-1 pr-2">Scale</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((x, i) => (
            <tr key={`${x.id}-${i}`} className="border-t border-line/60 align-top">
              <td className="py-1 pr-2 text-muted">{i + 1}</td>
              <td className="py-1 pr-2">
                <code>{x.id}</code>
              </td>
              <td className="py-1 pr-2">{x.type}{x.required ? "" : " (optional)"}</td>
              <td className="py-1 pr-2">
                {x.text}
                {x.labels && <span className="block text-muted">{Object.entries(x.labels).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>}
                {x.options && <span className="block text-muted">Options: {x.options.map((o: any) => (typeof o === "object" ? o.label ?? o.value : o)).join(" · ")}</span>}
              </td>
              <td className="py-1 pr-2">
                {x.scale ? <code>{x.scale}</code> : ""}
                {x.reverse ? " (reversed)" : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SetEditor({ editing, set, ownDir, onClose, onSaved }: { editing: Editing; set?: QSet; ownDir: string; onClose: () => void; onSaved: (id: string) => void }) {
  const [text, setText] = useState(editing.text);
  const [problems, setProblems] = useState<string[] | null>(null);
  const original = editing.mode === "edit" ? editing.id : null;
  useEffect(() => {
    setProblems(null);
    const t = window.setTimeout(() => {
      api("/api/admin/questionnaire-library/check", { body: { text, original } }).then((r) => setProblems(r.problems)).catch((e) => setProblems([e.message]));
    }, 300);
    return () => window.clearTimeout(t);
  }, [text]);
  const save = async () => {
    try {
      const r = editing.mode === "edit"
        ? await api(`/api/admin/questionnaire-library/${encodeURIComponent(editing.id)}`, { method: "PUT", body: { text } })
        : await api("/api/admin/questionnaire-library", { body: { text } });
      toast(`Saved ${r.id} to ${r.path}`);
      onSaved(r.id);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const where =
    editing.mode === "new"
      ? `A new file in ${ownDir} (named after the id).`
      : set?.origin === "bundled"
        ? `Saving writes an override, ${ownDir}/${editing.id}.yaml; the bundled file is not changed. Deleting that file later restores the bundled version.`
        : set?.origin === "override"
          ? `Saving rewrites ${set.path}, which overrides the bundled set; deleting it restores the bundled version.`
          : `Saving rewrites ${set?.path ?? "its file"}.`;
  return (
    <div id="questionnaire-set-editor">
      <Group
        title={editing.mode === "edit" ? `Edit ${editing.id}` : editing.from ? `New set, copied from ${editing.from}` : "New set"}
        footer="Keys: id (letters, digits, _ and -), title, description, forms (pre_questionnaire, per_negotiation, post_session), tags (assistant, opponent: the party the questions are about; with both, write {{agent}} for the party and requires: agent), based_on, questions. Question types: likert5, likert7, yes_no, select (with options), text."
        actions={
          <button className="btn-ghost text-xs" onClick={onClose}>
            <X size={13} /> Cancel
          </button>
        }
      >
        <div className="px-4 pt-3 text-xs text-muted">{where}</div>
        {set?.warning && (
          <div className="px-4 pt-2">
            <Note tone="warn">{set.warning}</Note>
          </div>
        )}
        <div className="p-3">
          <TextArea label="Set (YAML)" value={text} rows={22} mono onChange={setText} />
        </div>
        {problems && problems.length > 0 && (
          <div className="flex items-start gap-2 bg-warn/10 px-4 py-2 text-sm text-warn" data-problems>
            <TriangleAlert size={15} className="mt-0.5 shrink-0" />
            <ul className="list-disc pl-4">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}
      </Group>
      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
        <span className="mr-auto truncate text-xs text-muted">{problems === null ? "Checking…" : problems.length ? "Fix the problems to save" : "Ready to save"}</span>
        <button className="btn-primary" onClick={save} disabled={!problems || problems.length > 0}>
          <Save size={15} /> Save set
        </button>
      </div>
    </div>
  );
}
