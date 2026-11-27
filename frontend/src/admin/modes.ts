// Pure helpers of the project and study editor (no imports, so `node --test` can load this file):
// the study mode against the opponent pool, the HAN agents picker and the K-of-N check.
// The rules mirror hani2.study_modes (the server checks them again on save).

export type Mode = "solo" | "paired" | "mixed";
export const MODES: Mode[] = ["solo", "paired", "mixed"];
export const MODE_LABEL: Record<Mode, string> = { solo: "Solo", paired: "Paired", mixed: "Mixed" };

/** A pool setting as a list of non-empty strings (a comma-separated string is split). */
export function items(v: unknown): string[] {
  if (v == null) return [];
  if (typeof v === "string") return v.split(",").map((s) => s.trim()).filter(Boolean);
  if (Array.isArray(v)) return v.filter((s) => s != null).map((s) => String(s).trim()).filter(Boolean);
  return [String(v).trim()].filter(Boolean);
}

const norm = (s: string) => s.trim().toLowerCase().replace(/[\s+_-]+/g, "+");
/** ``human`` / ``human+assistant`` however written. */
export const isHuman = (spec: string) => ["human", "human+assistant"].includes(norm(spec));
export const canonicalHuman = (spec: string) => (norm(spec) === "human+assistant" ? "human+assistant" : "human");

/** The mode a pool implies: no human entry → solo, only human entries → paired, both → mixed. */
export function derive(opponents: unknown): Mode {
  const pool = items(opponents);
  const humans = pool.filter(isHuman);
  if (!humans.length) return "solo";
  return humans.length === pool.length ? "paired" : "mixed";
}

/** What is wrong with a declared mode against the pool, the Assistants and the project's kind
 *  (empty: they agree, or the mode is not declared). */
export function modeProblems(mode: string | null | undefined, opponents: unknown, assistants: unknown, kind: string): string[] {
  if (!mode) return [];
  const pool = items(opponents);
  const humans = pool.filter(isHuman);
  const ai = pool.filter((x) => !isHuman(x));
  const asst = items(assistants);
  const noAssistant = asst.length > 0 && asst.every((a) => a.toLowerCase() === "none");
  const out: string[] = [];
  const fmt = (p: string[]) => `[${p.join(", ")}]`;
  if (mode === "solo") {
    if (humans.length) out.push(`Solo plays AI opponents only, but the opponents list ${humans.join(", ")}`);
    if (kind === "assistant" && noAssistant) out.push("Solo in an HI project needs Assistants, not [none]");
  } else if (mode === "paired") {
    const want = kind === "assistant" ? ["human+assistant"] : kind === "opponent" ? ["human"] : null;
    if (pool.length) {
      const got = new Set<string>(humans.map(canonicalHuman));
      if (want && (ai.length || got.size !== 1 || !got.has(want[0])))
        out.push(`A Paired ${kind === "assistant" ? "HI" : "HAN"} study needs opponents ${fmt(want)}, not ${fmt(pool)}`);
      else if (!want && ai.length) out.push(`Paired lists people only, but the opponents list ${ai.join(", ")} (use Mixed)`);
    }
    if (kind === "assistant" && noAssistant) out.push("Paired in an HI project needs an Assistant on each side, not [none]");
    if (kind === "opponent" && asst.length && !noAssistant) out.push(`A Paired HAN study plays without Assistants (assistants: [none]), not ${fmt(asst)}`);
  } else if (mode === "mixed") {
    if (!pool.length) out.push("Mixed needs an opponent pool with a person and an AI, e.g. [human+assistant, :pan]");
    else if (!humans.length || !ai.length) out.push(`Mixed needs at least one person and one AI opponent; ${fmt(pool)} has ${humans.length ? "no AI entry" : "no human entry"}`);
  }
  return out;
}

/* ---------- HAN agents ---------- */
export const HAN_SETS = ["all", "qualified", "finalists", "winners"] as const;
const HAN_RE = /^[:@]?han(\d{4})-(all|qualified|finalists|winners)$/i;

/** ``{year, set}`` of a ``:han<year>-<set>`` entry, else null. */
export function hanToken(tok: string): { year: number; set: string } | null {
  const m = HAN_RE.exec(String(tok ?? "").trim());
  return m ? { year: Number(m[1]), set: m[2].toLowerCase() } : null;
}
export const hanEntry = (year: number, set: string) => `:han${year}-${set}`;

