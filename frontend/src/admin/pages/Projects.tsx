import { useEffect, useState } from "react";
import { BookOpen, FlaskConical, FolderKanban, Info, Plus, Save } from "lucide-react";
import { api } from "../../api";
import { Markdown } from "../../ui/Markdown";
import { Group } from "../Group";
import { InfoRow, Row, Tile } from "../Row";
import { Disclosure } from "../Disclosure";
import { useNav } from "../Nav";
import { shortPath, useLayer } from "../layer";
import { BASE } from "../../router";
import { CopyField } from "../CopyField";
import { Select } from "../controls/Select";
import { Stepper } from "../controls/Stepper";
import { TextArea, TextField } from "../controls/TextField";
import { Tags } from "../controls/Tags";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";

const PROJECT_FIELDS = ["name", "full_name", "short_description", "link", "year", "kind", "organizer", "contact"];
const STUDY_FIELDS = ["name", "project", "type", "title", "link", "year", "start", "end", "prolific_study_id", "completion_code", "completion_url", "end_text", "organizer", "contact"];
const INFO_KEYS = ["path", "legacy", "participants", "results_rows", "default", "links", "yaml", "studies", "scheduling_effective", "errors"];
const KINDS = [
  { value: "none", label: "Research (none)" },
  { value: "opponent", label: "Opponents are evaluated" },
  { value: "assistant", label: "Assistants are evaluated" },
];
const TYPES = [
  { value: "prolific", label: "Prolific" },
  { value: "online", label: "Online (link)" },
  { value: "lab", label: "Lab (in person)" },
];
const LINK_LABELS: Record<string, [string, string]> = {
  prolific: ["Prolific study URL", "Paste into Prolific's study URL; Prolific fills the placeholders"],
  participant: ["Participant link", "Replace <PARTICIPANT_ID> with each participant's id"],
  session_code: ["Lab session link", "Replace <SESSION_CODE> with the code you hand out"],
  play: ["Play link", "Opens the study without an account"],
  app: ["App link", "Participants with accounts log in here"],
};

/** Split a GET payload into the editable data (round-tripping unknown keys, which are text variables). */
function dataOf(d: any, fields: string[]) {
  const out: any = {};
  for (const [k, v] of Object.entries(d)) if (!INFO_KEYS.includes(k) && k !== "name" && k !== "project") out[k] = v;
  for (const f of fields) if (out[f] === "" || out[f] == null) delete out[f];
  return out;
}
const extraKeys = (data: any, fields: string[], nested: string) => Object.keys(data).filter((k) => !fields.includes(k) && k !== nested && k !== "scheduling");

export const PROJECT_ENTRIES = [
  { id: "projects-list", label: "Projects", hint: "Every project and its studies; open a study for its participant links (Prolific URL, play, online and lab links) and Assistant balance", keywords: "participant links copy url prolific" },
  { id: "project-new", label: "New project", hint: "Create a project (project.yaml)" },
];

