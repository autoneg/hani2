import { useEffect, useMemo, useState } from "react";
import { Copy, Eye, FilePlus2, RotateCcw, Save, TriangleAlert } from "lucide-react";
import { api } from "../../api";
import { Markdown } from "../../ui/Markdown";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { Disclosure } from "../Disclosure";
import { LayerPicker, lq, shortPath, useLayer } from "../layer";
import { Segmented } from "../controls/Segmented";
import { Select } from "../controls/Select";
import { TextArea } from "../controls/TextField";
import { Note, Spinner } from "../schema";
import { copyText, toast } from "../toast";

type Kind = "announcements" | "consent" | "scenario_sets" | "scenario_order";
export const TEXT_KINDS: [Kind, string, string][] = [
  ["announcements", "Welcome text", "announcements.md, shown before the first negotiation (Markdown, {{variables}})"],
  ["consent", "Consent form", "consent.md, shown on registration and on the consent page (Markdown, {{variables}})"],
  ["scenario_sets", "Scenario sets", "scenario_sets.yaml, the named lists of scenario types (or use Scenario sets)"],
  ["scenario_order", "Custom order", "scenario_order.txt, one scenario type per line (the Custom set)"],
];
const LAYER_NAME = (id?: string) => (!id ? "" : id === "bundled" ? "the bundled default" : id === "settings" ? "the settings folder" : id.startsWith("project:") ? `project ${id.slice(8)}` : `study ${id.slice(6)}`);

function useStudies() {
  const { info } = useLayer();
  return info.layers.filter((l) => l.kind === "study").map((l) => `${l.project}/${l.study}`);
}

