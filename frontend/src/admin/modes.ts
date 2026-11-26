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
      ? { perNegotiation: true, warn: true, text: `${head}: random_each can repeat an Assistant, but Repeats is off: saving is refused` }
      : { perNegotiation: true, warn: false, text: `${head}: drawn each negotiation, so repeats can happen` };
  if (K == null || N == null || N <= 0) return { perNegotiation: true, warn: false, text: head };
  if (K > N)
    return repeats === true
      ? { perNegotiation: true, warn: false, text: `${head}: K > N, and Repeats is on: the Assistants wrap around` }
      : { perNegotiation: true, warn: true, text: `${head}: K > N but each Assistant is used at most once: saving is refused (lower K, add Assistants or turn Repeats on)` };
  return { perNegotiation: true, warn: false, text: `${head}: each Assistant at most once per person${K === N ? " (every Assistant once)" : ""}` };
}

/** Opponent methods the crossing shifts. */
export const CROSSED_OPPONENTS = ["latin_square", "cyclic"];
/** Whether ``cross: shift`` changes anything for these methods. */
export const crossingActive = (assistants: string | null | undefined, opponents: string | null | undefined, cross: string | null | undefined) =>
  cross === "shift" && PER_NEGOTIATION.includes(assistants ?? "") && CROSSED_OPPONENTS.includes(opponents ?? "");
