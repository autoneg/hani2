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
import { Select } from "../controls/Select";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { FormItemsEditor } from "./FormItemsEditor";
import { VALIDATED_SOURCE_TIP, ValidatedMark } from "../../ui/metricGroups";

type Form = "pre_questionnaire" | "per_negotiation" | "post_session";
export const FORMS: [Form, string, string][] = [
  ["pre_questionnaire", "Pre-questionnaire", "questionnaires/pre_questionnaire.yaml: once, before a participant's first negotiation (can set the participant type)"],
  ["per_negotiation", "After each negotiation", "questionnaires/per_negotiation.yaml: after every negotiation, the practice round included"],
  ["post_session", "Post-session", "questionnaires/post_session.yaml: once, after a study participant's last counted negotiation, before the completion link"],
];
const LAYER_NAME = (id?: string) =>
  !id || id === "none" ? "nowhere (no form)" : id === "bundled" ? "the bundled default" : id === "settings" ? "the settings folder" : id === "env.json" ? "a name in env.json" : id.startsWith("env:") ? `the ${id.slice(4)} environment variable` : id.startsWith("project:") ? `project ${id.slice(8)}` : `study ${id.slice(6)}`;

interface LibSet {
  id: string;
  title: string;
  description: string;
  reference: string;
  forms: string[];
  /** the parties its questions are about (assistant, opponent, both, or none) */
  tags: string[];
  questions: any[];
  source: string;
  /** checked against its source instrument (hani2.evaluation.catalog) */
  validated?: boolean;
  validation_note?: string;
  url?: string;
  /** a source warning from the registry (e.g. TAM items not checked against Davis, 1989); admin only */
  warning?: string;
}

/** a source warning of the bundled sets a form uses (from /api/admin/questionnaires/check) */
interface SetWarning {
  set: string;
  title: string;
  warning: string;
}

/** The source warnings of a form, one box per distinct text naming the sets it covers. Admin only:
 * never part of the participant's form. */
function SourceWarnings({ warnings, id }: { warnings?: SetWarning[]; id?: string }) {
  if (!warnings?.length) return null;
  const by = new Map<string, string[]>();
  for (const w of warnings) by.set(w.warning, [...(by.get(w.warning) ?? []), w.title]);
  return (
    <div data-testid="form-source-warning" id={id}>
      {[...by].map(([text, titles]) => (
        <Note tone="warn" key={text}>
          <TriangleAlert size={14} className="mr-1 inline" /> <b>Items not checked against the source</b> ({titles.join(", ")}): {text} <span className="text-muted">Shown to admins only; participants never see it.</span>
        </Note>
      ))}
    </div>
  );
}

/** the source warnings of a form's text (empty while loading or when it has none) */
function useFormWarnings(text: string | undefined) {
  const [w, setW] = useState<SetWarning[]>([]);
  useEffect(() => {
    if (!text?.trim()) return setW([]);
    let live = true;
    api("/api/admin/questionnaires/check", { body: { text } }).then((r) => live && setW(r.warnings ?? [])).catch(() => live && setW([]));
    return () => {
      live = false;
    };
  }, [text]);
  return w;
}

