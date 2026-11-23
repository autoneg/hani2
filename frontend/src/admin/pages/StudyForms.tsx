import { useEffect, useMemo, useState } from "react";
import { BookOpen, CircleSlash, Eye, FilePlus2, Library, RotateCcw, Save, TriangleAlert } from "lucide-react";
import { api } from "../../api";
import type { Questionnaire } from "../../types";
import { QuestionnaireFields } from "../../negotiate/ActionDock";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { LayerPicker, lq, shortPath, useLayer } from "../layer";
import { Segmented } from "../controls/Segmented";
import { TextArea } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";

type Form = "pre_questionnaire" | "per_negotiation" | "post_session";
export const FORMS: [Form, string, string][] = [
  ["pre_questionnaire", "Pre-questionnaire", "questionnaires/pre_questionnaire.yaml: once, before a participant's first negotiation (can set the participant type)"],
  ["per_negotiation", "After each negotiation", "questionnaires/per_negotiation.yaml: after every negotiation, the practice round included"],
  ["post_session", "Post-session", "questionnaires/post_session.yaml: once, after a study participant's last counted negotiation, before the completion link"],
];
const LAYER_NAME = (id?: string) =>
  !id || id === "none" ? "nowhere (no form)" : id === "bundled" ? "the bundled default" : id === "settings" ? "the settings folder" : id === "env.json" ? "a name in env.json" : id.startsWith("env:") ? `the ${id.slice(4)} environment variable` : id.startsWith("project:") ? `project ${id.slice(8)}` : `study ${id.slice(6)}`;

interface LibSet { id: string; title: string; description: string; reference: string; forms: string[]; questions: any[]; source: string }

