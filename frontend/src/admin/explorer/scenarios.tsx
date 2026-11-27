import { useEffect, useState } from "react";
import { ChevronRight, Dices, Map as MapIcon, TriangleAlert } from "lucide-react";
import { api } from "../../api";
import { Markdown } from "../../ui/Markdown";
import { Plot } from "../../ui/Plot";
import { Renderer } from "../../ui/Renderer";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { lq, shortPath, type Layer } from "../layer";
import { Select } from "../controls/Select";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { SOURCE_LABEL } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

const enc = encodeURIComponent;

/** A section that folds away; its body mounts only while open (plots size to their container,
 *  and closed sections fetch nothing). The open state is remembered per section. */
function Fold({ id, title, hint, defaultOpen = true, children }: { id: string; title: React.ReactNode; hint?: React.ReactNode; defaultOpen?: boolean; children: () => React.ReactNode }) {
  const key = `hani2.explorer.fold.${id}`;
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem(key);
      return v === null ? defaultOpen : v === "1";
    } catch {
      return defaultOpen;
    }
  });
  const toggle = () => {
    setOpen(!open);
    try {
      localStorage.setItem(key, open ? "0" : "1");
    } catch {
      /* no storage: the state lasts for the page */
    }
  };
  return (
    <section className="mb-4" id={`fold-${id}`}>
      <button type="button" onClick={toggle} aria-expanded={open} className="mb-1.5 flex w-full items-center gap-1.5 rounded px-1 text-left hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-you/40">
        <ChevronRight size={14} className={`shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
        <h3 className="text-[0.8rem] font-semibold text-muted">{title}</h3>
        {hint && <span className="ml-auto truncate text-xs text-muted">{hint}</span>}
      </button>
      {open && children()}
    </section>
  );
}

/** A scenario type as participants would see it (``GET /api/admin/scenarios/{name}``): pick a pool
 *  scenario or draw one from the generator by any generation rule. */
function Details({ item, layer }: { item: ExItem; layer: Layer }) {
  const t = item.raw;
  const [d, setD] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState<string>("");
  const [gen, setGen] = useState<number | null>(null);
  const [rule, setRule] = useState<string>("");
  useEffect(() => setD(null), [t.name, layer.id]);
  useEffect(() => {
    let live = true;
    setLoading(true);
    const q = `${lq(layer)}${pick ? `&scenario=${enc(pick)}` : ""}${gen !== null ? `&generate=${gen}` : ""}${rule && !pick ? `&rule=${enc(rule)}` : ""}`;
    api(`/api/admin/scenarios/${enc(t.name)}${q}`)
      .then((x) => live && setD(x))
      .catch((e) => live && setD({ error: e.message }))
      .finally(() => live && setLoading(false));
    return () => void (live = false);
  }, [t.name, layer.id, pick, gen, rule]);
  const generator = t.source === "builtin" || (t.source === "registered" && !t.n_scenarios) || d?.kind === "generator" || d?.kind === "story";
  const draw = () => (setPick(""), setGen(Math.floor(Math.random() * 10000)));
  const ruleLabel = (v: string | null | undefined) => d?.rules?.find((r: any) => r.value === v)?.label ?? v;
  return (
    <>
      {d?.has_display_py && (
        <Note tone="warn"><TriangleAlert size={14} className="mr-1 inline" /> This scenario has a display.py. It runs as Python code on the server whenever an offer is shown.</Note>
      )}
      <Group title="Example">
        {d?.pool?.length > 0 && (
          <Row label="Scenario" hint={`${d.pool.length} in the pool`}>
            <Select label="Pool scenario" value={pick} onChange={(v) => (setPick(v), setGen(null))} options={[{ value: "", label: gen !== null ? "A generated sample" : "First in the pool" }, ...d.pool]} />
          </Row>
        )}
        {generator && d?.rules?.length > 0 && (
          <Row label="Generation rule" hint={d.rules.find((r: any) => r.value === (rule || d.layer_rule))?.description}>
            <Select
              label="Generation rule"
              value={rule}
              onChange={(v) => (setRule(v), setPick(""), gen === null && setGen(0))}
              options={[{ value: "", label: `As this layer (${ruleLabel(d.layer_rule)})` }, ...d.rules.map((r: any) => ({ value: r.value, label: r.label }))]}
            />
          </Row>
        )}
        {generator && (
          <Row label="Generate a sample" hint="A fresh draw from the generator by the rule above (not saved)">
            <button className="btn-secondary" onClick={draw} disabled={loading}><Dices size={14} /> {loading ? "Generating…" : "Generate"}</button>
          </Row>
        )}
        {d && !d.error && (
          <InfoRow
            label="Shown"
            value={d.generated ? `generated · ${ruleLabel(d.rule)}${gen !== null ? ` · draw ${gen}` : ""}` : `${shortPath(d.loaded_from) || "bundled template"}${d.simple ? " · simple" : ""}`}
            mono={!d.generated}
          />
        )}
      </Group>
      {!d ? <Spinner /> : d.error ? <Note tone="warn">{d.error}</Note> : <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}><ScenarioBody d={d} /></div>}
    </>
  );
}

function ScenarioBody({ d }: { d: any }) {
  return (
    <>
      <Fold id="picture" title="Picture">{() => <Picture token={d.plot_token} />}</Fold>
      <Fold id="description" title="Description" hint={d.title || d.name}>
        {() => (
          <Group>
            <div className="px-4 pt-3 text-sm font-semibold">{d.title || d.name}</div>
            {d.short_description ? <div className="px-4 py-3 text-sm">{d.short_description}</div> : <div className="px-4 py-3 text-sm text-muted">No short description.</div>}
            {d.source && <InfoRow label="Source" value={d.source} />}
            <InfoRow label="Outcomes" value={d.n_outcomes ?? "—"} />
          </Group>
        )}
      </Fold>
      <Fold id="long-description" title="Long description" hint="What participants read" defaultOpen={false}>
        {() => <Group><div className="px-4 py-3">{d.long_description ? <Markdown text={d.long_description} /> : <span className="text-sm text-muted">No long description.</span>}</div></Group>}
      </Fold>
      <Fold id="summaries" title="Preference summaries" hint="“In short” of the Preferences tool, per role">
        {() => (
          <Group>
            {d.summaries?.map((s: any) => (
              <div key={s.role} className="px-4 py-3">
                <div className="mb-1 text-sm font-semibold">{s.role}{s.human && <ParticipantTag />}</div>
                {s.summary ? <Markdown text={s.summary} /> : <span className="text-sm text-muted">No summary.</span>}
              </div>
            ))}
          </Group>
        )}
      </Fold>
      <Fold id="roles" title={`Roles (${d.roles.length})`}>
        {() => (
          <Group>
            {d.roles.map((r: any) => (
              <InfoRow key={r.name} label={<>{r.name}{r.human && <ParticipantTag />}</>} hint={r.description} value={`no deal: ${fmt(r.reserved_value)}`} />
            ))}
          </Group>
        )}
      </Fold>
      <Fold id="issues" title={`Issues (${d.issues.length})`}>
        {() => (
          <Group>
            {d.issues.map((i: any) => (
              <Row key={i.name} label={i.name} hint={i.description || i.type} wide>
                <div className="flex flex-wrap gap-1">
                  {i.values.map((v: string) => <span key={v} className="chip">{v}</span>)}
                  {i.n_values > i.values.length && <span className="text-xs text-muted">… {i.n_values} options</span>}
                </div>
              </Row>
            ))}
          </Group>
        )}
      </Fold>
      <Fold id="outcome-space" title="Outcome space" hint="2D utility plot">{() => <UtilityPlots d={d} />}</Fold>
      <Fold id="statistics" title="Statistics" hint="negmas: opposition, Pareto frontier, bargaining solutions" defaultOpen={false}>{() => <ScenarioStats key={d.plot_token} token={d.plot_token} />}</Fold>
      <Fold id="preferences" title="Preferences tool" hint="As each role sees it" defaultOpen={false}>{() => <RolePreferences d={d} />}</Fold>
      {d.sample?.length > 0 && (
        <Fold id="sample" title="Sample utilities" hint="Best outcome per role, then a few others" defaultOpen={false}>
          {() => (
            <Group>
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
        </Fold>
      )}
      {d.warnings?.length > 0 && <Note tone="warn">{d.warnings.join(" · ")}</Note>}
    </>
  );
}

const ParticipantTag = () => <span className="ml-1.5 rounded bg-you/10 px-1.5 text-[0.68rem] font-normal text-you">participant</span>;

/** Every negmas statistic of the scenario (``GET /api/admin/scenarios/stats/{token}``): computed in
 *  the background and cached next to it, so this polls while they are ``pending``. A scenario too
 *  large or too slow to compute says why instead. */
function ScenarioStats({ token }: { token: string }) {
  const [v, setV] = useState<any>(null);
  const [force, setForce] = useState(0);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let first = force > 0;
    setV(null);
    const load = () =>
      api<any>(`/api/admin/scenarios/stats/${enc(token)}${first ? "?force=true" : ""}`)
        .then((x) => {
          first = false;
          if (!live) return;
          setV(x);
          if (x.status === "pending") timer = setTimeout(load, 2000);
        })
        .catch((e) => live && setV({ status: "error", message: e.message }));
    load();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [token, force]);
  if (!v) return <Group><div className="px-4"><Spinner /></div></Group>;
  const again = (
    <button type="button" className="btn-ghost px-2 text-xs" onClick={() => setForce((k) => k + 1)}>
      Compute again
    </button>
  );
  if (v.status === "pending") return <Group><div className="flex items-center gap-2 px-4 py-3 text-sm text-muted"><Spinner /> Computing in the background…</div></Group>;
  if (v.status !== "ok") {
    const title: Record<string, string> = { timeout: "Too slow to compute", too_large: "Too large to compute", disabled: "Switched off", failed: "Could not compute" };
    return (
      <Group actions={v.status !== "disabled" ? again : undefined}>
        <div className="px-4 py-3 text-sm"><span className="font-semibold">{title[v.status] ?? "Not available"}.</span> <span className="text-muted">{v.message}</span></div>
      </Group>
    );
  }
  const roles: { name: string; human: boolean; reserved_value: number | null }[] = v.roles ?? [];
  const reserved = Object.fromEntries(roles.map((r) => [r.name, r.reserved_value]));
  const RoleHead = ({ name }: { name: string }) => <>{name}{roles.find((r) => r.name === name)?.human && <ParticipantTag />}</>;
  const outcomeText = (o: any) => (o ? Object.entries(o).map(([k, x]) => `${k}: ${x}`).join(", ") : "—");
  const points = (rows: { label?: string; p: any }[], withLabel: boolean) => (
    <div className="scroll-thin max-h-[420px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            {withLabel && <th className="px-3 py-2 font-medium">Solution</th>}
            {roles.map((r) => <th key={r.name} className="px-3 py-2 text-right font-medium"><RoleHead name={r.name} /></th>)}
            <th className="px-3 py-2 text-right font-medium">Welfare</th>
            <th className="px-3 py-2 font-medium">Outcome</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, p }, k) => (
            <tr key={k} className="border-t border-line/70">
              {withLabel && <td className="px-3 py-1.5">{label}</td>}
              {roles.map((r) => <td key={r.name} className="tnum px-3 py-1.5 text-right">{fmt3(p.utilities?.[r.name])}</td>)}
              <td className="tnum px-3 py-1.5 text-right">{fmt3(p.welfare)}</td>
              <td className="px-3 py-1.5">{outcomeText(p.outcome)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  const solRows = (v.solutions ?? []).flatMap((s: any) => s.points.map((p: any, k: number) => ({ label: s.label + (s.points.length > 1 ? ` #${k + 1}` : ""), p })));
  const meta = [v.computed_at && `Computed ${v.computed_at}`, typeof v.seconds === "number" && `in ${v.seconds.toFixed(2)} s`, v.cache === "disk" ? "cached with the scenario" : v.cache === "memory" ? "cached in memory (not a saved scenario folder)" : null].filter(Boolean).join(", ");
  return (
    <>
      <Group footer={meta ? `${meta}.` : undefined} actions={again}>
        <InfoRow label="Outcomes" value={typeof v.n_outcomes === "number" ? v.n_outcomes.toLocaleString() : "—"} />
        <InfoRow label="Issues" value={v.n_issues ?? "—"} />
        <InfoRow label="Opposition" hint="0: no conflict, 1: fully opposed" value={fmt3(v.opposition)} />
        <InfoRow label="Rational fraction" hint="Outcomes better than no deal for every role" value={typeof v.rational_fraction === "number" ? `${(v.rational_fraction * 100).toFixed(1)} %` : "—"} />
        <InfoRow label="Pareto frontier" hint={v.pareto_cached === false ? `Not kept with the scenario: more than ${Number(v.pareto_max_outcomes).toLocaleString()} outcomes` : undefined} value={`${v.pareto_size ?? 0} outcomes`} />
      </Group>
      <div className="mt-3" />
      <Group title="Utility ranges">
        {(v.utility_ranges ?? []).map((r: any) => (
          <InfoRow key={r.role} label={<RoleHead name={r.role} />} value={`${fmt3(r.min)} – ${fmt3(r.max)} · no deal ${fmt3(reserved[r.role])}`} />
        ))}
      </Group>
      <div className="mt-3" />
      <Group title="Bargaining solutions">{solRows.length ? points(solRows, true) : <div className="px-4 py-3 text-sm text-muted">None.</div>}</Group>
      <div className="mt-3" />
      <Group title={`Pareto frontier (${v.pareto_size ?? 0})`} footer={v.pareto_truncated ? `The first ${v.pareto.length} of ${v.pareto_size} points.` : undefined}>
        {v.pareto?.length ? points(v.pareto.map((p: any) => ({ p })), false) : <div className="px-4 py-3 text-sm text-muted">Empty.</div>}
      </Group>
    </>
  );
}

const fmt3 = (x: any) => (typeof x === "number" ? x.toFixed(3) : x == null ? "—" : String(x));

/** The scenario's picture (light and dark), fetched apart: it can be a large data URL. */
function Picture({ token }: { token: string }) {
  const [p, setP] = useState<{ light: string | null; dark: string | null } | { error: string } | null>(null);
  useEffect(() => {
    let live = true;
    setP(null);
    api<any>(`/api/admin/scenarios/picture/${enc(token)}`).then((x) => live && setP(x)).catch((e) => live && setP({ error: e.message }));
    return () => void (live = false);
  }, [token]);
  if (!p) return <Spinner />;
  if ("error" in p) return <Note tone="warn">{p.error}</Note>;
  if (!p.light) return <Note>This scenario has no picture.</Note>;
  const cls = "block h-auto max-h-[420px] w-full rounded-xl object-contain";
  return (
    <Group>
      <div className="p-2">
        {p.dark ? (
          <>
            <img src={p.light} alt="" className={`${cls} theme-light-only`} />
            <img src={p.dark} alt="" className={`${cls} theme-dark-only`} />
          </>
        ) : (
          <img src={p.light} alt="" className={cls} />
        )}
      </div>
    </Group>
  );
}

/** The Preferences tool, rendered on the server for every role, side by side. */
function RolePreferences({ d }: { d: any }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {d.roles.map((r: any, i: number) => <RolePreference key={`${d.plot_token}:${i}`} token={d.plot_token} index={i} role={r} />)}
    </div>
  );
}

