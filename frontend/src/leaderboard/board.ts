// The leaderboard API as the pages read it (schema hani2.leaderboard/2): the same endpoints a trusted
// website reads, so every page shows exactly the board HANI2 computes.
import { api } from "../api";

export type Interval = { mean: number | null; ci: [number | null, number | null] };
export type SortOption = { key: string; title: string; kind: "score" | "criterion"; description?: string; direction?: string; group?: string; validated?: boolean };
export type Entry = {
  rank: number;
  tied_with_leader: boolean;
  entrant: string;
  label: string;
  assistant?: string;
  opponent?: string;
  values: Record<string, Interval>;
  games: Record<string, number>;
  participants?: number;
  guests?: number;
  ci_unit?: string;
  abandon_rate?: number;
  cost_usd?: number | null;
  personas?: number;
};
export type Unranked = { entrant: string; label: string; games: Record<string, number>; reason: string };
export type ScoreInfo = { weights_in_effect: Record<string, number>; dropped: string[]; provisional: boolean; title?: string };
export type Board = {
  schema: string;
  project: string;
  study: string | null;
  track: "hi" | "han";
  source: "game" | "tournament";
  generated_at: string;
  data_version: string;
  query: Record<string, string>;
  options: { sort: SortOption[]; games?: string[]; stratum?: string[]; window?: string[]; defaults: Record<string, string>; groups?: { id: string; title: string }[]; validated_tooltip?: string };
  columns: string[];
  scores: Record<string, ScoreInfo>;
  rules: Record<string, any>;
  entries: Entry[];
  unranked: Unranked[];
  excluded: Record<string, number>;
  warnings: string[];
  notes?: string[];
  visibility?: string;
  stratum_title?: string;
  totals?: { sessions?: number; matches?: number; agreement_rate?: number | null; welfare?: number | null };
  reference?: { frozen?: boolean };
};

export const SWITCHES = ["games", "stratum", "window"] as const;
export type Switch = (typeof SWITCHES)[number];
export const COUNT_COLUMNS = ["games", "participants", "guests", "abandon_rate", "cost_usd"];

/** The API path of a board (a project's, or one study's). */
export function boardPath(project: string, study?: string | null) {
  const p = `/api/v1/projects/${encodeURIComponent(project)}`;
  return study ? `${p}/studies/${encodeURIComponent(study)}/leaderboard` : `${p}/leaderboard`;
}

/** ``GET`` a board. ``asUser``: as end users get it, even for an admin (the end-user pages). */
export function fetchBoard(project: string, study: string | null | undefined, query: Record<string, string>, asUser: boolean) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v) q.set(k, v);
  if (asUser) q.set("view", "user");
  const s = q.toString();
  return api<Board>(boardPath(project, study) + (s ? `?${s}` : ""));
}

/** The end-user page of a board, from the server's root (outside any study prefix). */
export function boardPage(root: string, project: string, study?: string | null) {
  return `${root}/s/${encodeURIComponent(project)}${study ? `/${encodeURIComponent(study)}` : ""}/leaderboard`;
}

const GAMES: Record<string, string> = { all: "All games", people: "Against people", ai: "Against AI" };
const STRATA: Record<string, string> = {
  combined: "Combined",
  solo: "Solo",
  paired: "Paired",
  alone: "Alone",
  vs_team: "With an Assistant",
  both: "Both (pooled)",
};
const STRATA_HINT: Record<string, string> = {
  combined: "Every game: Solo and Paired, cell-balanced",
  solo: "Games against AI opponents (including the fallbacks of Paired studies)",
  paired: "Games against another person with their own Assistant",
  alone: "The official board: people without an Assistant",
  vs_team: "People who had an Assistant (HI games against these agents)",
  both: "Alone and With an Assistant pooled together",
};
export const SWITCH_TITLE: Record<Switch, string> = { games: "Games", stratum: "Group", window: "Period" };

