import { useEffect, useMemo, useRef, useState } from "react";
import { create } from "zustand";
import { BookOpen, ChevronRight, Info, Loader2, Search, X } from "lucide-react";
import { api } from "../api";
import { Markdown } from "../ui/Markdown";
import { loadKatex, Tex } from "../ui/math";

/* The metric reference: what every metric and column measures and how it is
   calculated, from GET /api/replay/metric-reference (the metric definitions).
   Opened on click (ⓘ buttons, "Metric reference"), never on hover. */

export interface RefColumn {
  name: string;
  title: string;
  description: string;
  higher_is_better: boolean | null;
  formula: string;
  details: string;
  range: string;
}
export interface RefMetric {
  name: string;
  kind: string;
  title: string;
  description: string;
  needs_llm: boolean;
  default: boolean;
  columns: RefColumn[];
  formula: string;
  details: string;
  patterns: RefColumn[];
  figures: string[];
  options: Record<string, string>;
}
export interface Reference {
  notation: string;
  kinds: Record<string, { title: string; description: string }>;
  metrics: RefMetric[];
  aggregates: RefColumn[];
  identifiers: { name: string; title: string; description: string }[];
  figures: Record<string, { title: string; caption: string; svg: string }>;
}

export const useMetricRef = create<{ open: boolean; target: string | null; nonce: number; show: (target?: string | null) => void; close: () => void }>((set) => ({
  open: false,
  target: null,
  nonce: 0,
  show: (target = null) => set((s) => ({ open: true, target, nonce: s.nonce + 1 })),
  close: () => set({ open: false }),
}));

let cache: Promise<Reference> | null = null;
const loadReference = () => (cache ??= api<Reference>("/api/replay/metric-reference").catch((e) => ((cache = null), Promise.reject(e))));

/** A small ⓘ button that opens the reference at `name` (a metric, column or compare statistic). */
export function InfoButton({ name, label, className = "" }: { name: string; label?: string; className?: string }) {
  const show = useMetricRef((s) => s.show);
  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center rounded p-0.5 align-middle text-muted/70 hover:bg-sunken hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-you ${className}`}
      aria-label={label ?? `About ${name}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        show(name);
      }}
    >
      <Info size={12} />
    </button>
  );
}

/** A button that opens the whole reference. */
export function ReferenceButton({ className = "" }: { className?: string }) {
  const show = useMetricRef((s) => s.show);
  return (
    <button type="button" className={`btn-ghost px-2 py-1 text-xs ${className}`} onClick={() => show(null)}>
      <BookOpen size={13} /> Metric reference
    </button>
  );
}

const patternRx = (name: string) => new RegExp("^" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/<[^>]*>/g, ".+") + "$");

/** Where `name` lives: the metric and (maybe) the column, or a section key. */
function resolve(ref: Reference, name: string): string[] {
  const m = ref.metrics.find((x) => x.name === name);
  if (m) return [`m:${m.name}`];
  for (const x of ref.metrics) {
    const c = x.columns.find((c) => c.name === name) ?? x.patterns.find((c) => c.name.includes("<") && patternRx(c.name).test(name));
    // the metric's column list (not its long body) and the column itself
    if (c) return [`l:${x.name}`, `c:${x.name}/${c.name}`];
  }
  if (ref.aggregates.some((a) => a.name === name)) return ["s:compare", `c:compare/${name}`];
  if (name === "notation") return ["s:notation"];
  return [];
}

const dir = (h: boolean | null) => (h === true ? "higher is better" : h === false ? "lower is better" : "no better direction");
const has = (q: string, ...xs: (string | undefined)[]) => xs.some((x) => x && x.toLowerCase().includes(q));
const colHit = (q: string, c: RefColumn) => has(q, c.name, c.title, c.description, c.details);