function RolePreference({ token, index, role }: { token: string; index: number; role: any }) {
  const [view, setView] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  useEffect(() => {
    let live = true;
    api<any>(`/api/admin/scenarios/preferences/${enc(token)}`, { method: "POST", body: { role: index, values } })
      .then((x) => live && (setView(x.components), setErr(null)))
      .catch((e) => live && setErr(e.message));
    return () => void (live = false);
  }, [token, index, values]);
  return (
    <div className="min-w-0 rounded-xl border border-line/80 bg-surface p-3">
      <div className="mb-2 text-sm font-semibold">{role.name}{role.human && <ParticipantTag />}</div>
      {err ? <Note tone="warn">{err}</Note> : !view ? <Spinner /> : (
        <Renderer components={view} ctx={{ reserved: role.reserved_value, onInput: (n, v) => setValues((s) => ({ ...s, [n]: v })), onAction: () => {} }} />
      )}
    </div>
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
  if (!r) return <Group><div className="px-4"><Spinner /></div></Group>;
  if ("error" in r) return <Note tone="warn">{r.error}</Note>;
  const plots = r.plots;
  if (!plots.length) return r.plot_note ? <Note>{r.plot_note}</Note> : null;
  const p = plots[Math.min(k, plots.length - 1)];
  return (
    <Group
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