export interface HanYear {
  year: number;
  /** "this year" / "last year", from the project's year (never the clock) */
  relative: string;
  covered: boolean;
  source: "submissions" | "han-agents" | null;
}

/** The years the HAN picker offers: those the sources cover, plus the project's year and the one
 *  before (greyed out when no source covers them), newest first. */
export function hanYears(projectYear: number | null | undefined, packageYears: number[], currentYear: number | null | undefined): HanYear[] {
  const py = projectYear ? Number(projectYear) : null;
  const all = new Set<number>(packageYears.map(Number));
  if (currentYear) all.add(Number(currentYear));
  if (py) {
    all.add(py);
    all.add(py - 1);
  }
  return [...all].sort((a, b) => b - a).map((year) => {
    const source = year === Number(currentYear) ? "submissions" : packageYears.map(Number).includes(year) ? "han-agents" : null;
    return { year, relative: py === year ? "this year" : py && py - 1 === year ? "last year" : "", covered: source !== null, source };
  });
}

export function hanYearLabel(y: HanYear): string {
  const rel = y.relative ? ` (${y.relative})` : "";
  return y.covered ? `${y.year}${rel}` : `${y.year}${rel}: no agents for ${y.year}`;
}

/* ---------- K of N ---------- */
/** Assistant methods that give a new Assistant each negotiation and promise "at most once" when K ≤ N. */
export const AT_MOST_ONCE = ["latin_square", "cyclic", "balanced_subset", "random_subset"];
export const PER_NEGOTIATION = [...AT_MOST_ONCE, "random_each"];

export interface KofN {
  /** the method gives a new Assistant each negotiation */
  perNegotiation: boolean;
  /** K > N under an at-most-once method: some Assistant is used twice by one person */
  warn: boolean;
  text: string;
}

/** K counted negotiations against N Assistants under ``method``; ``repeats`` is
 *  ``scheduling.assistant_repeats`` in effect (``null``: unset). */
export function kOfN(method: string | null | undefined, k: number | null | undefined, n: number | null | undefined, repeats: boolean | null = null): KofN {
  const m = method ?? "";
  const per = PER_NEGOTIATION.includes(m);
  const K = k ?? null;
  const N = n ?? null;
  const head = `K = ${K ?? "?"} counted negotiations, N = ${N ?? "?"} Assistants`;
  if (!per) return { perNegotiation: false, warn: false, text: `${head}: one Assistant per person (${m || "the default method"})` };
  if (m === "random_each")
    return repeats === false
      ? { perNegotiation: true, warn: true, text: `${head}: random_each can repeat an Assistant, but Repeats is No: saving is refused` }
      : { perNegotiation: true, warn: false, text: `${head}: drawn each negotiation, so repeats can happen` };
  if (K == null || N == null || N <= 0) return { perNegotiation: true, warn: false, text: head };
  if (K > N)
    return repeats === true
      ? { perNegotiation: true, warn: false, text: `${head}: K > N, and Repeats is on: the Assistants wrap around` }
      : { perNegotiation: true, warn: true, text: `${head}: K > N but each Assistant is used at most once per person: lower K, add Assistants or turn Repeats on (a file that names the pool is refused on save)` };
  return { perNegotiation: true, warn: false, text: `${head}: each Assistant at most once per person${K === N ? " (every Assistant once)" : ""}` };
}

/** Opponent methods the crossing shifts. */
export const CROSSED_OPPONENTS = ["latin_square", "cyclic"];
/** Whether ``cross: shift`` changes anything for these methods. */
export const crossingActive = (assistants: string | null | undefined, opponents: string | null | undefined, cross: string | null | undefined) =>
  cross === "shift" && PER_NEGOTIATION.includes(assistants ?? "") && CROSSED_OPPONENTS.includes(opponents ?? "");

/* ---------- what each mode offers ---------- */
/** The human entries a declared mode allows in the opponent pool (``null``: no mode declared, so
 *  every entry is offered: the mode is then derived from the pool). Paired lists people only. */
export function allowedHumans(mode: string | null | undefined, kind: string): string[] | null {
  if (mode === "solo") return [];
  if (mode === "paired") return kind === "assistant" ? ["human+assistant"] : kind === "opponent" ? ["human"] : ["human", "human+assistant"];
  return null;
}

