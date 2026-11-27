// The ``leaderboard`` block of a project (``defaults.leaderboard``) or a study's override
// (``overrides.leaderboard``, merged key by key; rules, user_options and defaults per key). Saved with
// the page. The choices are limited to what saving accepts: strata of the track, the default sort among
// the sort options, each switch's default among its allowed values.
import { useEffect, useState } from "react";
import { ExternalLink, Plus, X } from "lucide-react";
import { api } from "../api";
import { Group } from "./Group";
import { Row } from "./Row";
import { Select } from "./controls/Select";
import { Stepper } from "./controls/Stepper";
import { Checks } from "./controls/Checks";
import { Toggle } from "./controls/Toggle";
import { type Criteria, useCriteria, useScores } from "./boards";
import { grouped } from "../ui/metricGroups";
import { type KeyGroup, KeyList } from "./controls/KeyList";
import { COUNT_COLUMNS, SWITCH_TITLE, type Switch, boardPage, switchLabel } from "../leaderboard/board";
import { ROOT } from "../pages/Leaderboard";

const STRATA: Record<string, string[]> = { hi: ["combined", "solo", "paired"], han: ["alone", "vs_team", "both"] };
const WINDOWS = ["all", "last_7_days", "last_30_days", "last_90_days", "last_365_days"];
const COUNT_TITLE: Record<string, string> = { games: "Games", participants: "Players", guests: "Guests", abandon_rate: "Abandon rate", cost_usd: "Cost (US$)" };

function switchValues(sw: Switch, track: string, extra: string[] = []): string[] {
  if (sw === "games") return ["all", "people", "ai"];
  if (sw === "stratum") return STRATA[track] ?? STRATA.hi;
  return [...new Set([...WINDOWS, ...extra.filter((x) => /^last_\d+_days$/.test(x))])];
}

