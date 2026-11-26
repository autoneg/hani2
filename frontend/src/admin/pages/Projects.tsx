import { useEffect, useState } from "react";
import { BookOpen, FlaskConical, FolderKanban, Info, Plus, Save, X } from "lucide-react";
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
import { Checks } from "../controls/Checks";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { useScheduling as useSchedulingMethods } from "../help";
import { HAN_SETS, MODE_LABEL, crossingActive, derive, hanEntry, hanToken, hanYearLabel, hanYears, items, kOfN, modeProblems } from "../modes";
import { ScoresGroup } from "../ScoreBuilder";

const PROJECT_FIELDS = ["name", "full_name", "short_description", "link", "year", "kind", "organizer", "contact"];
const STUDY_FIELDS = ["name", "project", "type", "title", "link", "year", "start", "end", "prolific_study_id", "completion_code", "completion_url", "end_text", "organizer", "contact"];
const INFO_KEYS = ["path", "legacy", "participants", "results_rows", "default", "links", "yaml", "studies", "scheduling_effective", "study_mode_effective", "editor", "errors"];
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
/** ``obj`` with ``k`` set (``null`` / empty: removed). */
function putKey(obj: any, k: string, v: any) {
  const n = { ...(obj ?? {}) };
  if (v === null || v === undefined) delete n[k];
  else n[k] = v;
  return n;
}
/** The unsaved ``data`` with the file's fresh ``scores`` (after a score endpoint wrote the file), so a
 *  later page Save keeps what the endpoint wrote; every other unsaved edit stays. */
function withScores(data: any, nested: "defaults" | "overrides", fresh: any) {
  const inner = putKey(data?.[nested], "scores", fresh?.[nested]?.scores);
  return { ...data, [nested]: inner };
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
  const load = () => api("/api/admin/projects").then(setD).catch((e) => toast(e.message, "error"));
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
const useScheduling = () => useSchedulingMethods((e) => toast(e.message, "error"));

/** How many Assistants a layer's pool has after the groups are expanded (``null``: unknown). */
function usePoolSize(layer: string | undefined, version: unknown) {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    if (!layer) return;
    api(`/api/admin/pools/assistant?layer=${encodeURIComponent(layer)}`).then((r: any) => setN(Array.isArray(r?.effective) ? r.effective.length : null)).catch(() => setN(null));
  }, [layer, version]);
  return n;
}

