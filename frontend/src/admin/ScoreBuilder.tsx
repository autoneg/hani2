import { useEffect, useMemo, useState } from "react";
import { Copy, Pencil, Plus, Save, Scale, Trash2, X } from "lucide-react";
import { api } from "../api";
import { NumberInput } from "../ui/NumberInput";
import { Group } from "./Group";
import { Row } from "./Row";
import { HelpFor } from "./help";
import { Select } from "./controls/Select";
import { TextField } from "./controls/TextField";
import { Note, Spinner } from "./schema";
import { toast } from "./toast";
import { atHundred, normalise, sumText, toFractions } from "./weights";

/* ---------- the target of the score endpoints ---------- */
const base = (project: string, study?: string) =>
  `/api/admin/projects/${encodeURIComponent(project)}${study ? `/studies/${encodeURIComponent(study)}` : ""}`;
const query = (project: string, study?: string) => (study ? `study=${encodeURIComponent(`${project}/${study}`)}` : `project=${encodeURIComponent(project)}`);

const SOURCE_TITLE: Record<string, string> = {
  hard: "Measured when the game ends",
  soft: "Rated by the language-model judge",
  subjective: "Questionnaire scales (bundled)",
  questionnaire: "Questionnaire items and scales of this project's forms",
  score: "Scores",
};
const TRACKS = [
  { value: "any", label: "any: Assistants or opponents" },
  { value: "hi", label: "hi: ranks Assistants" },
  { value: "han", label: "han: ranks opponents" },
];
const MISSING = [
  { value: "renormalise", label: "renormalise (default)" },
  { value: "zero", label: "zero" },
  { value: "skip_game", label: "skip_game" },
];
const KEY_RE = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

interface Comp {
  criterion: string;
  /** percent */
  weight: number;
  /** "" = the catalogue's */
  direction: string;
  /** null = the catalogue's default */
  normaliser: any | null;
  label?: string;
}

/** The criteria catalogue (``GET /api/admin/criteria``); ``coverage`` evaluates the current games. */
function useCriteria(project: string, study: string | undefined, coverage: boolean) {
  const [c, setC] = useState<any>(undefined);
  useEffect(() => {
    setC((x: any) => (x ? { ...x, loading: true } : x));
    api(`/api/admin/criteria?${query(project, study)}${coverage ? "&coverage=true" : ""}`)
      .then(setC)
      .catch((e) => (toast(e.message, "error"), setC(null)));
  }, [project, study, coverage]);
  return c;
}

/** Why a criterion cannot be chosen for this score (empty: it can). */
function unusable(c: any, track: string, chosen: string[]): string {
  if (chosen.includes(c.id)) return "already in the score";
  if (track === "hi" && c.hi_usable === false) return c.reason || "not usable for HI scores";
  return "";
}

