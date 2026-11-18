import { useEffect, useState } from "react";
import { Dices, Map as MapIcon, TriangleAlert } from "lucide-react";
import { api } from "../../api";
import { Markdown } from "../../ui/Markdown";
import { Plot } from "../../ui/Plot";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { Disclosure } from "../Disclosure";
import { lq, shortPath, type Layer } from "../layer";
import { Select } from "../controls/Select";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { SOURCE_LABEL } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

const enc = encodeURIComponent;

/** A scenario type as participants would see it (``GET /api/admin/scenarios/{name}``). */
function Details({ item, layer }: { item: ExItem; layer: Layer }) {
  const t = item.raw;
  const [d, setD] = useState<any>(null);
  const [pick, setPick] = useState<string>("");
  const [gen, setGen] = useState<number | null>(null);
  useEffect(() => {
    setD(null);
    const q = `${lq(layer)}${pick ? `&scenario=${enc(pick)}` : ""}${gen !== null ? `&generate=${gen}` : ""}`;
    api(`/api/admin/scenarios/${enc(t.name)}${q}`).then(setD).catch((e) => setD({ error: e.message }));
  }, [t.name, layer.id, pick, gen]);
  const generator = t.source === "builtin" || (t.source === "registered" && !t.n_scenarios);
  return (
    <>
      {d?.has_display_py && (
        <Note tone="warn"><TriangleAlert size={14} className="mr-1 inline" /> This scenario has a display.py. It runs as Python code on the server whenever an offer is shown.</Note>
      )}
      <Group title="Example">
        {d?.pool?.length > 0 && (
          <Row label="Scenario" hint={`${d.pool.length} in the pool`}>
            <Select label="Pool scenario" value={pick} onChange={(v) => (setPick(v), setGen(null))} options={[{ value: "", label: "First in the pool" }, ...d.pool]} />
          </Row>
        )}
        {(generator || d?.kind === "generator" || d?.kind === "story") && (
          <Row label="Generate an example" hint="A fresh draw from the generator (not saved)">
            <button className="btn-secondary" onClick={() => (setPick(""), setGen(Math.floor(Math.random() * 10000)))}><Dices size={14} /> Generate</button>
          </Row>
        )}
        {d && !d.error && <InfoRow label="Shown" value={d.generated ? (gen !== null ? `generated (seed ${gen})` : "generated") : shortPath(d.loaded_from) || "bundled template"} mono={!d.generated} />}
      </Group>
      {!d ? <Spinner /> : d.error ? <Note tone="warn">{d.error}</Note> : <ScenarioBody d={d} />}
    </>
  );
}