export function LeaderboardSettings({ value, onChange, project, study, kind, info, studies, version }: {
  value: any;
  onChange: (v: any) => void;
  project: string;
  study?: string;
  kind: string;
  /** ``editor.leaderboard``: the block inherited (a project: the defaults) and the one in effect as saved */
  info?: { inherited?: any; effective?: any } | null;
  /** the project's studies (a project board: which feed it) */
  studies?: string[];
  version?: unknown;
}) {
  const scores = useScores(project, study ?? null, version);
  const crit: Criteria | undefined = useCriteria(project, study ?? null);
  const [others, setOthers] = useState<string[]>([]);
  useEffect(() => {
    if (study) return;
    api("/api/admin/projects")
      .then((d: any) => setOthers((d.projects ?? []).filter((p: any) => p.name !== project).flatMap((p: any) => (p.studies ?? []).map((s: string) => `${p.name}/${s}`))))
      .catch(() => setOthers([]));
  }, [project, study]);
  const isStudy = !!study;
  const v: any = value ?? {};
  const listed = value !== undefined && value !== null;
  const inh: any = info?.inherited ?? {};
  const inherit = isStudy ? "Project" : "Default";
  const track: string = v.track ?? inh.track ?? (kind === "opponent" ? "han" : "hi");
  const put = (k: string, x: any) => {
    const n = { ...v };
    if (x === null || x === undefined || x === "" || (Array.isArray(x) && !x.length && k !== "include")) delete n[k];
    else n[k] = x;
    onChange(isStudy && !Object.keys(n).length ? null : n);
  };
  const putIn = (k: "rules" | "user_options" | "defaults", sub: string, x: any) => {
    const inner = { ...(v[k] ?? {}) };
    if (x === null || x === undefined || x === "") delete inner[sub];
    else inner[sub] = x;
    put(k, Object.keys(inner).length ? inner : null);
  };
  const enabled = scores?.enabled ?? [];
  const titleOf: Record<string, string> = { ...(crit?.titles ?? {}), ...COUNT_TITLE };
  for (const s of scores?.scores ?? []) titleOf[s.key] = s.title;
  const validatedScore = new Set((scores?.scores ?? []).filter((s) => s.validated).map((s) => s.key));
  const scoreGroup: KeyGroup = { label: "Enabled scores", keys: enabled.map((k) => ({ key: k, title: titleOf[k] ?? k, validated: validatedScore.has(k) })) };
  const sortGroups: KeyGroup[] = [scoreGroup, ...(crit?.sortGroups ?? []).map((g) => ({ label: g.label, keys: g.options.map((o) => ({ key: o.key, title: o.title, validated: o.validated })) }))];
  const criteriaGroups: KeyGroup[] = grouped(crit?.all ?? [], (c) => c.group, crit?.groups).map((g) => ({ label: g.title, keys: g.items.map((c) => ({ key: c.key, title: c.title, validated: c.validated })) }));
  const columnGroups: KeyGroup[] = [scoreGroup, { label: "Counts", keys: COUNT_COLUMNS.map((k) => ({ key: k, title: COUNT_TITLE[k] })) }, ...criteriaGroups];
  const sortOptions: string[] = v.sort_options ?? inh.sort_options ?? [];
  const columns: string[] = v.columns ?? inh.columns ?? [];
  const defaultSort: string = v.default_sort ?? inh.default_sort ?? sortOptions[0] ?? "";
  const userOptions: Record<string, string[]> = { ...(isStudy ? inh.user_options ?? {} : {}), ...(v.user_options ?? {}) };
  const defaults: Record<string, string> = { ...(inh.defaults ?? {}), ...(v.defaults ?? {}) };
  const rules: Record<string, any> = { ...(inh.rules ?? {}), ...(v.rules ?? {}) };
  const ownRule = (k: string) => v.rules?.[k] !== undefined;
  /** A new track: strata of the other track (switch values, the default, included studies) are dropped,
   *  since saving refuses them. */
  const setTrack = (x: string) => {
    const n: any = { ...v };
    if (x) n.track = x;
    else delete n.track;
    const ok = STRATA[x || inh.track || (kind === "opponent" ? "han" : "hi")] ?? STRATA.hi;
    if (n.user_options?.stratum && !n.user_options.stratum.every((y: string) => ok.includes(y))) {
      const { stratum: _s, ...rest } = n.user_options;
      if (Object.keys(rest).length) n.user_options = rest;
      else delete n.user_options;
    }
    if (n.defaults?.stratum && !ok.includes(n.defaults.stratum)) {
      const { stratum: _d, ...rest } = n.defaults;
      if (Object.keys(rest).length) n.defaults = rest;
      else delete n.defaults;
    }
    if (Array.isArray(n.include)) n.include = n.include.map((e: any) => (e.stratum && !ok.includes(e.stratum) ? { study: e.study } : e));
    onChange(isStudy && !Object.keys(n).length ? null : n);
  };
  const setSortOptions = (xs: string[]) => {
    const n = { ...v, sort_options: xs };
    if (!xs.length) delete n.sort_options;
    // the default sort must stay one of the sort options
    if (xs.length && !xs.includes(defaultSort)) n.default_sort = xs[0];
    onChange(n);
  };
  const setSwitch = (sw: Switch, vals: string[] | null) => {
    const uo = { ...(v.user_options ?? {}) };
    if (vals === null) delete uo[sw];
    else uo[sw] = vals;
    const n = { ...v, user_options: uo };
    if (!Object.keys(uo).length) delete n.user_options;
    // the switch's default must be one of its allowed values
    if (vals && vals.length && !vals.includes(defaults[sw])) n.defaults = { ...(v.defaults ?? {}), [sw]: vals[0] };
    onChange(n);
  };
  const ruleNum = (k: string, label: string, help: string, opts: { min: number; nullable?: boolean; step?: number; max?: number; ph?: string }) => (
    <Row id={`board-${k.replace(/_/g, "-")}`} help={help} label={label} overridden={ownRule(k)} onReset={() => putIn("rules", k, null)}>
      <Stepper label={label} value={v.rules?.[k] ?? null} nullable placeholder={opts.ph ?? (inh.rules?.[k] === null || inh.rules?.[k] === undefined ? "no cap" : String(inh.rules[k]))} step={opts.step ?? 1} min={opts.min} max={opts.max} onChange={(x) => putIn("rules", k, x)} />
    </Row>
  );
  const shown = (k: string) => (inh[k] === undefined || inh[k] === null ? inherit : `${inherit} (${Array.isArray(inh[k]) ? inh[k].join(", ") || "none" : inh[k]})`);
  return (
    <Group title="Leaderboard" id="setting-board-settings" footer={isStudy ? "This study's own board: the study.yaml block overrides the project's key by key (rules, switches and defaults per key). Saved with the page." : "The project board: the leaderboard block of project.yaml. Studies override it key by key for their own boards. Saved with the page."}>
      <Row id="board-listed" help="leaderboard" label={isStudy ? "Study board" : "Project board"} hint={isStudy ? (listed ? `${Object.keys(v).length} key(s) set here` : "Uses the project's settings") : listed ? "Listed in GET /api/v1/leaderboards" : "No board settings yet: the board uses the defaults and is not listed"}>
        {!isStudy && <Toggle label="Project board settings" value={listed} onChange={(on) => onChange(on ? {} : null)} />}
      </Row>
      {(listed || isStudy) && (
        <>
          <Row id="board-track" help="leaderboard.track" label="Track" overridden={v.track !== undefined} onReset={() => put("track", null)}>
            <Select label="Track" value={v.track ?? ""} onChange={setTrack} options={[{ value: "", label: shown("track") }, { value: "hi", label: "hi: rank Assistants" }, { value: "han", label: "han: rank opponents" }]} />
          </Row>
          <Row id="board-source" help="leaderboard.source" label="Source" overridden={v.source !== undefined} onReset={() => put("source", null)}>
            <Select label="Source" value={v.source ?? ""} onChange={(x) => put("source", x)} options={[{ value: "", label: shown("source") }, { value: "game", label: "game: the games people played" }, { value: "tournament", label: "tournament: the simulated table" }]} />
          </Row>
          {!isStudy && (
            <>
              <Row id="board-studies" help="leaderboard.studies" label="Studies" hint={Array.isArray(v.studies) ? `${v.studies.length} chosen` : `Every study of the project (${(studies ?? []).length})`} overridden={Array.isArray(v.studies)} onReset={() => put("studies", null)} wide={Array.isArray(v.studies)}>
                {Array.isArray(v.studies) ? (
                  <Checks value={v.studies} onChange={(x) => put("studies", x.length ? x : null)} options={[...new Set([...(studies ?? []), ...v.studies])].map((s) => ({ value: s, label: s }))} />
                ) : (
                  <button className="btn-secondary text-xs" disabled={!(studies ?? []).length} onClick={() => put("studies", [...(studies ?? [])])}>Choose studies</button>
                )}
              </Row>
              <Row id="board-include" help="leaderboard.include" label="Rows from other projects" hint="Games of a study of another project, for one stratum only" wide={(v.include ?? []).length > 0}>
                <span className="flex flex-col items-end gap-1.5">
                  {(v.include ?? []).map((e: any, i: number) => (
                    <span key={i} className="flex flex-wrap items-center justify-end gap-1.5" data-include={i}>
                      <Select label={`Included study ${i + 1}`} value={e.study ?? ""} onChange={(x) => put("include", v.include.map((y: any, j: number) => (j === i ? { ...y, study: x } : y)))} options={[...new Set([e.study, ...others].filter(Boolean))].map((s) => ({ value: s, label: s }))} />
                      <Select label={`Stratum of included study ${i + 1}`} value={e.stratum ?? ""} onChange={(x) => put("include", v.include.map((y: any, j: number) => (j === i ? (x ? { ...y, stratum: x } : { study: y.study }) : y)))} options={[{ value: "", label: "every stratum" }, ...(STRATA[track] ?? []).filter((s) => s !== "combined" && s !== "both").map((s) => ({ value: s, label: s }))]} />
                      <button className="btn-ghost px-1.5 text-xs text-bad" aria-label={`Remove included study ${i + 1}`} onClick={() => put("include", v.include.filter((_: any, j: number) => j !== i).length ? v.include.filter((_: any, j: number) => j !== i) : null)}><X size={13} /></button>
                    </span>
                  ))}
                  <button className="btn-secondary text-xs" disabled={!others.length} onClick={() => put("include", [...(v.include ?? []), { study: others[0], stratum: track === "han" ? "vs_team" : "solo" }])}><Plus size={13} /> Add a study</button>
                </span>
              </Row>
            </>
          )}
          <Row id="board-sort-options" help="leaderboard.sort_options" label="Sort options" hint={v.sort_options ? "What end users may rank by" : `${inherit}: ${sortOptions.map((k) => titleOf[k] ?? k).join(", ") || "the enabled scores of the track"}`} overridden={!!v.sort_options} onReset={() => put("sort_options", null)} wide={!!v.sort_options}>
            {v.sort_options ? <KeyList label="Sort options" value={v.sort_options} groups={sortGroups} onChange={setSortOptions} titles={titleOf} /> : <button className="btn-secondary text-xs" onClick={() => setSortOptions(sortOptions.length ? sortOptions : enabled.slice(0, 1))}>Choose here</button>}
          </Row>
          <Row id="board-default-sort" help="leaderboard.default_sort" label="Default sort" overridden={v.default_sort !== undefined} onReset={() => put("default_sort", null)}>
            <Select label="Default sort" value={v.default_sort ?? ""} onChange={(x) => put("default_sort", x)} options={[{ value: "", label: `${inherit} (${titleOf[inh.default_sort] ?? inh.default_sort ?? "the first sort option"})` }, ...sortOptions.map((k) => ({ value: k, label: titleOf[k] ?? k }))]} />
          </Row>
          <Row id="board-columns" help="leaderboard.columns" label="Columns" hint={v.columns ? "The values each entry shows" : `${inherit}: ${columns.map((k) => titleOf[k] ?? k).join(", ")}`} overridden={!!v.columns} onReset={() => put("columns", null)} wide={!!v.columns}>
            {v.columns ? <KeyList label="Columns" value={v.columns} groups={columnGroups} onChange={(x) => put("columns", x.length ? x : null)} titles={titleOf} /> : <button className="btn-secondary text-xs" onClick={() => put("columns", columns.length ? columns : [...sortOptions, "games", "participants"])}>Choose here</button>}
          </Row>
          {(["games", "stratum", "window"] as Switch[]).map((sw) => {
            const on = (userOptions[sw]?.length ?? 0) > 1;  // a switch with one value is not shown
            const all = switchValues(sw, track, userOptions[sw]);
            const vals = userOptions[sw] ?? [];
            return (
              <Row key={sw} id={`board-switch-${sw}`} help="leaderboard.user_options" label={`${SWITCH_TITLE[sw]} switch`} hint={on ? `End users choose among ${vals.map((x) => switchLabel(sw, x)).join(", ")}` : `Not shown to end users: ${switchLabel(sw, defaults[sw] ?? "all")} applies`} overridden={v.user_options?.[sw] !== undefined} onReset={() => setSwitch(sw, null)} wide={on}>
                <span className="flex flex-wrap items-center justify-end gap-3">
                  <Toggle label={`Show the ${SWITCH_TITLE[sw].toLowerCase()} switch`} value={on} onChange={(x) => (x ? setSwitch(sw, all.slice(0, sw === "stratum" ? 3 : sw === "window" ? 2 : 3)) : isStudy && inh.user_options?.[sw] ? setSwitch(sw, [defaults[sw] ?? all[0]]) : setSwitch(sw, null))} />
                  {on && <Checks value={vals} onChange={(x) => x.length && setSwitch(sw, all.filter((y) => x.includes(y)))} options={all.map((x) => ({ value: x, label: switchLabel(sw, x) }))} columns={2} />}
                </span>
              </Row>
            );
          })}
          <Row id="board-defaults" help="leaderboard.defaults" label="Switch defaults" hint="What applies when the viewer does not choose (and always, for a switch end users do not get)" overridden={!!v.defaults} onReset={() => put("defaults", null)}>
            <span className="flex flex-wrap justify-end gap-1.5">
              {(["games", "stratum", "window"] as Switch[]).map((sw) => {
                const allowed = (userOptions[sw]?.length ?? 0) > 0 ? userOptions[sw] : switchValues(sw, track, [defaults[sw]].filter(Boolean));
                return <Select key={sw} label={`Default ${SWITCH_TITLE[sw].toLowerCase()}`} value={v.defaults?.[sw] ?? ""} onChange={(x) => putIn("defaults", sw, x)} options={[{ value: "", label: `${SWITCH_TITLE[sw]}: ${switchLabel(sw, inh.defaults?.[sw] ?? allowed[0])}` }, ...allowed.map((x) => ({ value: x, label: switchLabel(sw, x) }))]} />;
              })}
            </span>
          </Row>
          <Row id="board-visibility" help="leaderboard.visibility" label="Visibility" overridden={v.visibility !== undefined} onReset={() => put("visibility", null)}>
            <Select label="Visibility" value={v.visibility ?? ""} onChange={(x) => put("visibility", x)} options={[{ value: "", label: shown("visibility") }, { value: "public", label: "public: anyone" }, { value: "participants", label: "participants: signed-in users" }, { value: "admins", label: "admins only" }]} />
          </Row>
          {ruleNum("min_games", "Minimum games", "leaderboard.rules.min_games", { min: 0 })}
          {ruleNum("min_participants", "Minimum players", "leaderboard.rules.min_participants", { min: 0 })}
          {ruleNum("max_games_per_pair", "Cap per pair of people", "leaderboard.rules.max_games_per_pair", { min: 1 })}
          {ruleNum("max_games_per_participant", "Cap per player", "leaderboard.rules.max_games_per_participant", { min: 1 })}
          <Row id="board-exclude-own" help="leaderboard.rules.exclude_own" label="Own-team games" overridden={ownRule("exclude_own")} onReset={() => putIn("rules", "exclude_own", null)}>
            <Select label="Own-team games" value={v.rules?.exclude_own === undefined ? "" : v.rules.exclude_own ? "exclude" : "count"} onChange={(x) => putIn("rules", "exclude_own", x === "" ? null : x === "exclude")} options={[{ value: "", label: `${inherit} (${inh.rules?.exclude_own ? "left out" : "counted"})` }, { value: "count", label: "Counted" }, { value: "exclude", label: "Left out" }]} />
          </Row>
          <Row id="board-adjust" help="leaderboard.rules.adjust" label="Adjustment" overridden={ownRule("adjust")} onReset={() => putIn("rules", "adjust", null)}>
            <Select label="Adjustment" value={v.rules?.adjust ?? ""} onChange={(x) => putIn("rules", "adjust", x)} options={[{ value: "", label: `${inherit} (${inh.rules?.adjust ?? "relative"})` }, { value: "relative", label: "relative: cell-adjusted" }, { value: "balanced", label: "balanced: mean of cell means" }]} />
          </Row>
          {ruleNum("ci", "Confidence level", "leaderboard.rules.ci", { min: 0.5, max: 0.99, step: 0.01, ph: String(inh.rules?.ci ?? 0.95) })}
          <Row id="board-link" label="The board as end users see it" hint={`${rules.min_games ?? "?"} games and ${rules.min_participants ?? "?"} players to be ranked · save first to see a change`}>
            <a className="btn-secondary text-xs" href={boardPage(ROOT, project, study)} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Open the board</a>
          </Row>
        </>
      )}
    </Group>
  );
}