function CriteriaPicker({ criteria, track, chosen, onPick }: { criteria: any[]; track: string; chosen: string[]; onPick: (c: any) => void }) {
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const t = q.trim().toLowerCase();
    const hit = (c: any) => !t || `${c.id} ${c.title} ${c.description} ${c.metric} ${c.source}`.toLowerCase().includes(t);
    const out: Record<string, any[]> = {};
    for (const c of criteria) if (hit(c)) (out[c.source] ??= []).push(c);
    return Object.keys(SOURCE_TITLE).filter((s) => out[s]?.length).map((s) => [s, out[s]] as const);
  }, [criteria, q]);
  const n = groups.reduce((a, [, cs]) => a + cs.length, 0);
  return (
    <div>
      <input aria-label="Search criteria" type="search" className="mb-2 w-full rounded-md border border-line bg-surface px-2 py-1 text-sm focus:border-you focus:outline-none" placeholder={`Search ${criteria.length} criteria`} value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="scroll-thin max-h-72 overflow-y-auto rounded-lg border border-line/70" role="listbox" aria-label="Criteria">
        {groups.map(([src, cs]) => (
          <div key={src}>
            <div className="sticky top-0 z-[1] border-b border-line/60 bg-sunken/95 px-3 py-1 text-xs font-semibold text-muted">
              {SOURCE_TITLE[src]} <span className="font-normal">({cs.length})</span>
            </div>
            {cs.map((c: any) => {
              const why = unusable(c, track, chosen);
              return (
                <button
                  key={c.id}
                  type="button"
                  role="option"
                  aria-selected={chosen.includes(c.id)}
                  disabled={!!why}
                  title={why || c.description}
                  onClick={() => onPick(c)}
                  className="flex w-full items-start gap-2 border-b border-line/40 px-3 py-1.5 text-left text-sm last:border-0 hover:bg-sunken/60 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <Plus size={13} className="mt-1 shrink-0 text-you" />
                  <span className="min-w-0 flex-1">
                    <span className="font-mono text-[0.78rem]">{c.id}</span> <span className="text-muted">{c.title !== c.id ? c.title : ""}</span>
                    <span className="block text-xs text-muted">
                      {[
                        c.direction === "none" ? "no direction" : `${c.direction} is better`,
                        c.normaliser_text,
                        c.cost,
                        c.coverage != null ? `coverage ${Math.round(100 * c.coverage)} %` : null,
                        why && why !== "already in the score" ? why : null,
                      ].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        ))}
        {!n && <div className="px-3 py-2 text-sm text-muted">No criterion matches.</div>}
      </div>
    </div>
  );
}

function NormaliserEdit({ value, preset, onChange, kinds }: { value: any | null; preset: string; onChange: (v: any | null) => void; kinds: string[] }) {
  const kind = value?.kind ?? "";
  const set = (patch: any) => onChange({ ...(value ?? {}), ...patch });
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Select
        label="Normaliser"
        value={kind}
        onChange={(k) => onChange(!k ? null : k === "bounded" || k === "clip" ? { kind: k, lo: value?.lo ?? 0, hi: value?.hi ?? 1 } : k === "reciprocal" || k === "saturating" ? { kind: k, scale: "reference_median" } : { kind: k })}
        options={[{ value: "", label: `Preset: ${preset}` }, ...kinds.map((k) => ({ value: k, label: k }))]}
      />
      {(kind === "bounded" || kind === "clip") && (
        <>
          <NumberInput aria-label="Lower bound" className="field tnum w-16" value={value.lo} onCommit={(lo) => set({ lo })} />
          <NumberInput aria-label="Upper bound" className="field tnum w-16" value={value.hi} onCommit={(hi) => set({ hi })} />
        </>
      )}
      {(kind === "reciprocal" || kind === "saturating") && (
        <>
          <Select label="Scale" value={value.scale === "reference_median" ? "median" : "fixed"} onChange={(x) => set({ scale: x === "median" ? "reference_median" : 1 })} options={[{ value: "median", label: "s = reference median" }, { value: "fixed", label: "s = a number" }]} />
          {value.scale !== "reference_median" && <NumberInput aria-label="Scale" className="field tnum w-16" min={0} value={value.scale} onCommit={(scale) => scale > 0 && set({ scale })} />}
        </>
      )}
    </span>
  );
}

/** The catalogue's default normaliser as text, turned by the component's direction: ``reciprocal``
 *  and ``saturating`` are one rule seen from the two directions. */
function presetNormaliser(info: any, direction: string): string {
  const t: string = (info?.normaliser_text ?? "none").replace("reference median", "median");
  const dir = direction || info?.direction || "none";
  if (dir === "lower") return t.replace(/^saturating/, "reciprocal");
  if (dir === "higher") return t.replace(/^reciprocal/, "saturating");
  return t;
}

function fromDefinition(d: any): Comp[] {
  const comps = d?.components ?? [];
  // stored fractions sum to 1; rounding each to 0.01 % could show 99.99 % (thirds), so rescale exactly
  const pct = normalise(comps.map((c: any) => c.weight));
  return comps.map((c: any, i: number) => ({ criterion: c.criterion, weight: pct[i], direction: c.direction ?? "", normaliser: c.normaliser ?? null, label: c.label }));
}

/** Build or edit one score: a criteria picker over the catalogue, a weight in % per component with
 *  the running sum (Save only at 100 %, Normalise rescales), and a direction and normaliser per
 *  component (preset from the catalogue). ``initial`` is a definition as ``GET /api/admin/scores``
 *  gives it; ``scoreKey`` fixed means an edit. */
export function ScoreBuilder({ project, study, scoreKey, initial, onSaved, onClose }: { project: string; study?: string; scoreKey?: string; initial?: any; onSaved: () => void; onClose: () => void }) {
  const [key, setKey] = useState(scoreKey ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [track, setTrack] = useState(initial?.track ?? "any");
  const [missing, setMissing] = useState(initial?.missing ?? "renormalise");
  const [minCov, setMinCov] = useState<number>(initial?.min_coverage ?? 0.5);
  const [same, setSame] = useState<string>(initial?.same_assistant ?? "once");
  const [comps, setComps] = useState<Comp[]>(() => fromDefinition(initial));
  const [coverage, setCoverage] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const cat = useCriteria(project, study, coverage);
  const byId = useMemo(() => Object.fromEntries((cat?.criteria ?? []).map((c: any) => [c.id, c])), [cat]);
  if (cat === undefined) return <Spinner />;
  if (cat === null) return <Note tone="warn">The criteria could not be loaded.</Note>;
  const kinds: string[] = (cat.normalisers ?? []).map((n: any) => n.kind);
  const weights = comps.map((c) => c.weight);
  const ok100 = atHundred(weights);
  const needDirection = comps.filter((c) => !c.direction && (byId[c.criterion]?.direction ?? "none") === "none").map((c) => c.criterion);
  const keyOk = KEY_RE.test(key);
  const canSave = keyOk && comps.length > 0 && ok100 && !needDirection.length && !saving;
  const patch = (i: number, p: Partial<Comp>) => setComps(comps.map((c, j) => (j === i ? { ...c, ...p } : c)));
  const save = async () => {
    const fr = toFractions(weights);
    const body = {
      title: title || undefined,
      description: description || undefined,
      track,
      missing,
      min_coverage: minCov,
      ...(same !== "once" ? { same_assistant: same } : {}),
      components: comps.map((c, i) => ({
        criterion: c.criterion,
        weight: fr[i],
        ...(c.direction ? { direction: c.direction } : {}),
        ...(c.normaliser ? { normaliser: c.normaliser } : {}),
        ...(c.label ? { label: c.label } : {}),
      })),
    };
    setSaving(true);
    try {
      await api(`${base(project, study)}/scores/${encodeURIComponent(key)}`, { method: "PUT", body });
      toast(`Saved score ${key}`);
      setError("");
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <div data-score-builder>
      <Group title={scoreKey ? `Edit score ${scoreKey}` : "New score"} actions={<button className="btn-ghost px-1.5 text-xs" onClick={onClose}><X size={13} /> Close</button>}>
        <Row label="Key" hint="The score's name in results, exports and boards: a letter, then letters, digits and _">
          {scoreKey ? <code className="text-sm">{scoreKey}</code> : <TextField label="Score key" value={key} onChange={setKey} className="w-44" placeholder="hi_score" mono />}
        </Row>
        <Row label="Title"><TextField label="Score title" value={title} onChange={setTitle} placeholder="HI-score" /></Row>
        <Row label="Description"><TextField label="Score description" value={description} onChange={setDescription} className="w-72" /></Row>
        <Row label="Track" help="scores.track"><Select label="Track" value={track} onChange={setTrack} options={TRACKS} /></Row>
        <Row label="Missing values" help="scores.missing"><Select label="Missing values" value={missing} onChange={setMissing} options={MISSING} /></Row>
        <Row label="Minimum coverage" help="scores.min_coverage">
          <NumberInput aria-label="Minimum coverage" className="field tnum w-20" min={0} max={1} step={0.05} value={minCov} onCommit={setMinCov} />
        </Row>
        <Row label="Same-Assistant games" help="scores.same_assistant">
          <Select label="Same-Assistant games" value={same} onChange={setSame} options={[{ value: "once", label: "Count once (the mean of the two rows)" }, { value: "skip", label: "Leave out" }]} />
        </Row>
      </Group>
      <Group
        title="Components"
        actions={
          <>
            <span className={`tnum rounded px-1.5 py-0.5 text-xs font-medium ${ok100 ? "bg-good/10 text-good" : "bg-warn/10 text-warn"}`} data-weight-sum>
              Sum {sumText(weights)}
            </span>
            <button className="btn-secondary text-xs" disabled={!comps.length} onClick={() => setComps(comps.map((c, i) => ({ ...c, weight: normalise(weights)[i] })))}>
              <Scale size={13} /> Normalise
            </button>
          </>
        }
        footer="Weights are in %, and must sum to 100 % to save. Normalise rescales them to 100 % keeping their proportions. Direction and normaliser start from the criterion's own (preset)."
      >
        {comps.length === 0 && <div className="px-4 py-3 text-sm text-muted">No component yet: pick criteria below.</div>}
        {comps.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 bg-sunken/50 px-4 py-1.5 text-xs text-muted">
            <span className="flex-1">Criterion</span>
            <span className="inline-flex items-center gap-0.5">Weight <HelpFor id="scores.weights" /></span>
            <span className="inline-flex items-center gap-0.5">Direction <HelpFor id="scores.direction" /></span>
            <span className="inline-flex items-center gap-0.5">Normaliser <HelpFor id="scores.normaliser" /></span>
          </div>
        )}
        {comps.map((c, i) => {
          const info = byId[c.criterion];
          const presetDir = info?.direction ?? "none";
          return (
            <div key={c.criterion} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2" data-component={c.criterion}>
              <div className="min-w-[10rem] flex-1">
                <div className="font-mono text-[0.8rem]">{c.criterion}</div>
                <div className="truncate text-xs text-muted">{info ? [info.title !== c.criterion && info.title, info.cost].filter(Boolean).join(" · ") : "not in the catalogue"}</div>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1.5">
                <span className="inline-flex items-center gap-1">
                  <NumberInput aria-label={`Weight of ${c.criterion} (%)`} className="field tnum w-20" min={0} max={100} value={c.weight} onCommit={(w) => patch(i, { weight: w })} />
                  <span className="text-xs text-muted">%</span>
                </span>
                <Select
                  label={`Direction of ${c.criterion}`}
                  value={c.direction}
                  onChange={(d) => patch(i, { direction: d })}
                  options={[{ value: "", label: presetDir === "none" ? "Direction: choose" : `Preset: ${presetDir}` }, { value: "higher", label: "higher is better" }, { value: "lower", label: "lower is better" }]}
                />
                <NormaliserEdit value={c.normaliser} preset={presetNormaliser(info, c.direction)} kinds={kinds} onChange={(n) => patch(i, { normaliser: n })} />
                <button className="btn-ghost px-1.5 text-bad" aria-label={`Remove ${c.criterion}`} onClick={() => setComps(comps.filter((_, j) => j !== i))}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </Group>
      <Group
        title={<span className="inline-flex items-center gap-1">Add criteria <HelpFor id="scores.criteria" /></span>}
        actions={
          <button className="btn-ghost text-xs" onClick={() => setCoverage(true)} disabled={coverage}>
            {coverage ? (cat.loading ? "Computing coverage…" : `Coverage of ${cat.games ?? 0} games`) : "Show coverage in the current games"}
          </button>
        }
        footer={cat.reference?.frozen ? `Scales come from the project's frozen reference.` : "This project has no frozen reference yet: the scales of unbounded criteria are provisional (hani2 scores freeze)."}
      >
        <div className="px-4 py-3">
          <CriteriaPicker criteria={cat.criteria ?? []} track={track} chosen={comps.map((c) => c.criterion)} onPick={(x) => setComps([...comps, { criterion: x.id, weight: 0, direction: "", normaliser: null }])} />
        </div>
      </Group>
      {error && <Note tone="warn">{error}</Note>}
      <div className="mb-6 flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-xs text-muted">
          {!keyOk ? "Give the score a key." : !comps.length ? "Add at least one criterion." : !ok100 ? `The weights sum to ${sumText(weights)}: they must sum to 100 % (Normalise).` : needDirection.length ? `Choose a direction for ${needDirection.join(", ")}.` : "Ready to save."}
        </span>
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={!canSave} onClick={save}>
          <Save size={15} /> Save score
        </button>
      </div>
    </div>
  );
}

/** The scores of a project or study: the built-ins (read-only, Duplicate), the defined ones (Edit,
 *  Remove) and the builder. ``onChange`` runs after every write, so the page can take the file's new
 *  ``scores`` into its unsaved data. */
export function ScoresGroup({ project, study, onChange }: { project: string; study?: string; onChange: () => void }) {
  const [d, setD] = useState<any>(undefined);
  const [editing, setEditing] = useState<{ key?: string; initial?: any } | null>(null);
  const load = () => api(`/api/admin/scores?${query(project, study)}`).then(setD).catch((e) => (toast(e.message, "error"), setD(null)));
  useEffect(() => {
    load();
  }, [project, study]);
  if (d === undefined) return <Spinner />;
  if (d === null) return null;
  const here = study ? "study" : "project";
  const changed = () => {
    load();
    onChange();
  };
  const duplicate = async (from: string) => {
    const key = window.prompt(`Copy ${from} as`, `my_${from}`);
    if (!key) return;
    try {
      await api(`${base(project, study)}/scores/${encodeURIComponent(key)}/duplicate`, { method: "POST", body: { from } });
      toast(`Copied ${from} as ${key}`);
      changed();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const remove = async (key: string) => {
    if (!window.confirm(`Remove the score ${key} from this ${here}?`)) return;
    try {
      await api(`${base(project, study)}/scores/${encodeURIComponent(key)}`, { method: "DELETE" });
      toast(`Removed ${key}`);
      changed();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <>
      <Group
        title={<span className="inline-flex items-center gap-1">Scores <HelpFor id="scores" /></span>}
        id="setting-scores"
        actions={<button className="btn-secondary text-xs" onClick={() => setEditing({})}><Plus size={13} /> New score</button>}
        footer={`Built-in scores are read-only: Duplicate copies one into this ${here}'s file. Changes here are saved at once.`}
      >
        {(d.scores ?? []).map((s: any) => {
          const mine = s.origin === here;
          const parts = (s.components ?? []).map((c: any) => `${c.criterion} ${Math.round(c.weight * 1000) / 10} %`).join(", ");
          return (
            <Row key={s.key} label={<span><code className="text-[0.8rem]">{s.key}</code>{s.title && s.title !== s.key ? ` — ${s.title}` : ""}</span>} hint={<>{[s.origin === "builtin" ? "built-in" : `defined in the ${s.origin}`, s.track, s.enabled ? "enabled" : "not enabled"].join(" · ")}<span className="block truncate">{parts}</span></>}>
              <button className="btn-ghost px-1.5 text-xs" onClick={() => duplicate(s.key)} title="Copy into this file"><Copy size={13} /> Duplicate</button>
              {s.origin !== "builtin" && (
                <button className="btn-ghost px-1.5 text-xs" onClick={() => setEditing({ key: s.key, initial: s })}>
                  <Pencil size={13} /> {mine ? "Edit" : "Redefine here"}
                </button>
              )}
              {mine && <button className="btn-ghost px-1.5 text-xs text-bad" onClick={() => remove(s.key)}><Trash2 size={13} /> Remove</button>}
            </Row>
          );
        })}
      </Group>
      {[...(d.problems ?? []), ...(d.warnings ?? [])].length > 0 && <Note tone="warn">{[...d.problems, ...d.warnings].join(" · ")}</Note>}
      {editing && <ScoreBuilder key={editing.key ?? "new"} project={project} study={study} scoreKey={editing.key} initial={editing.initial} onClose={() => setEditing(null)} onSaved={() => (setEditing(null), changed())} />}
    </>
  );
}
