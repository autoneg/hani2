// One board: its switches (only those the response offers), the ranked entrants with their intervals
// and ties, the entrants not ranked yet with the reason, and what the board left out. Shared by the
// end-user pages and Admin → Leaderboards.
import { ArrowDownWideNarrow, Info } from "lucide-react";
import {
  type Board,
  type Entry,
  type SortOption,
  SWITCHES,
  SWITCH_TITLE,
  columnHint,
  columnTitle,
  countColumns,
  countValue,
  fmt,
  rankText,
  reasonText,
  scaleOf,
  switchHint,
  switchLabel,
  valueColumns,
} from "./board";

export type SortGroup = { label: string; options: SortOption[] };

/** A row of buttons, one per value (``aria-pressed`` on the chosen one). */
function Choice({ label, value, values, onChange, render, hint }: { label: string; value: string; values: string[]; onChange: (v: string) => void; render: (v: string) => string; hint?: (v: string) => string | undefined }) {
  return (
    <div role="group" aria-label={label} className="flex min-w-0 max-w-full flex-wrap gap-1 rounded-lg bg-sunken p-1">
      {values.map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          title={hint?.(v)}
          onClick={() => v !== value && onChange(v)}
          className={`rounded-md px-2.5 py-1 text-sm transition-colors ${v === value ? "bg-surface font-medium text-ink shadow-lift" : "text-muted hover:text-ink"}`}
        >
          {render(v)}
        </button>
      ))}
    </div>
  );
}