/** How each dimension is scheduled: this file's choice, else ``inherit`` (``effective``: what the study uses). */
function SchedulingGroup({ value, onChange, inherit, effective, k, layer, version, inherited }: { value: any; onChange: (v: any) => void; inherit: string; effective?: Record<string, string>; k?: number | null; layer?: string; version?: unknown; inherited?: Record<string, any> }) {
  const m = useScheduling();
  const n = usePoolSize(layer, version);
  if (!m) return m === null ? null : <Spinner />;
  const v = value ?? {};
  const dims: [string, string, string][] = [["opponents", "Opponents", "scheduling.opponents"], ["assistants", "Assistants", "scheduling.assistants"], ["scenarios", "Scenarios", "scheduling.scenarios"]];
  const method = (dim: string) => v[dim] ?? effective?.[dim] ?? m.defaults?.[dim];
  const setOpt = (key: string, x: any) => {
    const nv = { ...v };
    if (x === null || x === undefined || x === "") delete nv[key];
    else nv[key] = x;
    onChange(nv);
  };
  // the options are merged like the dimensions: this file's value, else the project's, else the default
  const repeats: boolean | null = v.assistant_repeats ?? inherited?.assistant_repeats ?? null;
  const cross: string = v.cross ?? inherited?.cross ?? m.options?.cross?.default ?? "shift";
  const kn = kOfN(method("assistants"), k, n, repeats);
  const crossOn = crossingActive(method("assistants"), method("opponents"), cross);
  const inhRepeats = inherited?.assistant_repeats;
  const inhCross = inherited?.cross ?? m.options?.cross?.default;
  return (
    <Group title="Scheduling" footer={`How HANI2 assigns each human. “${inherit}” keeps the value from the ${inherit === "Default" ? "server default" : "project"}.`} id="setting-scheduling">
      {dims.map(([k, l, help]) => {
        const opts = m.dimensions?.[k] ?? [];
        const cur = opts.find((o: any) => o.key === v[k]);
        // what an unset dimension uses (the study's effective value is its own once it sets one)
        const inh = v[k] ? undefined : opts.find((o: any) => o.key === (effective?.[k] ?? m.defaults?.[k]));
        return (
          <Row key={k} id={`scheduling-${k}`} help={help} label={l} hint={cur ? cur.summary : inh?.summary} overridden={!!v[k]} onReset={() => { const n = { ...v }; delete n[k]; onChange(n); }}>
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
      <Row id="assignment-k-of-n" help="assignment.k_of_n" label="K of N" hint={kn.perNegotiation ? "Counted negotiations against the Assistants in the pool" : "Counted negotiations and the Assistants in the pool"}>
        <span className={`text-right text-sm ${kn.warn ? "font-medium text-warn" : "text-muted"}`} data-k-of-n={kn.warn ? "warn" : "ok"}>{kn.text}</span>
      </Row>
      <Row id="scheduling-assistant-repeats" help="scheduling.assistant_repeats" label="Repeats" hint="assistant_repeats: may a person get the same Assistant twice?" overridden={v.assistant_repeats !== undefined} onReset={() => setOpt("assistant_repeats", null)}>
        <Select
          label="Repeats"
          value={v.assistant_repeats === undefined ? "" : v.assistant_repeats ? "yes" : "no"}
          onChange={(x) => setOpt("assistant_repeats", x === "" ? null : x === "yes")}
          options={[{ value: "", label: `${inherit} (${inhRepeats === undefined ? "unset" : inhRepeats ? "yes" : "no"})` }, { value: "yes", label: "Yes: wrap around" }, { value: "no", label: "No: at most once" }]}
        />
      </Row>
      <Row id="scheduling-cross" help="scheduling.cross" label="Crossing" hint={crossOn ? "Active: the opponents are shifted against the Assistants" : cross === "shift" ? "Applies only when the Assistants change every negotiation and the opponents use latin_square or cyclic" : "Off: the Assistant and the opponent may be confounded"} overridden={v.cross !== undefined} onReset={() => setOpt("cross", null)}>
        <Select label="Crossing" value={v.cross ?? ""} onChange={(x) => setOpt("cross", x || null)} options={[{ value: "", label: `${inherit} (${inhCross})` }, { value: "shift", label: "shift" }, { value: "none", label: "none" }]} />
      </Row>
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
function DefaultsGroup({ title, value, onChange, meta, inherit, footer, ed, effective }: { title: string; value: any; onChange: (v: any) => void; meta: any; inherit: string; footer?: string; ed?: any; effective?: any }) {
  const v = value ?? {};
  const inh = ed?.inherited ?? {};
  const kind: string = ed?.kind ?? "none";
  const opponents = v.opponents ?? inh.opponents;
  const declared: string | null = v.study_mode ?? inh.study_mode ?? null;
  const derived = derive(opponents);
  const mode = declared ?? derived;
  const problems = modeProblems(declared, opponents, v.assistants, kind);
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
    <>
    <Group title={title} footer={footer ?? `Empty fields keep the ${inherit.toLowerCase()} value.`}>
      <Row id="study-mode" help="study_mode" label="Mode" overridden={!!v.study_mode} onReset={() => put("study_mode", null)}>
        <Select
          label="Mode"
          value={v.study_mode ?? ""}
          onChange={(x) => put("study_mode", x || null)}
          options={[
            { value: "", label: inh.study_mode ? `${inherit} (${MODE_LABEL[inh.study_mode as keyof typeof MODE_LABEL] ?? inh.study_mode})` : `Derived from the opponents (${MODE_LABEL[derived]})` },
            { value: "solo", label: "Solo" },
            { value: "paired", label: "Paired" },
            { value: "mixed", label: "Mixed" },
          ]}
        />
      </Row>
      {problems.length > 0 && (
        <div className="px-4 py-2 text-sm text-bad" role="alert" data-mode-problem>
          {problems.map((p) => <div key={p}>{p}. Saving is refused until the mode and the opponents agree.</div>)}
        </div>
      )}
      {!problems.length && effective?.mode_error && !v.study_mode && !v.opponents && (
        <div className="px-4 py-2 text-sm text-bad" role="alert">{(effective.errors ?? []).join(" · ")}</div>
      )}
      {kind === "opponent" && mode === "paired" && <div className="px-4 py-2 text-sm text-warn" data-han-paired>Paired in a HAN project tests no HAN agent; its results are not ranked.</div>}
      {mode !== "paired" && <HanAgents own={v.opponents} inherited={inh.opponents} onChange={(x) => put("opponents", x)} ed={ed} />}
      <Row label="Scenario set" help="scenario_set" hint="The scenario types and their order">
        <Select label="Scenario set" value={v.scenario_set ?? ""} onChange={(x) => put("scenario_set", x)} options={[{ value: "", label: inherit }, ...sets]} />
      </Row>
      <Row label="Strict scenarios" help="strict_scenarios" hint="strict_scenarios: serve saved scenarios only; a missing or broken pool is an error, never a generated scenario">{tri("strict_scenarios")}</Row>
      <Row label="Simple scenarios" help="simple_scenarios" hint="simple_scenarios: generate scenarios with round numbers and linear or symmetric preferences, and serve only saved scenarios generated that way">{tri("simple_scenarios")}</Row>
      <Row label="Forced value on disagreement" help="force_reserved_value" hint="force_reserved_value: the participant's value on disagreement (0 to 1 on normalised scenarios) in every negotiation, whatever the scenario says; the opponent keeps the scenario's. Empty: each scenario's own values">
        <Stepper label="Forced value on disagreement" value={v.force_reserved_value ?? null} nullable placeholder={inherit.toLowerCase()} step={0.05} min={0} onChange={(x) => put("force_reserved_value", x)} />
      </Row>
      <Row label="Counted negotiations" help="n_required" hint="n_required: K, the counted negotiations per participant">{num("n_required")}</Row>
      <Row label="Practice round" help="practice" hint="A first negotiation that does not count">{tri("practice")}</Row>
      <Row label="Practice time limit (s)">{num("practice_time_limit", 30)}</Row>
      <Row label="Counted time limit (s)">{num("counted_time_limit", 30)}</Row>
      <Row label="Time limit (s)" hint="Per negotiation, outside Prolific studies">{num("time_limit", 30)}</Row>
      <Row label="Rounds" hint="n_steps">{num("n_steps", 10)}</Row>
      <Row label="Expected minutes" hint="minutes, shown in texts as {{minutes}}">{num("minutes", 5)}</Row>
      <Row label="Participant's role" help="role_rule" hint="role_rule">
        <Select label="Participant's role" value={v.role_rule ?? ""} onChange={(x) => put("role_rule", x)} options={[{ value: "", label: inherit }, ...Object.keys(meta?.role_rules ?? { auto: 1, index: 1, roles: 1, alternate: 1, random: 1 })]} />
      </Row>
      <Row label="Preferred roles" help="human_roles" hint="human_roles, for the roles rule">
        <Tags label="Preferred roles" value={v.human_roles} onChange={(x) => put("human_roles", x)} placeholder="Buyer" />
      </Row>
      <InfoRow label="Opponents and Assistants" value={[v.opponents && `opponents: ${[].concat(v.opponents).join(", ")}`, v.assistants && `assistants: ${[].concat(v.assistants).join(", ")}`].filter(Boolean).join(" · ") || inherit} hint="Choose the pools in Opponents and Assistants (pick this layer there)" />
      <InformationRows value={v.information} onChange={(x) => put("information", x)} inherit={inherit} />
    </Group>
    {(mode === "paired" || mode === "mixed") && <PairingGroup value={v.pairing} onChange={(x) => put("pairing", x)} inherit={inherit} effective={effective?.pairing_effective} />}
    </>
  );
}

/** The ``:han<year>-<set>`` entries of this layer's opponent pool: a year (labelled "this year" /
 *  "last year" from the project's year; years no source covers are greyed out) and a set. */
function HanAgents({ own, inherited, onChange, ed }: { own: any; inherited: any; onChange: (v: string[] | null) => void; ed?: any }) {
  const years = hanYears(ed?.project_year, ed?.han?.package_years ?? [], ed?.han?.current_year);
  const first = years.find((y) => y.covered)?.year ?? years[0]?.year;
  const [year, setYear] = useState<number | undefined>(first);
  const [set, setSet] = useState<string>("finalists");
  const pool = own !== undefined ? items(own) : items(inherited);
  const han = pool.filter((x) => hanToken(x));
  const y = years.find((x) => x.year === year);
  const entry = year ? hanEntry(year, set) : "";
  const add = () => onChange([...pool, entry]);
  const remove = (t: string) => {
    const rest = pool.filter((x) => x !== t);
    onChange(rest.length ? rest : null);
  };
  return (
    <Row id="opponents-han" help="opponents.han" label="HAN agents" hint={own === undefined && pool.length ? "Adding writes this layer's own opponent pool, starting from the inherited one" : y && !y.covered ? `No agents for ${y.year}: neither han-agents nor the current year's submissions cover it` : undefined}>
      <span className="flex flex-wrap items-center justify-end gap-1.5">
        {han.map((t) => (
          <span key={t} className="chip py-0.5 text-[0.78rem]">
            {t}
            {own !== undefined && (
              <button aria-label={`Remove ${t}`} className="text-muted hover:text-bad" onClick={() => remove(t)}>
                <X size={12} />
              </button>
            )}
          </span>
        ))}
        {years.length > 0 ? (
          <>
            <select aria-label="HAN year" className="rounded-md border border-line bg-surface py-1 pl-2.5 pr-2 text-sm text-ink focus:border-you focus:outline-none" value={year ?? ""} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((x) => (
                <option key={x.year} value={x.year} disabled={!x.covered}>{hanYearLabel(x)}</option>
              ))}
            </select>
            <Select label="HAN set" value={set} onChange={setSet} options={HAN_SETS.map((x) => ({ value: x, label: x }))} />
            <button className="btn-secondary text-xs" disabled={!y?.covered || pool.includes(entry)} onClick={add} title={entry}>
              <Plus size={13} /> Add {entry}
            </button>
          </>
        ) : (
          <span className="text-xs text-muted">No HAN agents: install han-agents or set han.current_year</span>
        )}
      </span>
    </Row>
  );
}

/** The ``pairing`` block (Paired and Mixed studies): merged key by key with the layer above. */
function PairingGroup({ value, onChange, inherit, effective }: { value: any; onChange: (v: any) => void; inherit: string; effective?: Record<string, any> }) {
  const v = value ?? {};
  const put = (k: string, x: any) => {
    const n = { ...v };
    if (x === null || x === undefined || x === "" || (Array.isArray(x) && !x.length)) delete n[k];
    else n[k] = x;
    onChange(Object.keys(n).length ? n : null);
  };
  const shown = (k: string) => {
    const e = effective?.[k];
    return e === undefined || e === null ? inherit : `${inherit} (${typeof e === "boolean" ? (e ? "yes" : "no") : Array.isArray(e) ? e.join(", ") : e})`;
  };
  const sel = (k: string, label: string, opts: string[]) => (
    <Select label={label} value={v[k] ?? ""} onChange={(x) => put(k, x)} options={[{ value: "", label: shown(k) }, ...opts]} />
  );
  return (
    <Group title="Pairing" id="setting-pairing" footer="Read only in Paired and Mixed studies. Empty fields keep the value above; a study's block is merged key by key with its project's.">
      <Row id="pairing-scope" help="pairing.scope" label="Where people meet" overridden={v.scope !== undefined} onReset={() => put("scope", null)}>{sel("scope", "Where people meet", ["study", "project", "code"])}</Row>
      <Row id="pairing-assign" help="pairing.assign" label="How a match is formed" overridden={v.assign !== undefined} onReset={() => put("assign", null)}>{sel("assign", "How a match is formed", ["cells", "order", "random"])}</Row>
      <Row id="pairing-slack" help="pairing.slack" label="Slack" overridden={v.slack !== undefined} onReset={() => put("slack", null)}>
        <Stepper label="Slack" value={v.slack ?? null} nullable placeholder={String(effective?.slack ?? "")} min={0} step={1} onChange={(x) => put("slack", x)} />
      </Row>
      <Row id="pairing-cell-scenario" help="pairing.cell_scenario" label="Scenario in a cell" overridden={v.cell_scenario !== undefined} onReset={() => put("cell_scenario", null)}>{sel("cell_scenario", "Scenario in a cell", ["type", "name"])}</Row>
      <Row id="pairing-same" help="pairing.allow_same_assistant" label="Same-Assistant matches" overridden={v.allow_same_assistant !== undefined} onReset={() => put("allow_same_assistant", null)}>
        <Select label="Same-Assistant matches" value={v.allow_same_assistant === undefined ? "" : v.allow_same_assistant ? "yes" : "no"} onChange={(x) => put("allow_same_assistant", x === "" ? null : x === "yes")} options={[{ value: "", label: shown("allow_same_assistant") }, { value: "yes", label: "Allowed" }, { value: "no", label: "Not allowed" }]} />
      </Row>
      <Row id="pairing-fallback" help="pairing.fallback" label="When nobody fits" overridden={v.fallback !== undefined} onReset={() => put("fallback", null)}>{sel("fallback", "When nobody fits", ["ai", "wait", "end"])}</Row>
      <Row id="pairing-fallback-opponents" help="pairing.fallback_opponents" label="Fallback opponents" overridden={v.fallback_opponents !== undefined} onReset={() => put("fallback_opponents", null)}>
        <Tags label="Fallback opponents" value={v.fallback_opponents} onChange={(x) => put("fallback_opponents", x)} placeholder=":pan" />
      </Row>
    </Group>
  );
}

/** ``scores_enabled``: this layer's list, or the default (every score; a study: the project's). */
function ScoresEnabledGroup({ value, onChange, project, study, inherit, version }: { value: string[] | undefined; onChange: (v: string[] | null) => void; project: string; study?: string; inherit: string; version: unknown }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api(`/api/admin/scores?${study ? `study=${encodeURIComponent(`${project}/${study}`)}` : `project=${encodeURIComponent(project)}`}`).then(setD).catch(() => setD(null));
  }, [project, study, version]);
  const all: string[] = (d?.scores ?? []).map((s: any) => s.key);
  const own = Array.isArray(value);
  const shown: string[] = d?.enabled ?? [];
  return (
    <Group title="Scores enabled" id="setting-scores-enabled" footer="Saved with the page. The boards, results views and exports of this layer compute and show the enabled scores.">
      <Row id="scores-enabled" help="scores_enabled" label="Enabled scores" hint={own ? `${value!.length} chosen here` : `${inherit}: ${shown.join(", ") || "every score"}`} overridden={own} onReset={() => onChange(null)} wide={own}>
        {own ? (
          <Checks value={value} onChange={(x) => onChange(x)} options={[...new Set([...all, ...value!])].map((k) => ({ value: k, label: k }))} />
        ) : (
          <button className="btn-secondary text-xs" disabled={!all.length} onClick={() => onChange(shown.length ? shown : all)}>Choose here</button>
        )}
      </Row>
    </Group>
  );
}


/** The ``information`` block: what the human and the Assistant each know (see the Information split guide). */
function InformationRows({ value, onChange, inherit }: { value: any; onChange: (v: any) => void; inherit: string }) {
  const info = value ?? {};
  const set = (section: string, k: string, x: any) => {
    const sec = { ...(info[section] ?? {}) };
    if (x === null || x === undefined || x === "") delete sec[k];
    else sec[k] = x;
    const n = { ...info, [section]: sec };
    if (!Object.keys(sec).length) delete n[section];
    onChange(Object.keys(n).length ? n : null);
  };
  const sel = (section: string, k: string, label: string, opts: string[]) => (
    <Select label={label} value={info[section]?.[k] ?? ""} onChange={(x) => set(section, k, x)} options={[{ value: "", label: inherit }, ...opts]} />
  );
  const parts = ["full", "weights", "values", "none"];
  return (
    <>
      <Row label="Participant knows" help="information.preferences.human" hint="information.preferences.human: which part of their own preferences the participant sees">{sel("preferences", "human", "Participant knows", parts)}</Row>
      <Row label="Assistant knows" help="information.preferences.assistant" hint="information.preferences.assistant: which part of the participant's preferences the Assistant knows">{sel("preferences", "assistant", "Assistant knows", parts)}</Row>
      <Row label="Value on disagreement" help="information.preferences.reserved_value" hint="information.preferences.reserved_value: who knows it">{sel("preferences", "reserved_value", "Value on disagreement", ["both", "human", "assistant", "none"])}</Row>
      <Row label="Past negotiations" help="information.past_negotiations.count" hint="information.past_negotiations.count: records of earlier negotiations in the same scenario (0: none)">
        <Stepper label="Past negotiations" value={info.past_negotiations?.count ?? null} nullable placeholder={inherit.toLowerCase()} step={1} min={0} onChange={(x) => set("past_negotiations", "count", x)} />
      </Row>
      <Row label="Participant's share" help="information.past_negotiations.human_share" hint="information.past_negotiations.human_share: the fraction of past negotiations the participant gets; the Assistant gets the rest">
        <Stepper label="Participant's share" value={info.past_negotiations?.human_share ?? null} nullable placeholder={inherit.toLowerCase()} step={0.1} min={0} onChange={(x) => set("past_negotiations", "human_share", x == null ? x : Math.min(1, x))} />
      </Row>
      <Row label="Past preferences" help="information.past_negotiations.preferences" hint="information.past_negotiations.preferences: how the past parties' preferences relate to this negotiation's">{sel("past_negotiations", "preferences", "Past preferences", ["similar", "same", "different"])}</Row>
      <Row label="Market research" help="information.market_research.audience" hint="information.market_research.audience: who gets statistics about how preferences in the scenario are usually distributed">{sel("market_research", "audience", "Market research", ["none", "assistant", "human", "both"])}</Row>
    </>
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
  const [scoresVersion, setScoresVersion] = useState(0);
  const nav = useNav();
  const { reload } = useLayer();
  const url = `/api/admin/projects/${encodeURIComponent(name)}`;
  const load = () =>
    api(url).then((r) => {
      setD(r);
      setData(dataOf(r, PROJECT_FIELDS));
      setDirty(false);
    }).catch((e) => toast(e.message, "error"));
  // a score endpoint rewrote project.yaml: take its new ``scores`` into the unsaved data
  const refreshScores = () =>
    api(url).then((r) => {
      setScoresVersion((x) => x + 1);
      setData((x: any) => withScores(x, "defaults", r));
    }).catch((e) => toast(e.message, "error"));
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
        <Row label="Kind" help="kind" hint="What the project evaluates"><Select label="Kind" value={data.kind ?? "none"} onChange={(v) => set("kind", v)} options={KINDS} /></Row>
        <Row label="Organizer" hint="{{organizer}}"><TextField label="Organizer" value={data.organizer} onChange={(v) => set("organizer", v)} /></Row>
        <Row label="Contact" hint="{{contact}}"><TextField label="Contact" value={data.contact} onChange={(v) => set("contact", v)} placeholder="lab@example.org" /></Row>
      </Group>
      <DefaultsGroup title="Defaults for its studies" value={data.defaults} onChange={(v) => set("defaults", v)} meta={meta} inherit="Default" ed={d.editor} effective={d.study_mode_effective} />
      <SchedulingGroup value={data.scheduling} onChange={(v) => set("scheduling", v)} inherit="Default" k={data.defaults?.n_required ?? d.editor?.inherited?.n_required} layer={`project:${name}`} version={d} />
      {!isDefault && (
        <>
          <ScoresGroup project={name} onChange={refreshScores} />
          <ScoresEnabledGroup value={data.defaults?.scores_enabled} onChange={(x) => set("defaults", putKey(data.defaults, "scores_enabled", x))} project={name} inherit="Default" version={scoresVersion} />
        </>
      )}
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
  const [scoresVersion, setScoresVersion] = useState(0);
  const url = `/api/admin/projects/${encodeURIComponent(project)}/studies/${encodeURIComponent(study)}`;
  const load = () =>
    api(url).then((r) => {
      setD(r);
      setData(dataOf(r, STUDY_FIELDS));
      setDirty(false);
    }).catch((e) => toast(e.message, "error"));
  const refreshScores = () =>
    api(url).then((r) => {
      setScoresVersion((x) => x + 1);
      setData((x: any) => withScores(x, "overrides", r));
    }).catch((e) => toast(e.message, "error"));
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
        <Row label="Type" help="type" hint="How participants arrive"><Select label="Type" value={data.type ?? "prolific"} onChange={(v) => set("type", v)} options={TYPES} /></Row>
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
      <DefaultsGroup title="Overrides of the project's defaults" value={data.overrides} onChange={(v) => set("overrides", v)} meta={meta} inherit="Project" ed={d.editor} effective={d.study_mode_effective} />
      <SchedulingGroup value={data.scheduling} onChange={(v) => set("scheduling", v)} inherit="Project" effective={d.scheduling_effective} k={data.overrides?.n_required ?? d.editor?.inherited?.n_required} layer={`study:${project}/${study}`} version={d} inherited={d.editor?.inherited?.scheduling} />
      <ScoresGroup project={project} study={study} onChange={refreshScores} />
      <ScoresEnabledGroup value={data.overrides?.scores_enabled} onChange={(x) => set("overrides", putKey(data.overrides, "scores_enabled", x))} project={project} study={study} inherit="Project" version={scoresVersion} />
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