export function switchLabel(sw: string, v: string): string {
  if (sw === "games") return GAMES[v] ?? v;
  if (sw === "stratum") return STRATA[v] ?? v;
  if (v === "all") return "All time";
  const m = /^last_(\d+)_days$/.exec(v);
  return m ? `Last ${m[1]} days` : v;
}
export const switchHint = (sw: string, v: string) => (sw === "stratum" ? STRATA_HINT[v] : undefined);

const COUNT_TITLE: Record<string, string> = { games: "Games", participants: "Players", guests: "Guests", abandon_rate: "Abandoned", cost_usd: "Cost" };
const COUNT_HINT: Record<string, string> = {
  games: "Counted games in this view",
  participants: "Distinct players",
  guests: "Invited guests who played with this entrant",
  abandon_rate: "Share of its matches that were abandoned",
  cost_usd: "Language-model cost per game (US dollars)",
};

/** A column's title: a sort option's, a score's, a count's, or (admins) a criterion's from the catalogue. */
export function columnTitle(b: Board, key: string, titles?: Record<string, string>): string {
  return b.options.sort.find((o) => o.key === key)?.title ?? b.scores?.[key]?.title ?? COUNT_TITLE[key] ?? titles?.[key] ?? key;
}
export const columnHint = (b: Board, key: string) => b.options.sort.find((o) => o.key === key)?.description ?? COUNT_HINT[key];

/** The value columns an entry has (columns the server dropped are skipped; the sort key always shows, first). */
export function valueColumns(b: Board): string[] {
  if (b.source === "tournament") return b.columns.filter((k) => !COUNT_COLUMNS.includes(k));
  const have = new Set(b.entries.flatMap((e) => Object.keys(e.values)));
  const ok = (k: string) => !!k && !COUNT_COLUMNS.includes(k) && (have.has(k) || !b.entries.length);
  return [...new Set([b.query.sort, ...b.columns])].filter(ok);
}
export const countColumns = (b: Board) => b.columns.filter((k) => COUNT_COLUMNS.includes(k));

export function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(1);
  return v.toFixed(digits);
}

export function countValue(e: Entry, key: string): string {
  if (key === "games") return String(e.games?.all ?? 0);
  if (key === "participants") return e.participants === undefined ? "–" : String(e.participants);
  if (key === "guests") return e.guests === undefined ? "–" : String(e.guests);
  if (key === "abandon_rate") return e.abandon_rate === undefined ? "–" : `${Math.round(100 * e.abandon_rate)} %`;
  if (key === "cost_usd") return e.cost_usd === null || e.cost_usd === undefined ? "–" : `$${e.cost_usd.toFixed(3)}`;
  return "–";
}

/** "1", "=2" (tied with the leader: the intervals overlap). */
export const rankText = (e: Entry) => (e.tied_with_leader ? `=${e.rank}` : String(e.rank));

export function reasonText(reason: string, rules: Record<string, any>): string {
  if (reason === "min_games") return `Fewer than ${rules.min_games ?? "the minimum"} counted games`;
  if (reason === "min_participants") return `Fewer than ${rules.min_participants ?? "the minimum"} players outside its own team`;
  if (reason === "no_value") return "No value yet for this ranking";
  return reason;
}

/** The scale of a column's interval bars: [0, 1] when every number fits, else the range of the data. */
export function scaleOf(b: Board, key: string): [number, number] {
  const xs = b.entries.flatMap((e) => [e.values[key]?.mean, ...(e.values[key]?.ci ?? [])]).filter((x): x is number => typeof x === "number");
  if (!xs.length) return [0, 1];
  const lo = Math.min(...xs), hi = Math.max(...xs);
  if (lo >= 0 && hi <= 1) return [0, 1];
  if (lo >= -1 && hi <= 1) return [-1, 1];
  return lo === hi ? [lo - 1, hi + 1] : [lo, hi];
}

export const trackTitle = (t: string) => (t === "han" ? "Opponent agents (HAN)" : "Assistants (HI)");