function ScenarioBody({ d }: { d: any }) {
  return (
    <>
      <Group title={d.title || d.name}>
        {d.short_description && <div className="px-4 py-3 text-sm">{d.short_description}</div>}
        {d.long_description && <Disclosure label="Long description" hint="What participants read" title="Long description" render={() => <Group><div className="px-4 py-3"><Markdown text={d.long_description} /></div></Group>} />}
        <InfoRow label="Outcomes" value={d.n_outcomes} />
      </Group>
      <Group title="Roles">
        {d.roles.map((r: any) => (
          <InfoRow key={r.name} label={<>{r.name}{r.human && <span className="ml-1.5 rounded bg-you/10 px-1.5 text-[0.68rem] text-you">participant</span>}</>} hint={r.description} value={`no deal: ${fmt(r.reserved_value)}`} />
        ))}
      </Group>
      <Group title={`Issues (${d.issues.length})`}>
        {d.issues.map((i: any) => (
          <Row key={i.name} label={i.name} hint={i.description || i.type} wide>
            <div className="flex flex-wrap gap-1">
              {i.values.map((v: string) => <span key={v} className="chip">{v}</span>)}
              {i.n_values > i.values.length && <span className="text-xs text-muted">… {i.n_values} options</span>}
            </div>
          </Row>
        ))}
      </Group>
      <UtilityPlots d={d} />
      {d.sample?.length > 0 && (
        <Group title="Sample utilities" footer="The best outcome for each role, then a few others.">
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  {d.issues.map((i: any) => <th key={i.name} className="px-3 py-2 font-medium">{i.name}</th>)}
                  {d.roles.map((r: any) => <th key={r.name} className="px-3 py-2 text-right font-medium">{r.name}</th>)}
                </tr>
              </thead>
              <tbody>
                {d.sample.map((s: any, k: number) => (
                  <tr key={k} className="border-t border-line/70">
                    {d.issues.map((i: any) => <td key={i.name} className="px-3 py-1.5">{s.outcome[i.name]}</td>)}
                    {d.roles.map((r: any) => <td key={r.name} className="tnum px-3 py-1.5 text-right">{fmt(s.utilities[r.name])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Group>
      )}
      {d.warnings?.length > 0 && <Note tone="warn">{d.warnings.join(" · ")}</Note>}
    </>
  );
}
/** Every outcome in utility space (negmas's 2D plot): the participant's role against each other
 *  role, with the Pareto frontier, the bargaining solutions and the no-deal regions shaded. */
function UtilityPlots({ d }: { d: any }) {
  // fetched after the details, so the page never waits for the plot
  const [r, setR] = useState<{ plots: { title: string; figure: any }[]; plot_note: string } | { error: string } | null>(null);
  const [k, setK] = useState(0);
  useEffect(() => {
    setR(null);
    setK(0);
    if (!d.plot_token) return;
    let live = true;
    api<any>(`/api/admin/scenarios/plot/${enc(d.plot_token)}`).then((x) => live && setR(x)).catch((e) => live && setR({ error: e.message }));
    return () => void (live = false);
  }, [d.plot_token]);
  if (!d.plot_token) return null;
  if (!r) return <Group title="Outcome space"><div className="px-4"><Spinner /></div></Group>;
  if ("error" in r) return <Note tone="warn">{r.error}</Note>;
  const plots = r.plots;
  if (!plots.length) return r.plot_note ? <Note>{r.plot_note}</Note> : null;
  const p = plots[Math.min(k, plots.length - 1)];
  return (
    <Group
      title="Outcome space"
      footer={["Each dot is an outcome at its utility for the two roles; shading marks where an outcome is worse than a role's no-deal value.", r.plot_note].filter(Boolean).join(" ")}
    >
      {plots.length > 1 && (
        <Row label="Roles" hint="The participant's role against each other role">
          <Select label="Roles plotted" value={String(k)} onChange={(v) => setK(Number(v))} options={plots.map((x, i) => ({ value: String(i), label: x.title }))} />
        </Row>
      )}
      <div className="px-2 pb-2">
        <Plot figure={p.figure} height={480} />
      </div>
    </Group>
  );
}

const fmt = (x: any) => (typeof x === "number" ? x.toFixed(2) : x == null ? "—" : String(x));

/** The default scenario set of the layer (``scenario_sets.yaml`` → ``default``). */
function DefaultSet({ layer, groups, reload }: { layer: Layer; groups: ExGroup[]; reload: () => void }) {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    api(`/api/admin/library/scenarios/default${lq(layer)}`).then(setS).catch(() => setS(null));
  }, [layer.id, groups]);
  if (!s) return null;
  return (
    <Group title="Scenario set in use" footer="An admin's session choice, HANI2_SCENARIO_SET and a study's scenario_set win over this default." id="setting-scenario-default-set">
      <Row id="default-set" label="Default set" hint={s.here ? `Set in ${layer.label}` : `Inherited: ${s.effective}`}>
        <Select
          label="Default set"
          value={s.here ?? ""}
          onChange={async (v) => {
            try {
              setS(await api(`/api/admin/library/scenarios/default${lq(layer)}`, { method: "PUT", body: { default: v || null } }));
              toast(`Default set saved to ${layer.label}`);
              reload();
            } catch (e: any) {
              toast(e.message, "error");
            }
          }}
          options={[{ value: "", label: `Inherit (${s.effective})` }, ...s.sets]}
        />
      </Row>
    </Group>
  );
}

export const scenariosAdapter: Adapter = {
  kind: "scenarios",
  noun: "scenario type",
  nouns: "scenario types",
  groupNoun: "set",
  groupNouns: "scenario sets",
  icon: MapIcon,
  color: "bg-good",
  ordered: true,
  code: true,
  accept: ".zip",
  linkHint: "/data/scenarios/MyCase",
  uploadHint: "A zip holds one scenario folder (<Type>.yml, one file per role, _info.yaml) or a category of them; every scenario is checked. A name must not equal or start like a registered type.",
  Intro: () => <Note>Scenario types are registered generators and category folders (uploaded or linked). Sets list types and other sets (@name) in the order participants meet them.</Note>,
  subtitle: (t) => [SOURCE_LABEL[t.source] ?? t.source, t.n_scenarios ? `${t.n_scenarios} saved` : null, t.groups.length ? `in ${t.groups.slice(0, 3).join(", ")}${t.groups.length > 3 ? "…" : ""}` : "in no set", t.description].filter(Boolean).join(" · "),
  ItemExtra: ({ item, layer }) => <Details item={item} layer={layer} />,
  Extra: ({ layer, groups, reload }) => <DefaultSet layer={layer} groups={groups} reload={reload} />,
  validKey: (k) => /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/.test(k) && k.toLowerCase() !== "custom",
};