export function StudyForms() {
  const { layer } = useLayer();
  const [form, setForm] = useState<Form>("per_negotiation");
  const [d, setD] = useState<any>(null);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [showLib, setShowLib] = useState(false);
  const load = () =>
    api(`/api/admin/settings/${form}${lq(layer)}`).then((r) => {
      setD(r);
      setText(r.exists ? r.text : "");
      setDirty(false);
    }).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    setD(null);
    setShowLib(false);
    load();
  }, [form, layer.id]);
  const save = async (t = text) => {
    try {
      await api(`/api/admin/settings/${form}${lq(layer)}`, { method: "PUT", body: { text: t } });
      toast(`Saved to ${layer.label}`);
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const remove = async () => {
    if (!confirm(`Remove ${layer.label}'s own ${FORMS.find((f) => f[0] === form)![1].toLowerCase()}? It then uses the form it inherits (if any).`)) return;
    try {
      await api(`/api/admin/settings/${form}${lq(layer)}`, { method: "DELETE" });
      toast("Removed");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const switchOff = () => {
    if (!confirm(`Switch this form off for ${layer.label}? Its own file becomes "enabled: false" (any questions in it are replaced).`)) return;
    save("enabled: false\n");
  };
  const startFromInherited = () => {
    setText(d?.effective ?? "");
    setDirty(true);
  };
  return (
    <>
      <LayerPicker note="Each project and study can have its own forms; a study's file wins over its project's, which wins over the settings folder." />
      <ConsentSetting />
      <div className="mb-4">
        <Segmented label="Form" value={form} onChange={setForm} options={FORMS.map(([k, l]) => [k, l])} />
        <p className="mt-1.5 px-1 text-xs text-muted">{FORMS.find((f) => f[0] === form)![2]}</p>
      </div>
      {!d ? (
        <Spinner />
      ) : (
        <>
          {d.overridden && (
            <Note tone="warn">
              <TriangleAlert size={14} className="mr-1 inline" /> {LAYER_NAME(d.source)} names this form, so it wins over every layer's file: edits here have no effect until it is unset.
            </Note>
          )}
          <Group title="In effect here" id="setting-form-source">
            <InfoRow label="Status" value={d.active ? `On: ${d.n_questions} question${d.n_questions === 1 ? "" : "s"}` : d.disabled ? "Switched off" : "Off (no form)"} />
            <InfoRow label="From" value={LAYER_NAME(d.source)} hint={shortPath(d.source_path)} />
            <Row label="This layer's own file" hint={d.exists ? "Edits below are saved to it." : "None: this layer uses what it inherits. Saving creates its own file."}>
              <div className="flex flex-wrap justify-end gap-1">
                {!d.exists && d.effective && (
                  <button className="btn-ghost text-xs" onClick={startFromInherited}>
                    <FilePlus2 size={13} /> Copy the inherited form
                  </button>
                )}
                {!(d.exists && d.disabled) && (
                  <button className="btn-ghost text-xs" onClick={switchOff}>
                    <CircleSlash size={13} /> Switch off here
                  </button>
                )}
                {d.exists && (
                  <button className="btn-ghost text-xs text-bad" onClick={remove}>
                    <RotateCcw size={13} /> Remove this layer's file
                  </button>
                )}
              </div>
            </Row>
          </Group>
          {d.problems?.length > 0 && <Note tone="warn">This layer's file has problems: {d.problems.join("; ")}</Note>}
          <Group
            title={d.exists ? "This layer's form (YAML)" : "New form for this layer (YAML)"}
            id="setting-form-editor"
            actions={
              <button className="btn-ghost text-xs" onClick={() => setShowLib((v) => !v)}>
                <Library size={13} /> {showLib ? "Hide" : "Add"} predefined questionnaires
              </button>
            }
          >
            {showLib && <LibraryPicker form={form} text={text} onText={(t) => (setText(t), setDirty(true))} />}
            <div className="p-3">
              <TextArea label="Form" value={text} rows={18} mono onChange={(v) => (setText(v), setDirty(true))} />
            </div>
          </Group>
          <Preview text={text} />
          <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
            <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved changes · will be saved to ${layer.label}` : `Saving to ${layer.label}`}</span>
            <button className="btn-primary" onClick={() => save()} disabled={!dirty}>
              <Save size={15} /> Save
            </button>
          </div>
        </>
      )}
    </>
  );
}

/** auth.participant_consent at the chosen layer: Prolific and online participants see the consent form in the session. */
function ConsentSetting() {
  const { layer } = useLayer();
  const [env, setEnv] = useState<any>(null);
  const load = () => api(`/api/admin/settings/env${lq(layer)}`).then(setEnv).catch(() => setEnv(null));
  useEffect(() => {
    load();
  }, [layer.id]);
  if (!env) return null;
  const own = env.own?.auth?.participant_consent;
  const value = !!env.effective?.auth?.participant_consent;
  const set = async (v: boolean) => {
    try {
      await api(`/api/admin/settings/env${lq(layer)}`, { method: "PATCH", body: { auth: { participant_consent: v } } });
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const reset = async () => {
    try {
      await api(`/api/admin/settings/env${lq(layer)}&key=auth.participant_consent`, { method: "DELETE" });
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <Group title="Consent" id="setting-participant-consent" footer="The consent text is edited on the Texts page (Consent form). Logged-in users consent on the consent page instead (General → Require consent).">
      <Row
        id="participant-consent"
        label="Ask study participants for consent"
        hint="Prolific and online / lab participants see the consent form before their first negotiation; declining ends the study for them without a completion link."
        overridden={own !== undefined && layer.kind !== "settings"}
        onReset={reset}
      >
        <Toggle label="Ask study participants for consent" value={value} onChange={set} />
      </Row>
    </Group>
  );
}

function LibraryPicker({ form, text, onText }: { form: Form; text: string; onText: (t: string) => void }) {
  const [lib, setLib] = useState<LibSet[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api("/api/admin/questionnaires/library").then((r) => setLib(r.sets)).catch((e) => toast(e.message, "error"));
  }, []);
  const shown = useMemo(() => (lib ?? []).filter((s) => all || s.forms.includes(form)), [lib, all, form]);
  const add = async () => {
    try {
      const r = await api("/api/admin/questionnaires/compose", { body: { text, sets: picked, form } });
      onText(r.text);
      setPicked([]);
      toast(`Added ${r.added.length} question${r.added.length === 1 ? "" : "s"}` + (r.skipped.length ? `; skipped ${r.skipped.length} already in the form` : "") + ". Review and save.");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  if (!lib) return <Spinner />;
  return (
    <div className="border-b border-line px-4 py-3" id="setting-form-library">
      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-muted">
        <span className="inline-flex items-center gap-1">
          <BookOpen size={13} /> Pick sets to add to the form below; you can edit every question afterwards.
        </span>
        <label className="ml-auto inline-flex items-center gap-1.5">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show sets meant for other forms
        </label>
      </div>
      <div className="flex flex-col divide-y divide-line rounded-lg border border-line">
        {shown.map((s) => (
          <div key={s.id} className="px-3 py-2">
            <label className="flex cursor-pointer items-start gap-2">
              <input type="checkbox" className="mt-1" checked={picked.includes(s.id)} onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.id] : p.filter((x) => x !== s.id)))} />
              <span className="min-w-0 flex-1">
                <span className="text-sm font-medium">{s.title}</span>
                <span className="ml-2 text-xs text-muted">
                  {s.questions.length} question{s.questions.length === 1 ? "" : "s"}
                  {s.source === "settings" ? " · your own" : ""}
                </span>
                <span className="block text-xs text-muted">{s.description}</span>
                {s.reference && <span className="block text-[11px] italic text-muted">{s.reference}</span>}
              </span>
              <button type="button" className="btn-ghost px-1.5 text-xs" onClick={(e) => (e.preventDefault(), setOpen(open === s.id ? null : s.id))}>
                {open === s.id ? "Hide" : "Items"}
              </button>
            </label>
            {open === s.id && (
              <ol className="ml-7 mt-1 list-decimal pl-4 text-xs text-muted">
                {s.questions.map((q: any) => (
                  <li key={q.id}>
                    <code>{q.id}</code> · {q.type}: {q.text}
                    {q.labels ? ` (${Object.values(q.labels).join(" … ")})` : ""}
                  </li>
                ))}
              </ol>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-end">
        <button className="btn-primary text-sm" disabled={!picked.length} onClick={add}>
          <FilePlus2 size={14} /> Add {picked.length || ""} set{picked.length === 1 ? "" : "s"} to the form
        </button>
      </div>
    </div>
  );
}

function Preview({ text }: { text: string }) {
  const [r, setR] = useState<{ problems: string[]; form: Questionnaire | null } | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => {
      api("/api/admin/questionnaires/check", { body: { text } }).then(setR).catch((e) => setR({ problems: [e.message], form: null }));
    }, 300);
    return () => window.clearTimeout(t);
  }, [text]);
  return (
    <Group
      title={
        <span className="inline-flex items-center gap-1.5">
          <Eye size={13} /> Preview
        </span>
      }
      id="setting-form-preview"
    >
      {r?.problems?.length ? (
        <div className="flex items-start gap-2 bg-warn/10 px-4 py-2 text-sm text-warn">
          <TriangleAlert size={15} className="mt-0.5 shrink-0" />
          <span>{r.problems.join("; ")}</span>
        </div>
      ) : null}
      <div className="px-4 py-3">
        {!r ? <Spinner /> : r.form ? <QuestionnaireFields key={text} q={r.form} submitLabel="Submit answers (preview)" onSubmit={() => toast("Preview only: nothing is saved")} /> : !r.problems.length && <span className="text-sm text-muted">{text.trim() ? "Switched off: participants get no form." : "Empty: this layer uses what it inherits."}</span>}
      </div>
    </Group>
  );
}