export function Texts() {
  const { layer, info } = useLayer();
  const [kind, setKind] = useState<Kind>("announcements");
  const [d, setD] = useState<any>(null);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const studies = useStudies();
  const ownStudy = layer.kind === "study" ? `${layer.project}/${layer.study}` : null;
  const [previewStudy, setPreviewStudy] = useState<string>("");
  const load = () =>
    api(`/api/admin/settings/${kind}${lq(layer)}`).then((r) => {
      setD(r);
      setText(r.exists === false ? (r.effective ?? "") : (r.text ?? ""));
      setDirty(false);
    }).catch((e) => toast(e.message, "error"));
  useEffect(() => {
    setD(null);
    load();
  }, [kind, layer.id]);
  const candidates = layer.kind === "project" ? studies.filter((s) => s.startsWith(`${layer.project}/`)) : studies;
  const study = ownStudy ?? (previewStudy || info.bound?.slice(6) || "");
  const own = d?.exists !== false;
  const markdown = kind === "announcements" || kind === "consent";
  const save = async () => {
    try {
      await api(`/api/admin/settings/${kind}${lq(layer)}`, { method: "PUT", body: { text } });
      toast(`Saved to ${layer.label}`);
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const remove = async () => {
    if (!confirm(`Remove this layer's own ${TEXT_KINDS.find((k) => k[0] === kind)![1].toLowerCase()}? ${layer.label} then uses the inherited text.`)) return;
    try {
      await api(`/api/admin/settings/${kind}${lq(layer)}`, { method: "DELETE" });
      toast("Removed; the inherited text is used");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <>
      <LayerPicker />
      <div className="mb-4">
        <Segmented label="Text" value={kind} onChange={setKind} options={TEXT_KINDS.map(([k, l]) => [k, l])} />
        <p className="mt-1.5 px-1 text-xs text-muted">{TEXT_KINDS.find((k) => k[0] === kind)![2]}</p>
      </div>
      {!d ? (
        <Spinner />
      ) : (
        <>
          <Group title="Source">
            <InfoRow id="text-source" label="In effect here" value={d.source ? `from ${LAYER_NAME(d.source)}` : own ? "this layer" : "inherited"} hint={shortPath(d.source_path)} />
            <Row label="This layer's own file" hint={own ? "Edits below are saved to it." : "None: the text below is inherited. Saving creates this layer's own copy."}>
              {own && layer.kind !== "settings" ? (
                <button className="btn-ghost text-xs text-bad" onClick={remove}>
                  <RotateCcw size={13} /> Use the inherited text
                </button>
              ) : !own ? (
                <span className="inline-flex items-center gap-1 text-xs text-muted">
                  <FilePlus2 size={13} /> not set
                </span>
              ) : null}
            </Row>
          </Group>
          <Group title={own ? "Text" : "Inherited text (edit to override)"} id="setting-text-editor">
            <div className="p-3">
              <TextArea label="Text" value={text} rows={16} mono onChange={(v) => (setText(v), setDirty(true))} />
            </div>
          </Group>
          {markdown && <Preview text={text} layer={layer.id} study={study} candidates={ownStudy ? null : candidates} setStudy={setPreviewStudy} />}
          <InEffect version={d} />
          <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
            <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved changes · will be saved to ${layer.label}` : `Saving to ${layer.label}`}</span>
            <button className="btn-primary" onClick={save} disabled={!dirty && own}>
              <Save size={15} /> Save
            </button>
          </div>
        </>
      )}
    </>
  );
}

function Preview({ text, layer, study, candidates, setStudy }: { text: string; layer: string; study: string; candidates: string[] | null; setStudy: (s: string) => void }) {
  const [r, setR] = useState<any>(null);
  useEffect(() => {
    const t = window.setTimeout(() => {
      api("/api/admin/templates/preview", { body: { text, layer, ...(study ? { study } : {}) } })
        .then(setR)
        .catch((e) => setR({ error: e.message }));
    }, 300);
    return () => window.clearTimeout(t);
  }, [text, layer, study]);
  return (
    <>
      <Group
        title={
          <span className="inline-flex items-center gap-1.5">
            <Eye size={13} /> Preview
          </span>
        }
        actions={
          candidates && (
            <Select label="Preview for study" value={study} onChange={setStudy} options={[{ value: "", label: "No study" }, ...candidates.map((s) => ({ value: s, label: `as study ${s}` }))]} />
          )
        }
        id="setting-text-preview"
      >
        {r?.unknown?.length > 0 && (
          <div className="flex items-start gap-2 bg-warn/10 px-4 py-2 text-sm text-warn">
            <TriangleAlert size={15} className="mt-0.5 shrink-0" />
            <span>
              Unknown variables (left as written): {r.unknown.map((u: string) => <code key={u} className="mx-0.5 rounded bg-warn/15 px-1">{`{{${u}}}`}</code>)}
            </span>
          </div>
        )}
        <div className="px-4 py-3">{r?.error ? <span className="text-sm text-bad">{r.error}</span> : r ? <Markdown text={r.rendered} /> : <Spinner />}</div>
      </Group>
      {r?.variables && <Group><Disclosure id="text-variables" label="Available variables" hint="Every {{variable}} with its value for this preview" value={String(Object.keys(r.variables).length)} title="Variables" render={() => <Variables vars={r.variables} desc={r.descriptions ?? {}} />} /></Group>}
    </>
  );
}

function Variables({ vars, desc }: { vars: Record<string, string>; desc: Record<string, string> }) {
  const names = useMemo(() => Object.keys(vars).sort((a, b) => (a in desc ? 0 : 1) - (b in desc ? 0 : 1) || a.localeCompare(b)), [vars]);
  return (
    <>
      <Note>Write a variable as <code>{"{{name}}"}</code>. Custom keys of project.yaml and study.yaml become <code>project_&lt;key&gt;</code> and <code>study_&lt;key&gt;</code>.</Note>
      <Group>
        {names.map((n) => (
          <Row key={n} label={<code className="text-[0.8rem]">{`{{${n}}}`}</code>} hint={desc[n] ?? "Custom key"}>
            <span className="max-w-[16rem] truncate text-sm text-muted">{vars[n] || "—"}</span>
            <button className="btn-ghost px-1.5" aria-label={`Copy {{${n}}}`} onClick={() => copyText(`{{${n}}}`)}>
              <Copy size={13} />
            </button>
          </Row>
        ))}
      </Group>
    </>
  );
}

/** Which layer each text comes from, for one study. */
function InEffect({ version }: { version: any }) {
  const studies = useStudies();
  const { info } = useLayer();
  const [study, setStudy] = useState<string>(info.bound?.slice(6) ?? studies[0] ?? "");
  const [rows, setRows] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!study) return;
    Promise.all(TEXT_KINDS.map(([k]) => api(`/api/admin/settings/${k}${lq(`study:${study}`)}`).then((r) => [k, r] as const).catch(() => [k, null] as const))).then((x) => setRows(Object.fromEntries(x)));
  }, [study, version]);
  if (!studies.length) return null;
  return (
    <Group title="In effect for a study" actions={<Select label="Study" value={study} onChange={setStudy} options={studies} />} footer="Lookup order: study, project, settings folder, bundled default; the first file found is used." id="setting-texts-in-effect">
      {TEXT_KINDS.map(([k, l]) => (
        <InfoRow key={k} label={l} value={rows[k] ? `from ${LAYER_NAME(rows[k].source) || "?"}` : "…"} />
      ))}
    </Group>
  );
}