export function StudyForms() {
  const { layer } = useLayer();
  const [form, setForm] = useState<Form>("per_negotiation");
  const [d, setD] = useState<any>(null);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [showLib, setShowLib] = useState(false);
  const [mode, setMode] = useState<"items" | "yaml">("items");
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
  const effectiveWarnings = useFormWarnings(d?.active ? d.effective : "");
  const startFromInherited = () => {
    setText(d?.effective ?? "");
    setDirty(true);
  };
  return (
    <>
      <LayerPicker note="Each project and study can have its own forms; a study's file wins over its project's, which wins over the settings folder." />
      <ConsentSetting />
      <AllFormsSetting />
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
              <TriangleAlert size={14} className="mr-1 inline" /> {LAYER_NAME(d.source)} names this form, so it wins over every layer's file: edits here have no effect until it is unset{d.source === "env.json" ? " (Named form, below)" : " (an environment variable of the server cannot be changed here)"}.
            </Note>
          )}
          <NamedForm form={form} onChange={load} />
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
          <SourceWarnings warnings={effectiveWarnings} id="setting-form-effective-warning" />
          {d.problems?.length > 0 && <Note tone="warn">This layer's file has problems: {d.problems.join("; ")}</Note>}
          <Group
            title={d.exists ? "This layer's form (YAML)" : "New form for this layer (YAML)"}
            id="setting-form-editor"
            actions={
              <>
                <Segmented label="Edit as" value={mode} onChange={setMode} options={[["items", "Items"], ["yaml", "YAML"]]} />
                <button className="btn-ghost text-xs" onClick={() => setShowLib((v) => !v)}>
                  <Library size={13} /> {showLib ? "Hide" : "Add"} predefined questionnaires
                </button>
              </>
            }
          >
            {showLib && <LibraryPicker form={form} layer={layer.id} text={text} onText={(t) => (setText(t), setDirty(true))} />}
            {mode === "items" ? (
              <FormItemsEditor key={`${form}-${layer.id}`} form={form} text={text} onText={(t) => (setText(t), setDirty(true))} />
            ) : (
              <div className="p-3">
                <TextArea label="Form" value={text} rows={18} mono onChange={(v) => (setText(v), setDirty(true))} />
              </div>
            )}
          </Group>
          <Preview text={text} layer={layer.id} />
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

const ENV_KEY: Record<Form, string> = { pre_questionnaire: "pre_questionnaire", per_negotiation: "questionnaire", post_session: "post_questionnaire" };

/** The env.json name of a form at the chosen layer (``"pre_questionnaire": "expertise"``): a bundled or
 *  named form that wins over every layer's file. */
function NamedForm({ form, onChange }: { form: Form; onChange: () => void }) {
  const { layer } = useLayer();
  const [env, setEnv] = useState<any>(null);
  const [names, setNames] = useState<string[]>([]);
  const key = ENV_KEY[form];
  const load = () => api(`/api/admin/settings/env${lq(layer)}`).then(setEnv).catch(() => setEnv(null));
  useEffect(() => {
    load();
    api(`/api/admin/questionnaires/library${lq(layer)}`).then((r) => setNames(r.named_forms ?? [])).catch(() => setNames([]));
  }, [layer.id, form]);
  if (!env) return null;
  const own = env.own?.[key];
  const value = env.effective?.[key] ?? "";
  const set = async (v: string) => {
    try {
      if (v) await api(`/api/admin/settings/env${lq(layer)}`, { method: "PATCH", body: { [key]: v } });
      else {
        if (own !== undefined) await api(`/api/admin/settings/env${lq(layer)}&key=${key}`, { method: "DELETE" });
        // still named by a layer below: an empty name here unsets it for this layer
        const r = await api(`/api/admin/settings/env${lq(layer)}`);
        if (r?.effective?.[key]) await api(`/api/admin/settings/env${lq(layer)}`, { method: "PATCH", body: { [key]: "" } });
      }
      await load();
      onChange();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const opts = [...new Set([...names, ...(value ? [String(value)] : [])])];
  return (
    <Group title="Named form" id="setting-form-named" footer={`"${key}" in env.json: a form named here (a bundled one such as ${names.slice(0, 2).join(" or ") || "expertise"}, or a file in a questionnaires/ folder) wins over every layer's ${FORMS.find((f) => f[0] === form)![1].toLowerCase()} file.`}>
      <Row label="Use the named form" help="questionnaires.named" hint={`env.json → ${key}; empty: the layers' files decide`} overridden={own !== undefined && layer.kind !== "settings"} onReset={() => set("")}>
        <Select label="Use the named form" value={String(value)} onChange={set} options={[{ value: "", label: "None (the layers' files)" }, ...opts.map((n) => ({ value: n, label: n }))]} />
      </Row>
    </Group>
  );
}

/** ``questionnaires`` in env.json at the chosen layer: false switches every form off. */
function AllFormsSetting() {
  const { layer } = useLayer();
  const [env, setEnv] = useState<any>(null);
  const load = () => api(`/api/admin/settings/env${lq(layer)}`).then(setEnv).catch(() => setEnv(null));
  useEffect(() => {
    load();
  }, [layer.id]);
  if (!env) return null;
  const own = env.own?.questionnaires;
  const raw = env.effective?.questionnaires;
  const on = !(raw === false || ["0", "false", "no", "off"].includes(String(raw ?? "").toLowerCase()));
  const set = async (v: boolean) => {
    try {
      await api(`/api/admin/settings/env${lq(layer)}`, { method: "PATCH", body: { questionnaires: v } });
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const reset = async () => {
    try {
      await api(`/api/admin/settings/env${lq(layer)}&key=questionnaires`, { method: "DELETE" });
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <Group title="All questionnaires" id="setting-all-questionnaires" footer="questionnaires in env.json. A project or study can also switch them all off with Questionnaires: No in its defaults (Projects page); either wins over every form below and over the environment variables that name a form.">
      <Row id="forms-all" label="Ask the questionnaires" help="questionnaires" hint="Off: no pre, per-negotiation or post-session questionnaire at all here" overridden={own !== undefined && layer.kind !== "settings"} onReset={reset}>
        <Toggle label="Ask the questionnaires" value={on} onChange={set} />
      </Row>
    </Group>
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

/** the party a set is about, as a short chip text (``agent``: the party this layer's study evaluates) */
function aboutLabel(tags: string[] | undefined, agent?: string): string {
  const t = tags ?? [];
  if (t.includes("assistant") && t.includes("opponent")) return agent ? `About the ${agent} ({{agent}})` : "About the Assistant or the opponent";
  if (t.includes("assistant")) return "About the Assistant";
  if (t.includes("opponent")) return "About the opponent";
  return "";
}

/** a question text with ``{{agent}}`` / ``{{Agent}}`` filled in */
const withAgent = (text: string, agent: string) => String(text ?? "").replace(/\{\{\s*agent\s*\}\}/g, agent).replace(/\{\{\s*Agent\s*\}\}/g, agent.charAt(0).toUpperCase() + agent.slice(1));

function LibraryPicker({ form, layer, text, onText }: { form: Form; layer: string; text: string; onText: (t: string) => void }) {
  const [lib, setLib] = useState<LibSet[] | null>(null);
  const [agent, setAgent] = useState("assistant");
  const [kind, setKind] = useState("none");
  const [assistantSets, setAssistantSets] = useState(false);
  const [tip, setTip] = useState(VALIDATED_SOURCE_TIP);
  const [picked, setPicked] = useState<string[]>([]);
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api(`/api/admin/questionnaires/library${lq(layer)}`)
      .then((r) => (setLib(r.sets), r.agent && setAgent(r.agent), setKind(r.kind ?? "none"), r.validated_tooltip && setTip(r.validated_tooltip)))
      .catch((e) => toast(e.message, "error"));
  }, [layer]);
  // a HAN project's studies have no Assistant: the sets only about the Assistant are hidden
  const onlyAssistant = (s: LibSet) => (s.tags ?? []).includes("assistant") && !(s.tags ?? []).includes("opponent");
  const shown = useMemo(
    () => (lib ?? []).filter((s) => (all || s.forms.includes(form)) && (kind !== "opponent" || assistantSets || !onlyAssistant(s))),
    [lib, all, form, kind, assistantSets],
  );
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
        {kind === "opponent" && (
          <label className="inline-flex items-center gap-1.5" title="A HAN project (kind: opponent) plays without an Assistant, so sets only about the Assistant are hidden">
            <input type="checkbox" checked={assistantSets} onChange={(e) => setAssistantSets(e.target.checked)} /> Show sets about the Assistant
          </label>
        )}
      </div>
      <div className="flex flex-col divide-y divide-line rounded-lg border border-line">
        {shown.map((s) => (
          <div key={s.id} className="px-3 py-2">
            <label className="flex cursor-pointer items-start gap-2">
              <input type="checkbox" className="mt-1" checked={picked.includes(s.id)} onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.id] : p.filter((x) => x !== s.id)))} />
              <span className="min-w-0 flex-1">
                <span className="text-sm font-medium">{s.title}</span>
                {s.validated && <ValidatedMark tip={`${tip}${s.validation_note ? `: ${s.validation_note}` : ""}`} />}
                <span className="ml-2 text-xs text-muted">
                  {s.questions.length} question{s.questions.length === 1 ? "" : "s"}
                  {s.source === "settings" ? " · your own" : ""}
                </span>
                {aboutLabel(s.tags, agent) && (
                  <span className="ml-2 rounded-full border border-line px-1.5 py-px text-[11px] text-muted" data-set-about={(s.tags ?? []).join(" ") || "none"}>
                    {aboutLabel(s.tags, agent)}
                  </span>
                )}
                <span className="block text-xs text-muted">{s.description}</span>
                {s.warning && (
                  <span className="mt-1 flex items-start gap-1.5 rounded-md border border-warn/30 bg-warn/10 px-2 py-1 text-xs text-warn" data-testid="set-source-warning">
                    <TriangleAlert size={13} className="mt-0.5 shrink-0" />
                    <span>{s.warning}</span>
                  </span>
                )}
                {s.reference && (
                  <span className="block text-[11px] italic text-muted">
                    {s.reference}
                    {s.url && (
                      <>
                        {" "}
                        <a href={s.url} target="_blank" rel="noreferrer" className="not-italic text-you hover:underline" onClick={(e) => e.stopPropagation()}>
                          source
                        </a>
                      </>
                    )}
                  </span>
                )}
              </span>
              <button type="button" className="btn-ghost px-1.5 text-xs" onClick={(e) => (e.preventDefault(), setOpen(open === s.id ? null : s.id))}>
                {open === s.id ? "Hide" : "Items"}
              </button>
            </label>
            {open === s.id && (
              <ol className="ml-7 mt-1 list-decimal pl-4 text-xs text-muted">
                {s.questions.map((q: any) => (
                  <li key={q.id}>
                    <code>{q.id}</code> · {q.type}: {withAgent(q.text, agent)}
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

function Preview({ text, layer }: { text: string; layer: string }) {
  const [r, setR] = useState<{ problems: string[]; form: Questionnaire | null; warnings?: SetWarning[] } | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => {
      api(`/api/admin/questionnaires/check${lq(layer)}`, { body: { text } }).then(setR).catch((e) => setR({ problems: [e.message], form: null }));
    }, 300);
    return () => window.clearTimeout(t);
  }, [text, layer]);
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
      {r?.warnings?.length ? (
        <div className="px-4 pt-3">
          <SourceWarnings warnings={r.warnings} />
        </div>
      ) : null}
      <div className="px-4 py-3">
        {!r ? <Spinner /> : r.form ? <QuestionnaireFields key={text} q={r.form} submitLabel="Submit answers (preview)" onSubmit={() => toast("Preview only: nothing is saved")} /> : !r.problems.length && <span className="text-sm text-muted">{text.trim() ? "Switched off: participants get no form." : "Empty: this layer uses what it inherits."}</span>}
      </div>
    </Group>
  );
}