/** The interval as a bar: the band from low to high, the mean as a dot. */
export function CiBar({ mean, lo, hi, scale, strong }: { mean: number | null; lo: number | null; hi: number | null; scale: [number, number]; strong?: boolean }) {
  if (mean === null) return null;
  const [a, b] = scale;
  const pos = (x: number) => `${Math.max(0, Math.min(100, (100 * (x - a)) / (b - a || 1)))}%`;
  return (
    <div className="relative h-2 w-full min-w-[4rem] rounded-full bg-line/60" aria-hidden>
      {lo !== null && hi !== null && <div className={`absolute top-0 h-2 rounded-full ${strong ? "bg-you/35" : "bg-muted/30"}`} style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />}
      <div className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface ${strong ? "bg-you" : "bg-muted"}`} style={{ left: pos(mean) }} />
    </div>
  );
}

function ciText(iv?: { mean: number | null; ci: [number | null, number | null] }) {
  if (!iv || iv.ci[0] === null || iv.ci[1] === null) return null;
  return `${fmt(iv.ci[0])} – ${fmt(iv.ci[1])}`;
}

function Provisional() {
  return <span className="ml-1 rounded bg-warn/15 px-1 text-[0.65rem] font-medium uppercase tracking-wide text-warn" title="Provisional: the judge has not rated enough games yet, or no normalisation reference is frozen">provisional</span>;
}

function Rank({ e }: { e: Entry }) {
  return (
    <span className={`tnum inline-flex min-w-[2.25rem] justify-center rounded-md px-1.5 py-0.5 text-sm font-semibold ${e.rank === 1 ? "bg-you text-white" : e.tied_with_leader ? "bg-you/15 text-you" : "bg-sunken text-ink"}`} title={e.tied_with_leader ? "Tied with the leader: their intervals overlap" : undefined} data-rank={rankText(e)}>
      {rankText(e)}
    </span>
  );
}

function EntrantName({ e, admin }: { e: Entry; admin?: boolean }) {
  const spec = e.assistant ?? e.opponent;
  return (
    <div className="min-w-0">
      <div className="truncate font-medium">{e.label}</div>
      {admin && <div className="truncate font-mono text-[0.7rem] text-muted" title={spec}>{e.entrant !== e.label ? e.entrant : spec}</div>}
    </div>
  );
}

export function BoardView({ board: b, onQuery, sortGroups, titles, admin, busy }: {
  board: Board;
  onQuery: (q: Record<string, string>) => void;
  /** more sort keys (admins: criteria from the catalogue), shown after the board's own */
  sortGroups?: SortGroup[];
  titles?: Record<string, string>;
  admin?: boolean;
  busy?: boolean;
}) {
  const vcols = valueColumns(b);
  const ccols = countColumns(b);
  const sort = b.query.sort;
  const tournament = b.source === "tournament";
  const set = (k: string, v: string) => onQuery({ ...b.query, [k]: v });
  const sortOpts = b.options.sort;
  const extra = (sortGroups ?? []).map((g) => ({ ...g, options: g.options.filter((o) => !sortOpts.some((x) => x.key === o.key)) })).filter((g) => g.options.length);
  const known = sortOpts.some((o) => o.key === sort) || extra.some((g) => g.options.some((o) => o.key === sort));
  const scales = Object.fromEntries(vcols.map((k) => [k, scaleOf(b, k)]));
  const prov = (k: string) => !!b.scores?.[k]?.provisional;
  const title = (k: string) => columnTitle(b, k, titles);
  return (
    <div className={busy ? "opacity-60 transition-opacity" : "transition-opacity"} data-board data-sort={sort}>
      {!tournament && (
        <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3">
          <label className="flex min-w-0 flex-col gap-1">
            <span className="flex items-center gap-1 text-xs font-medium text-muted"><ArrowDownWideNarrow size={13} /> Ranked by</span>
            <select aria-label="Ranked by" value={sort} onChange={(e) => set("sort", e.target.value)} className="w-full max-w-full rounded-lg border border-line bg-surface py-1.5 pl-2.5 pr-8 text-sm sm:w-auto sm:min-w-[12rem] sm:max-w-xs text-ink focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20">
              {!known && <option value={sort}>{title(sort)}</option>}
              {extra.length ? (
                <optgroup label="This board">
                  {sortOpts.map((o) => <option key={o.key} value={o.key}>{o.title}{prov(o.key) ? " (provisional)" : ""}</option>)}
                </optgroup>
              ) : (
                sortOpts.map((o) => <option key={o.key} value={o.key}>{o.title}{prov(o.key) ? " (provisional)" : ""}</option>)
              )}
              {extra.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.options.map((o) => <option key={o.key} value={o.key}>{o.title}{o.direction === "lower" ? " (lower is better)" : ""}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
          {SWITCHES.filter((sw) => (b.options[sw]?.length ?? 0) > 1).map((sw) => (
            <div key={sw} className="flex min-w-0 max-w-full flex-col gap-1">
              <span className="text-xs font-medium text-muted">{SWITCH_TITLE[sw]}</span>
              <Choice label={SWITCH_TITLE[sw]} value={b.query[sw]} values={b.options[sw]!} onChange={(v) => set(sw, v)} render={(v) => switchLabel(sw, v)} hint={(v) => switchHint(sw, v)} />
            </div>
          ))}
        </div>
      )}
      {b.options.sort.find((o) => o.key === sort)?.description && <p className="mb-3 text-sm text-muted">{b.options.sort.find((o) => o.key === sort)!.description}</p>}

      {b.entries.length === 0 ? (
        <div className="panel px-4 py-10 text-center text-sm text-muted" data-empty>No entrant is ranked in this view yet.</div>
      ) : (
        <>
          {/* phones: one card per entrant */}
          <ol className="space-y-2 sm:hidden" aria-label="Ranking">
            {b.entries.map((e) => (
              <li key={e.entrant} className="panel px-3 py-2.5" data-entrant={e.entrant}>
                <div className="flex items-center gap-3">
                  <Rank e={e} />
                  <EntrantName e={e} admin={admin} />
                  {vcols[0] && <div className="tnum ml-auto text-right text-base font-semibold">{fmt(e.values[vcols[0]]?.mean)}</div>}
                </div>
                {vcols[0] && !tournament && (
                  <div className="mt-2 flex items-center gap-2">
                    <CiBar mean={e.values[vcols[0]]?.mean ?? null} lo={e.values[vcols[0]]?.ci[0] ?? null} hi={e.values[vcols[0]]?.ci[1] ?? null} scale={scales[vcols[0]]} strong />
                    <span className="tnum shrink-0 text-[0.7rem] text-muted">{ciText(e.values[vcols[0]])}</span>
                  </div>
                )}
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
                  {vcols.slice(1).map((k) => (
                    <div key={k} className="flex justify-between gap-2"><dt className="truncate text-muted">{title(k)}</dt><dd className="tnum">{fmt(e.values[k]?.mean)}</dd></div>
                  ))}
                  {ccols.map((k) => (
                    <div key={k} className="flex justify-between gap-2"><dt className="truncate text-muted">{title(k)}</dt><dd className="tnum">{countValue(e, k)}</dd></div>
                  ))}
                </dl>
              </li>
            ))}
          </ol>
          {/* wider screens: a table */}
          <div className="panel hidden overflow-x-auto sm:block">
            <table className="w-full border-collapse text-sm" aria-label="Ranking">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="w-14 whitespace-nowrap px-3 py-2 font-medium">Rank</th>
                  <th className="px-3 py-2 font-medium">{b.track === "han" ? "Opponent" : "Assistant"}</th>
                  {vcols.map((k, i) => (
                    <th key={k} className={`whitespace-nowrap px-3 py-2 font-medium ${i === 0 && !tournament ? "text-ink" : "text-right"}`} title={columnHint(b, k)}>
                      {title(k)}
                      {prov(k) && <Provisional />}
                      {k === sort && !tournament && <span className="sr-only"> (ranked by)</span>}
                    </th>
                  ))}
                  {ccols.map((k) => (
                    <th key={k} className="whitespace-nowrap px-3 py-2 text-right font-medium" title={columnHint(b, k)}>{title(k)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.entries.map((e) => (
                  <tr key={e.entrant} className="border-b border-line/60 last:border-0" data-entrant={e.entrant}>
                    <td className="px-3 py-2"><Rank e={e} /></td>
                    <td className="max-w-[16rem] px-3 py-2"><EntrantName e={e} admin={admin} /></td>
                    {vcols.map((k, i) =>
                      i === 0 && !tournament ? (
                        <td key={k} className="px-3 py-2">
                          <div className="flex items-center gap-3 whitespace-nowrap">
                            <span className="tnum w-10 text-right font-semibold">{fmt(e.values[k]?.mean)}</span>
                            <div className="w-20 shrink-0 xl:w-28">
                              <CiBar mean={e.values[k]?.mean ?? null} lo={e.values[k]?.ci[0] ?? null} hi={e.values[k]?.ci[1] ?? null} scale={scales[k]} strong />
                            </div>
                            <span className="tnum shrink-0 text-xs text-muted">{ciText(e.values[k])}</span>
                          </div>
                        </td>
                      ) : (
                        <td key={k} className="tnum whitespace-nowrap px-3 py-2 text-right" title={ciText(e.values[k]) ?? undefined}>
                          {fmt(e.values[k]?.mean)}
                          {ciText(e.values[k]) && <div className="text-[0.7rem] text-muted">{ciText(e.values[k])}</div>}
                        </td>
                      ),
                    )}
                    {ccols.map((k) => (
                      <td key={k} className="tnum whitespace-nowrap px-3 py-2 text-right" title={k === "games" ? `${e.games.people ?? 0} against people · ${e.games.ai ?? 0} against AI` : undefined}>
                        {countValue(e, k)}
                        {k === "games" && e.games.people !== undefined && <div className="text-[0.7rem] text-muted">{e.games.people} people · {e.games.ai} AI</div>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {b.unranked.length > 0 && (
        <section className="mt-5" aria-label="Not ranked yet" data-unranked>
          <h3 className="mb-2 text-sm font-semibold">Not ranked yet</h3>
          <ul className="panel divide-y divide-line/60">
            {b.unranked.map((u) => (
              <li key={u.entrant} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-sm" data-entrant={u.entrant}>
                <span className="font-medium">{u.label}</span>
                {admin && u.entrant !== u.label && <span className="font-mono text-[0.7rem] text-muted">{u.entrant}</span>}
                <span className="text-muted">{reasonText(u.reason, b.rules)}</span>
                <span className="tnum ml-auto text-xs text-muted">{u.games?.all ?? 0} games</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <About b={b} admin={admin} />
    </div>
  );
}

/** How to read the board: the interval, ties, minimums and what was left out (counts only). */
function About({ b, admin }: { b: Board; admin?: boolean }) {
  const ci = Math.round(100 * Number(b.rules?.ci ?? 0.95));
  const excluded = Object.entries(b.excluded ?? {}).filter(([, n]) => n > 0);
  return (
    <details className="mt-5 text-sm" open={admin}>
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-muted hover:text-ink">
        <Info size={14} /> How to read this board
      </summary>
      <div className="mt-2 space-y-2 text-muted">
        {b.source === "tournament" ? (
          <p>Simulated participants negotiated with each Assistant. The goal rate is the share of deals worth at least the persona's value on disagreement.</p>
        ) : (
          <>
            <p>
              Each value is the mean over the counted games, with its {ci} % confidence interval (the band). “=2” means tied with the leader: the two intervals overlap.
              {b.rules?.min_games !== undefined && ` An entrant needs ${b.rules.min_games} counted games and ${b.rules.min_participants} players outside its own team to be ranked.`}
            </p>
            {b.stratum_title && <p>This view: {b.stratum_title}.</p>}
            {excluded.length > 0 && <p data-excluded>Left out: {excluded.map(([k, n]) => `${k} ${n}`).join(" · ")}.</p>}
            {b.totals?.sessions !== undefined && (
              <p>
                {b.totals.sessions} games
                {b.totals.matches ? ` (${b.totals.matches} matches between people)` : ""}
                {typeof b.totals.agreement_rate === "number" ? `, ${Math.round(100 * b.totals.agreement_rate)} % ended in a deal` : ""}.
              </p>
            )}
          </>
        )}
        {(b.notes ?? []).map((n) => <p key={n}>{n}</p>)}
        <p>No names are shown: only entrants and counts.</p>
      </div>
    </details>
  );
}