export function Projects() {
  const [d, setD] = useState<any>(null);
  const [name, setName] = useState("");
  const nav = useNav();
  const { reload } = useLayer();
  const load = () => api("/api/admin/projects").then(setD);
  useEffect(() => {
    load();
  }, []);
  if (!d) return <Spinner />;
  const create = async () => {
    try {
      await api(`/api/admin/projects/${encodeURIComponent(name)}`, { method: "PUT", body: { data: { kind: "none" } } });
      toast(`Created project ${name}`);
      setName("");
      await load();
      reload();
      nav.push({ title: name, render: () => <ProjectView name={name} /> });
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <>
      <Group title="Projects" footer={d.default_study ? `Plain URLs (without /s/<project>/<study>) use the default study ${d.default_study}.` : "Plain URLs (without /s/<project>/<study>) use no study."} id="setting-projects-list">
        {d.projects.map((p: any) => (
          <Disclosure
            key={p.name}
            icon={<Tile icon={FolderKanban} color={p.name === "default" ? "bg-muted" : "bg-you"} />}
            label={p.full_name ? `${p.name} — ${p.full_name}` : p.name}
            hint={[p.kind !== "none" && KINDS.find((k) => k.value === p.kind)?.label, p.year, p.short_description].filter(Boolean).join(" · ") || (p.name === "default" ? "The default project (its settings are the settings folder)" : undefined)}
            value={`${p.studies.length} ${p.studies.length === 1 ? "study" : "studies"}`}
            title={p.name}
            render={() => <ProjectView name={p.name} />}
          />
        ))}
      </Group>
      <Group title="New project" footer="Letters, digits, '.', '_' and '-'." id="setting-project-new">
        <Row label="Project name" hint="Short name used in URLs, e.g. HI2027">
          <TextField label="New project name" value={name} onChange={setName} className="w-44" placeholder="HI2027" />
          <button className="btn-primary" disabled={!name} onClick={create}>
            <Plus size={15} /> Create
          </button>
        </Row>
      </Group>
    </>
  );
}

/* ---------- shared editors ---------- */
/** ``GET /api/admin/scheduling-methods``: the methods of each dimension and the defaults (fetched once). */
let methods: Promise<any> | null = null;
function useScheduling() {
  const [m, setM] = useState<any>(undefined);
  useEffect(() => {
    methods ??= api("/api/admin/scheduling-methods");
    methods.then(setM).catch((e) => (methods = null, toast(e.message, "error"), setM(null)));
  }, []);
  return m;
}

/** How each dimension is scheduled: this file's choice, else ``inherit`` (``effective``: what the study uses). */
function SchedulingGroup({ value, onChange, inherit, effective }: { value: any; onChange: (v: any) => void; inherit: string; effective?: Record<string, string> }) {
  const m = useScheduling();
  if (!m) return m === null ? null : <Spinner />;
  const v = value ?? {};
  const dims: [string, string][] = [["opponents", "Opponents"], ["assistants", "Assistants"], ["scenarios", "Scenarios"]];
  return (
    <Group title="Scheduling" footer={`How HANI2 assigns each human. “${inherit}” keeps the value from the ${inherit === "Default" ? "server default" : "project"}.`} id="setting-scheduling">
      {dims.map(([k, l]) => {
        const opts = m.dimensions?.[k] ?? [];
        const cur = opts.find((o: any) => o.key === v[k]);
        // what an unset dimension uses (the study's effective value is its own once it sets one)
        const inh = v[k] ? undefined : opts.find((o: any) => o.key === (effective?.[k] ?? m.defaults?.[k]));
        return (
          <Row key={k} id={`scheduling-${k}`} label={l} hint={cur ? cur.summary : inh?.summary} overridden={!!v[k]} onReset={() => { const n = { ...v }; delete n[k]; onChange(n); }}>
            <Select
              label={`${l} scheduling`}
              value={v[k] ?? ""}
              onChange={(x) => {
                const n = { ...v };
                if (x) n[k] = x;
                else delete n[k];
                onChange(n);
              }}
              options={[{ value: "", label: `${inherit}${inh ? ` (${inh.title})` : ""}` }, ...opts.map((o: any) => ({ value: o.key, label: o.title }))]}
            />
          </Row>
        );
      })}
      <Disclosure id="scheduling-about" icon={<Info size={16} className="text-you" />} label="About these methods" hint="What each method does, with examples, advantages and disadvantages" title="Scheduling methods" render={() => <SchedulingAbout m={m} />} />
    </Group>
  );
}

function SchedulingAbout({ m }: { m: any }) {
  return (
    <>
      {Object.entries(m.dimensions ?? {}).map(([dim, opts]: any) => (
        <section key={dim} className="mb-8">
          <h2 className="mb-3 text-lg font-semibold capitalize">{dim}</h2>
          {opts.map((o: any) => (
            <Group key={o.key} title={<>{o.title} {m.defaults?.[dim] === o.key && <span className="ml-1 rounded bg-you/10 px-1.5 text-[0.68rem] text-you">default</span>}</>}>
              <div className="px-4 py-3">
                <p className="mb-2 text-sm text-muted">{o.summary}</p>
                <Markdown math text={o.details ?? ""} />
              </div>
            </Group>
          ))}
        </section>
      ))}
    </>
  );
}

/** The defaults a project gives its studies (``defaults``) or a study's overrides (``overrides``). Empty = inherit. */
function DefaultsGroup({ title, value, onChange, meta, inherit, footer }: { title: string; value: any; onChange: (v: any) => void; meta: any; inherit: string; footer?: string }) {
  const v = value ?? {};
  const put = (k: string, x: any) => {
    const n = { ...v };
    if (x === null || x === undefined || x === "" || (Array.isArray(x) && !x.length)) delete n[k];
    else n[k] = x;
    onChange(n);
  };
  const tri = (k: string) => (
    <Select label={k} value={v[k] === undefined ? "" : v[k] ? "yes" : "no"} onChange={(x) => put(k, x === "" ? null : x === "yes")} options={[{ value: "", label: inherit }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} />
  );
  const num = (k: string, step = 1) => <Stepper label={k} value={v[k] ?? null} nullable placeholder={inherit.toLowerCase()} step={step} min={0} onChange={(x) => put(k, x)} />;
  const sets = Object.keys(meta?.scenario_sets ?? {});
  return (
    <Group title={title} footer={footer ?? `Empty fields keep the ${inherit.toLowerCase()} value.`}>
      <Row label="Scenario set" hint="The scenario types and their order">
        <Select label="Scenario set" value={v.scenario_set ?? ""} onChange={(x) => put("scenario_set", x)} options={[{ value: "", label: inherit }, ...sets]} />
      </Row>
      <Row label="Strict scenarios" hint="strict_scenarios: serve saved scenarios only; a missing or broken pool is an error, never a generated scenario">{tri("strict_scenarios")}</Row>
      <Row label="Counted negotiations" hint="n_required: negotiations per participant">{num("n_required")}</Row>
      <Row label="Practice round" hint="A first negotiation that does not count">{tri("practice")}</Row>
      <Row label="Practice time limit (s)">{num("practice_time_limit", 30)}</Row>
      <Row label="Counted time limit (s)">{num("counted_time_limit", 30)}</Row>
      <Row label="Time limit (s)" hint="Per negotiation, outside Prolific studies">{num("time_limit", 30)}</Row>
      <Row label="Rounds" hint="n_steps">{num("n_steps", 10)}</Row>
      <Row label="Expected minutes" hint="minutes, shown in texts as {{minutes}}">{num("minutes", 5)}</Row>
      <Row label="Participant's role" hint="role_rule">
        <Select label="Participant's role" value={v.role_rule ?? ""} onChange={(x) => put("role_rule", x)} options={[{ value: "", label: inherit }, ...Object.keys(meta?.role_rules ?? { auto: 1, index: 1, roles: 1, alternate: 1, random: 1 })]} />
      </Row>
      <Row label="Preferred roles" hint="human_roles, for the roles rule">
        <Tags label="Preferred roles" value={v.human_roles} onChange={(x) => put("human_roles", x)} placeholder="Buyer" />
      </Row>
      <InfoRow label="Opponents and Assistants" value={[v.opponents && `opponents: ${[].concat(v.opponents).join(", ")}`, v.assistants && `assistants: ${[].concat(v.assistants).join(", ")}`].filter(Boolean).join(" · ") || inherit} hint="Choose the pools in Opponents and Assistants (pick this layer there)" />
    </Group>
  );
}

function ExtraGroup({ data, keys, onChange, prefix }: { data: any; keys: string[]; onChange: (k: string, v: any) => void; prefix: string }) {
  const [k, setK] = useState("");
  return (
    <Group title="Custom variables" footer={`Other keys of the file; texts use them as {{${prefix}_<key>}}.`}>
      {keys.map((x) => (
        <Row key={x} label={<code className="text-[0.8rem]">{x}</code>} hint={`{{${prefix}_${x}}}`}>
          {typeof data[x] === "object" ? <span className="text-xs text-muted">{JSON.stringify(data[x])}</span> : <TextField label={x} value={String(data[x] ?? "")} onChange={(v) => onChange(x, v)} commit="blur" className="w-52" />}
          <button className="btn-ghost px-1.5 text-xs text-bad" onClick={() => onChange(x, undefined)}>Remove</button>
        </Row>
      ))}
      <Row label="Add a variable">
        <TextField label="New variable name" value={k} onChange={setK} className="w-40" placeholder="sponsor" />
        <button className="btn-secondary" disabled={!/^[A-Za-z0-9_]+$/.test(k) || keys.includes(k)} onClick={() => (onChange(k, ""), setK(""))}>
          <Plus size={14} /> Add
        </button>
      </Row>
    </Group>
  );
}

function SaveRow({ dirty, save, where }: { dirty: boolean; save: () => void; where: string }) {
  return (
    <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
      <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved changes to ${where}` : where}</span>
      <button className="btn-primary" onClick={save} disabled={!dirty}>
        <Save size={15} /> Save
      </button>
    </div>
  );
}

/* ---------- a project ---------- */
function ProjectView({ name }: { name: string }) {
  const [d, setD] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  const [meta, setMeta] = useState<any>(null);
  const [newStudy, setNewStudy] = useState({ name: "", type: "prolific" });
  const nav = useNav();
  const { reload } = useLayer();
  const load = () =>
    api(`/api/admin/projects/${encodeURIComponent(name)}`).then((r) => {
      setD(r);
      setData(dataOf(r, PROJECT_FIELDS));
      setDirty(false);
    });
  useEffect(() => {
    load();
    api("/api/admin/meta").then(setMeta).catch(() => {});
  }, [name]);
  if (!d || !data) return <Spinner />;
  const set = (k: string, v: any) => {
    setDirty(true);
    setData((x: any) => {
      const n = { ...x };
      if (v === undefined) delete n[k];
      else n[k] = v;
      return n;
    });
  };
  const save = async () => {
    try {
      await api(`/api/admin/projects/${encodeURIComponent(name)}`, { method: "PUT", body: { data } });
      toast("Saved project.yaml");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const isDefault = name === "default";
  return (
    <>
      <div className="mb-5 flex items-center gap-3">
        <Tile icon={FolderKanban} color="bg-you" size={20} />
        <div>
          <div className="text-lg font-semibold">{data.full_name || name}</div>
          <div className="text-xs text-muted">{shortPath(d.path) || (isDefault ? "default project: settings folder" : "")}</div>
        </div>
      </div>
      {d.errors?.length > 0 && <Note tone="warn">{d.errors.join(" · ")}</Note>}
      {isDefault && <Note>The default project uses the settings folder as its settings layer; its studies include the old experiment folders. It has no project.yaml to edit.</Note>}
      <Group title="Project" footer="project.yaml">
        <InfoRow label="Name" value={name} hint="{{project_name}}; the folder name" />
        <Row label="Full name" hint="{{project_full_name}}"><TextField label="Full name" value={data.full_name} onChange={(v) => set("full_name", v)} /></Row>
        <Row label="Short description" hint="{{project_short_description}}"><TextField label="Short description" value={data.short_description} onChange={(v) => set("short_description", v)} /></Row>
        <Row label="Link" hint="{{project_link}}"><TextField label="Link" value={data.link} onChange={(v) => set("link", v)} placeholder="https://…" /></Row>
        <Row label="Year" hint="{{project_year}}"><Stepper label="Year" value={data.year ?? null} nullable min={2000} max={2100} onChange={(v) => set("year", v ?? undefined)} /></Row>
        <Row label="Kind" hint="What the project evaluates"><Select label="Kind" value={data.kind ?? "none"} onChange={(v) => set("kind", v)} options={KINDS} /></Row>
        <Row label="Organizer" hint="{{organizer}}"><TextField label="Organizer" value={data.organizer} onChange={(v) => set("organizer", v)} /></Row>
        <Row label="Contact" hint="{{contact}}"><TextField label="Contact" value={data.contact} onChange={(v) => set("contact", v)} placeholder="lab@example.org" /></Row>
      </Group>
      <DefaultsGroup title="Defaults for its studies" value={data.defaults} onChange={(v) => set("defaults", v)} meta={meta} inherit="Default" />
      <SchedulingGroup value={data.scheduling} onChange={(v) => set("scheduling", v)} inherit="Default" />
      <ExtraGroup data={data} keys={extraKeys(data, PROJECT_FIELDS, "defaults")} onChange={set} prefix="project" />
      <Group title={`Studies (${d.studies.length})`}>
        {d.studies.map((s: any) => (
          <Disclosure
            key={s.name}
            icon={<Tile icon={FlaskConical} color={s.type === "prolific" ? "bg-good" : s.type === "online" ? "bg-opponent" : "bg-warn"} />}
            label={s.title ? `${s.name} — ${s.title}` : s.name}
            hint={[TYPES.find((t) => t.value === s.type)?.label, s.start && `${s.start}${s.end ? ` → ${s.end}` : ""}`, s.default && "default study", s.legacy && "experiment folder"].filter(Boolean).join(" · ")}
            value={`${s.participants} participants`}
            title={s.name}
            render={() => <StudyView project={name} study={s.name} />}
          />
        ))}
        <Row label="New study" hint="Letters, digits, '.', '_' and '-'">
          <TextField label="New study name" value={newStudy.name} onChange={(v) => setNewStudy({ ...newStudy, name: v })} className="w-36" placeholder="run-01" />
          <Select label="New study type" value={newStudy.type} onChange={(v) => setNewStudy({ ...newStudy, type: v })} options={TYPES} />
          <button
            className="btn-primary"
            disabled={!newStudy.name}
            onClick={async () => {
              try {
                await api(`/api/admin/projects/${encodeURIComponent(name)}/studies/${encodeURIComponent(newStudy.name)}`, { method: "PUT", body: { data: { type: newStudy.type } } });
                toast(`Created study ${newStudy.name}`);
                const s = newStudy.name;
                setNewStudy({ name: "", type: "prolific" });
                await load();
                reload();
                nav.push({ title: s, render: () => <StudyView project={name} study={s} /> });
              } catch (e: any) {
                toast(e.message, "error");
              }
            }}
          >
            <Plus size={15} /> Create
          </button>
        </Row>
      </Group>
      {!isDefault && <SaveRow dirty={dirty} save={save} where={`projects/${name}/project.yaml`} />}
    </>
  );
}

/* ---------- a study ---------- */
export function StudyView({ project, study }: { project: string; study: string }) {
  const [d, setD] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  const [meta, setMeta] = useState<any>(null);
  const url = `/api/admin/projects/${encodeURIComponent(project)}/studies/${encodeURIComponent(study)}`;
  const load = () =>
    api(url).then((r) => {
      setD(r);
      setData(dataOf(r, STUDY_FIELDS));
      setDirty(false);
    });
  useEffect(() => {
    load();
    api("/api/admin/meta").then(setMeta).catch(() => {});
  }, [project, study]);
  if (!d || !data) return <Spinner />;
  const set = (k: string, v: any) => {
    setDirty(true);
    setData((x: any) => {
      const n = { ...x };
      if (v === undefined || v === "") delete n[k];
      else n[k] = v;
      return n;
    });
  };
  const save = async () => {
    try {
      const r = await api(url, { method: "PUT", body: { data } });
      toast("Saved study.yaml");
      load();
      return r;
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const t = (k: string, label: string, hint?: string, ph?: string) => (
    <Row label={label} hint={hint}>
      <TextField label={label} value={data[k] ?? ""} onChange={(v) => set(k, v)} placeholder={ph} />
    </Row>
  );
  const links: Record<string, string> = d.links ?? {};
  const order = ["prolific", "participant", "session_code", "play", "app"];
  return (
    <>
      <div className="mb-5 flex items-center gap-3">
        <Tile icon={FlaskConical} color="bg-good" size={20} />
        <div className="min-w-0">
          <div className="text-lg font-semibold">{data.title || study}</div>
          <div className="truncate text-xs text-muted">{project}/{study} · {shortPath(d.path)}</div>
        </div>
      </div>
      {d.errors?.length > 0 && <Note tone="warn">{d.errors.join(" · ")}</Note>}
      <Group title="Participant links" footer="Give these to participants. The address comes from Public address (General) or HANI2_PUBLIC_URL." id="setting-study-links">
        {order.filter((k) => links[k]).concat(Object.keys(links).filter((k) => !order.includes(k))).map((k) => (
          <Row key={k} label={LINK_LABELS[k]?.[0] ?? k} hint={LINK_LABELS[k]?.[1]} wide>
            <CopyField value={links[k]} label={LINK_LABELS[k]?.[0] ?? k} open={k === "play" || k === "app"} />
          </Row>
        ))}
      </Group>
      <Group title="Results">
        <InfoRow label="Participants" value={d.participants ?? 0} />
        {d.results_rows !== undefined && <InfoRow label="Negotiations recorded" value={d.results_rows} />}
        <Row label="Results, events and recordings" hint="Open the console inside this study to see its results">
          <a className="btn-secondary text-xs" href={`${BASE.replace(/\/s\/[^/]+\/[^/]+$/, "")}/s/${project}/${study}/admin#results`}>
            <BookOpen size={13} /> Open in this study
          </a>
        </Row>
      </Group>
      <Balance project={project} study={study} />
      <Group title="Study" footer="study.yaml">
        <Row label="Type" hint="How participants arrive"><Select label="Type" value={data.type ?? "prolific"} onChange={(v) => set("type", v)} options={TYPES} /></Row>
        {t("title", "Title", "{{study_title}}", "January run")}
        {t("link", "Link", "{{study_link}}", "https://…")}
        <Row label="Year" hint="{{study_year}} (else the start date's year)"><Stepper label="Year" value={data.year ?? null} nullable min={2000} max={2100} onChange={(v) => set("year", v ?? undefined)} /></Row>
        <Row label="Start / end"><TextField label="Start" type="date" className="w-40" value={data.start ?? ""} onChange={(v) => set("start", v)} /><TextField label="End" type="date" className="w-40" value={data.end ?? ""} onChange={(v) => set("end", v)} /></Row>
        {t("organizer", "Organizer", "{{organizer}}; empty: the project's")}
        {t("contact", "Contact", "{{contact}}; empty: the project's")}
      </Group>
      <Group title="Completion" footer="PROLIFIC_COMPLETION_CODE and the completion URL environment variables win over these.">
        {data.type === "prolific" && t("prolific_study_id", "Prolific study id")}
        {t("completion_code", "Completion code", "{{completion_code}}")}
        {t("completion_url", "Completion URL", "Where participants go at the end; may use {pid} and {{variables}}", "https://app.prolific.com/submissions/complete?cc=…")}
        <Row label="End text" hint="Shown on the last page (Markdown)" wide>
          <TextArea label="End text" value={data.end_text ?? ""} rows={4} onChange={(v) => set("end_text", v)} />
        </Row>
      </Group>
      <DefaultsGroup title="Overrides of the project's defaults" value={data.overrides} onChange={(v) => set("overrides", v)} meta={meta} inherit="Project" />
      <SchedulingGroup value={data.scheduling} onChange={(v) => set("scheduling", v)} inherit="Project" effective={d.scheduling_effective} />
      <ExtraGroup data={data} keys={extraKeys(data, STUDY_FIELDS, "overrides")} onChange={set} prefix="study" />
      <SaveRow dirty={dirty} save={save} where={`study.yaml of ${project}/${study}`} />
    </>
  );
}

export function Balance({ project, study }: { project: string; study: string }) {
  const [b, setB] = useState<any>(undefined);
  useEffect(() => {
    api(`/api/admin/projects/${encodeURIComponent(project)}/studies/${encodeURIComponent(study)}/balance`).then(setB).catch(() => setB(null));
  }, [project, study]);
  if (b === undefined) return null;
  if (b === null) return null;
  const max = Math.max(1, ...Object.values(b.counts ?? {}).map(Number));
  return (
    <Group title="Assistant balance" footer={`Each counted human keeps one Assistant; the next human gets the least used one. Pool from ${b.source}${b.group ? ` (group ${b.group})` : ""}. Admins and guests are not counted.`} id="setting-study-balance">
      <InfoRow label="Humans assigned" value={b.humans ?? 0} />
      {Object.entries(b.counts ?? {}).map(([spec, n]: any) => (
        <Row key={spec} label={<code className="text-[0.8rem]">{spec}</code>}>
          <div className="flex w-32 items-center gap-2 sm:w-48">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-line/70">
              <div className="h-full rounded-full bg-you" style={{ width: `${(100 * n) / max}%` }} />
            </div>
            <span className="tnum w-8 text-right text-sm">{n}</span>
          </div>
        </Row>
      ))}
      {b.assignments?.length > 0 && (
        <Disclosure label="Every assignment" value={String(b.assignments.length)} title="Assignments" render={() => (
          <Group>
            {b.assignments.map((a: any) => (
              <InfoRow key={a.user} label={`${a.index ?? "–"}. ${a.user}`} value={a.assistant ?? "—"} hint={[a.assistant_group && `group ${a.assistant_group}`, a.assigned_at?.slice(0, 16)].filter(Boolean).join(" · ")} />
            ))}
          </Group>
        )} />
      )}
    </Group>
  );
}