/** Why ``entry`` may not be in the opponent pool of a study declared ``mode`` ("" when it may). */
export function poolEntryProblem(entry: string, mode: string | null | undefined, kind: string): string {
  const allowed = allowedHumans(mode, kind);
  if (allowed === null) return "";
  if (isHuman(entry)) {
    if (allowed.includes(canonicalHuman(entry))) return "";
    return mode === "solo" ? "Solo plays AI opponents only" : `a Paired ${kind === "assistant" ? "HI" : "HAN"} study plays ${allowed.join(" or ")}`;
  }
  return mode === "paired" ? "a Paired study plays people only (the AI fallback has its own pool)" : "";
}

/** Whether the opponent pool picker offers ``entry`` (an AI agent, a group or a human entry). */
export const poolOffers = (entry: string, mode: string | null | undefined, kind: string) => !poolEntryProblem(entry, mode, kind);

/** The pairing defaults a mode gives (``declared``: ``study_mode`` is set), as hani2.study_modes. */
export function pairingDefaults(mode: string | null | undefined, declared: boolean): Record<string, unknown> {
  const base: Record<string, unknown> = { scope: "project", assign: "random", slack: 1, cell_scenario: "type", allow_same_assistant: false, fallback: "ai", fallback_opponents: null };
  return declared && mode === "paired" ? { ...base, scope: "study", assign: "cells" } : base;
}

/** How a match is formed (``pairing.assign``), in the order a mode prefers (its default first). */
export function assignOptions(mode: string | null | undefined): { value: string; label: string }[] {
  const all: Record<string, string> = {
    cells: "cells: balance who meets whom (match cells)",
    order: "order: each person's planned order, strictly",
    random: "random: anyone who fits",
  };
  const keys = mode === "paired" ? ["cells", "order", "random"] : ["random", "cells", "order"];
  return keys.map((k, i) => ({ value: k, label: `${all[k]}${i === 0 ? " (the default here)" : ""}` }));
}

export interface SchedulingUse {
  /** why the dimension's method is not used in this mode ("" when it is) */
  opponents: string;
  assistants: string;
  cross: string;
  /** what the method means in this mode ("" when as in Solo) */
  assistantsHint: string;
  scenariosHint: string;
}

/** Which scheduling dimensions a mode uses: in Paired the opponent is the other person (no opponent
 *  method, no crossing), and a Paired HAN study plays without Assistants. */
export function schedulingUse(mode: string | null | undefined, kind: string): SchedulingUse {
  if (mode !== "paired")
    return { opponents: "", assistants: "", cross: "", assistantsHint: mode === "mixed" ? "Solo games use the method as a slot; a match with a person uses it as a set (see ?)" : "", scenariosHint: "" };
  return {
    opponents: "Not used in Paired: the opponent is the other person; the AI fallback draws from Fallback opponents",
    assistants: kind === "opponent" ? "Not used: a Paired HAN study plays without Assistants (assistants: [none])" : "",
    cross: "Not used in Paired: there is no AI opponent sequence to cross with the Assistants",
    assistantsHint: kind === "opponent" ? "" : "In Paired, the method gives each person a set of Assistants; pairing picks from it, so the order is a preference",
    scenariosHint: "In Paired, the joiner takes the host's scenario; by_participant pairs only people of the same scenario type",
  };
}

/** The opponent pool the env.json layers give under the files (the server's ``editor.pools``). */
export const envOpponents = (ed: any): string[] => items(ed?.pools?.opponents?.env);

export interface LiveMode {
  declared: string | null;
  derived: Mode;
  mode: string;
  opponents: unknown;
  assistants: unknown;
  /** the pool comes from an env.json layer (no file names one) */
  fromEnv: boolean;
  kind: string;
}

/** The mode of a layer being edited: its own unsaved values, else the project's (``ed.inherited``),
 *  else, for the pool, the env.json layers' (``ed.pools``). ``kind``: the project's (unsaved) kind. */
export function liveMode(own: any, ed: any, kind?: string): LiveMode {
  const inh = ed?.inherited ?? {};
  const env = envOpponents(ed);
  const filePool = own?.opponents ?? inh.opponents;
  const fromEnv = filePool == null && env.length > 0;
  const opponents = fromEnv ? env : filePool;
  const declared: string | null = own?.study_mode ?? inh.study_mode ?? null;
  const derived = derive(opponents);
  return { declared, derived, mode: declared ?? derived, opponents, assistants: own?.assistants ?? inh.assistants, fromEnv, kind: kind ?? ed?.kind ?? "none" };
}