function Row({ id, open, onToggle, head, children }: { id: string; open: boolean; onToggle: () => void; head: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div id={`ref-${id}`} className={`scroll-mt-2 ${open ? "bg-sunken/40" : ""}`}>
      <button type="button" className="flex w-full items-start gap-1.5 px-3 py-1.5 text-left hover:bg-sunken/70" aria-expanded={open} onClick={onToggle}>
        <ChevronRight size={14} className={`mt-0.5 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
        <span className="min-w-0 flex-1">{head}</span>
      </button>
      {open && <div className="px-3 pb-3 pl-8">{children}</div>}
    </div>
  );
}

function ColumnBody({ c }: { c: RefColumn }) {
  return (
    <>
      <div className="mb-1 flex flex-wrap gap-1.5 text-[11px]">
        {c.range && <span className="chip">range: {c.range}</span>}
        <span className="chip">{dir(c.higher_is_better)}</span>
      </div>
      {c.formula && <Tex tex={c.formula} display />}
      {c.details && <Markdown text={c.details} size="sm" math />}
    </>
  );
}

function ColumnHead({ c }: { c: RefColumn }) {
  return (
    <>
      <span className="text-[13px] font-medium">{c.title}</span> <code className="text-[11px] text-muted">{c.name}</code>
      {c.higher_is_better != null && <span className="ml-1 text-[11px] text-muted">{c.higher_is_better ? "↑" : "↓"}</span>}
      <span className="block text-xs text-muted">{c.description}</span>
    </>
  );
}

export function MetricReferenceSheet() {
  const { open, target, nonce, close } = useMetricRef();
  const [ref, setRef] = useState<Reference | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [exp, setExp] = useState<Set<string>>(new Set());
  const body = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open || ref) return;
    setError(null);
    loadReference().then(setRef, (e) => setError(e.message || String(e)));
  }, [open, ref]);
  // open at the target
  useEffect(() => {
    if (!open || !ref) return;
    const keys = target ? resolve(ref, target) : [];
    setQ("");
    setExp(new Set(keys));
    const last = keys[keys.length - 1];
    // scroll once the formulas are typeset (they change the heights)
    const go = () =>
      window.setTimeout(() => {
        const el = last ? document.getElementById(`ref-${last}`) : null;
        if (el) el.scrollIntoView({ block: "start" });
        else body.current?.scrollTo({ top: 0 });
      }, 30);
    loadKatex().then(go, go);
    if (!target) search.current?.focus();
  }, [open, ref, target, nonce]);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  }, [open, close]);

  const toggle = (k: string) =>
    setExp((s) => {
      const x = new Set(s);
      x.has(k) ? x.delete(k) : x.add(k);
      return x;
    });
  const query = q.trim().toLowerCase();
  const groups = useMemo(() => {
    if (!ref) return [];
    return Object.entries(ref.kinds)
      .map(([kind, info]) => ({
        kind,
        info,
        metrics: ref.metrics
          .filter((m) => m.kind === kind)
          .map((m) => {
            const cols = [...m.columns, ...m.patterns];
            const hitCols = query ? cols.filter((c) => colHit(query, c)) : cols;
            const hitSelf = !query || has(query, m.name, m.title, m.description, m.details);
            return { m, cols: hitSelf ? cols : hitCols, hitCols, show: hitSelf || hitCols.length > 0 };
          })
          .filter((x) => x.show),
      }))
      .filter((g) => g.metrics.length);
  }, [ref, query]);
  const aggs = ref ? ref.aggregates.filter((c) => !query || colHit(query, c)) : [];
  const nHits = groups.reduce((a, g) => a + g.metrics.length, 0) + aggs.length;

  if (!open) return null;
  return (
    <aside
      role="dialog"
      aria-label="Metric reference"
      className="enter fixed inset-y-0 right-0 z-[55] flex w-full flex-col border-l border-line bg-surface shadow-pop sm:w-[min(640px,94vw)]"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <BookOpen size={16} className="text-you" />
        <h2 className="flex-1 text-sm font-semibold">Metric reference</h2>
        <span className="hidden text-[11px] text-muted sm:inline">Esc to close</span>
        <button className="btn-ghost px-1.5" onClick={close} aria-label="Close the metric reference">
          <X size={16} />
        </button>
      </div>
      <div className="border-b border-line px-4 py-2">
        <label className="flex items-center gap-2 rounded-lg border border-line bg-paper px-2.5 py-1.5 focus-within:border-you">
          <Search size={14} className="text-muted" />
          <input
            ref={search}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted focus-visible:outline-none"
            placeholder="Search metrics and columns (e.g. pareto, nash, pass^k, ueq)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search the metric reference"
          />
          {q && (
            <button className="text-muted hover:text-ink" onClick={() => setQ("")} aria-label="Clear the search">
              <X size={13} />
            </button>
          )}
        </label>
      </div>
      <div ref={body} className="scroll-thin min-h-0 flex-1 overflow-y-auto pb-6">
        {error && <div className="m-4 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">Could not load the reference: {error}</div>}
        {!ref && !error && (
          <div className="flex items-center gap-2 p-4 text-sm text-muted">
            <Loader2 size={15} className="animate-spin" /> Loading…
          </div>
        )}
        {ref && (
          <>
            {!query && (
              <section className="border-b border-line">
                <Row id="s:notation" open={exp.has("s:notation")} onToggle={() => toggle("s:notation")} head={<span className="text-sm font-semibold">Notation</span>}>
                  <Markdown text={ref.notation} size="sm" math />
                </Row>
              </section>
            )}
            {groups.map((g) => (
              <section key={g.kind} className="border-b border-line">
                <div className="px-4 pb-1 pt-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted">{g.info.title}</div>
                  {!query && <div className="text-xs text-muted">{g.info.description}</div>}
                </div>
                {g.metrics.map(({ m, cols, hitCols }) => {
                  const mk = `m:${m.name}`;
                  const mOpen = exp.has(mk);
                  const listCols = mOpen || exp.has(`l:${m.name}`) ? cols : query ? hitCols : [];
                  return (
                    <div key={m.name} className="border-t border-line/60 first:border-t-0">
                      <Row
                        id={mk}
                        open={mOpen}
                        onToggle={() => toggle(mk)}
                        head={
                          <>
                            <span className="text-sm font-semibold">{m.title}</span> <code className="text-[11px] text-muted">{m.name}</code>
                            {m.needs_llm && <span className="ml-1.5 text-[10px] text-muted">LLM</span>}
                            {!m.default && <span className="ml-1.5 text-[10px] text-muted">not default</span>}
                            <span className="block text-xs text-muted">{m.description}</span>
                          </>
                        }
                      >
                        {m.formula && <Tex tex={m.formula} display />}
                        {m.details && <Markdown text={m.details} size="sm" math />}
                        {m.figures.map((f) =>
                          ref.figures[f] ? (
                            <figure key={f} className="my-3 rounded-lg border border-line bg-surface p-2 text-ink">
                              <div className="mx-auto max-w-[560px] [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: ref.figures[f].svg }} />
                              <figcaption className="mt-1 text-[11px] leading-snug text-muted">{ref.figures[f].caption}</figcaption>
                            </figure>
                          ) : null,
                        )}
                        {Object.keys(m.options).length > 0 && (
                          <div className="mt-2 text-xs">
                            <div className="font-semibold">Options</div>
                            {Object.entries(m.options).map(([k, v]) => (
                              <div key={k}>
                                <code>{k}</code> — {v}
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">Columns</div>
                      </Row>
                      {listCols.length > 0 && (
                        <div className={mOpen ? "bg-sunken/40 pb-1 pl-5" : "pl-5"}>
                          {listCols.map((c) => {
                            const ck = `c:${m.name}/${c.name}`;
                            return (
                              <Row key={c.name} id={ck} open={exp.has(ck)} onToggle={() => toggle(ck)} head={<ColumnHead c={c} />}>
                                <ColumnBody c={c} />
                              </Row>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </section>
            ))}
            {aggs.length > 0 && (
              <section id="ref-s:compare" className="border-b border-line">
                <div className="px-4 pb-1 pt-3">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted">Comparing groups</div>
                  {!query && <div className="text-xs text-muted">The statistics of Compare, per group and numeric column.</div>}
                </div>
                {aggs.map((c) => {
                  const ck = `c:compare/${c.name}`;
                  return (
                    <Row key={c.name} id={ck} open={exp.has(ck)} onToggle={() => toggle(ck)} head={<ColumnHead c={c} />}>
                      <ColumnBody c={c} />
                    </Row>
                  );
                })}
              </section>
            )}
            {query && nHits === 0 && <div className="p-4 text-sm text-muted">Nothing matches “{q}”.</div>}
          </>
        )}
      </div>
    </aside>
  );
}
