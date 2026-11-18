import { useEffect, useMemo, useState } from "react";
import { useUiState } from "../store";
import { ChevronDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import type { Component } from "../types";
import { Anchor } from "./Anchor";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";
import { Plot } from "./Plot";
import { Gauge } from "./Gauge";
import { fmtCell, fmtValue } from "./format";

export interface RenderCtx {
  onInput: (name: string, value: any) => void;
  onAction: (action: string, payload: Record<string, any>) => void;
  values: Record<string, any>;
  reserved?: number | null;
  /** disables every input and button (e.g. offer controls while it is not your turn) */
  disabled?: boolean;
  /** draws an ``issue`` component (the default control of one issue) */
  renderIssue?: (c: Component) => React.ReactNode;
  /** an anchor id for an input with this name (so highlights and notes can target it) */
  anchorFor?: (name: string) => string | undefined;
}

const ALERT: Record<string, string> = {
  info: "border-you/30 bg-you/5",
  success: "border-good/30 bg-good/5",
  warning: "border-warn/40 bg-warn/10",
  error: "border-bad/40 bg-bad/5",
  neutral: "border-line bg-sunken",
  tip: "border-good/30 bg-good/5",
};
const BADGE: Record<string, string> = {
  primary: "bg-you/10 text-you",
  success: "bg-good/10 text-good",
  warning: "bg-warn/15 text-warn",
  error: "bg-bad/10 text-bad",
  neutral: "bg-sunken text-muted",
};
const BTN: Record<string, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  success: "btn-success",
  danger: "btn-danger",
  ghost: "btn-ghost",
};
const GAP = (g?: number) => ({ gap: `${(g ?? 3) * 0.25}rem` });

const noop = () => {};
/** The context of views that only show something (an offer in the history or on the table). */
export const STATIC_CTX = { onInput: noop, onAction: noop };

function collectNames(cs: Component[], out: Record<string, any>) {
  for (const c of cs) {
    if (c.name !== undefined && "value" in c) out[c.name] = c.value;
    if (Array.isArray(c.children)) collectNames(c.children, out);
  }
  return out;
}

export function Renderer({ components, ctx }: { components: Component[]; ctx: Omit<RenderCtx, "values"> }) {
  // Local values of inputs (so typing is instant); server values win when they change.
  const serverValues = useMemo(() => collectNames(components, {}), [components]);
  const [values, setValues] = useState<Record<string, any>>(serverValues);
  useEffect(() => setValues(serverValues), [serverValues]);
  const full: RenderCtx = {
    ...ctx,
    values,
    onInput: (n, v) => {
      setValues((s) => ({ ...s, [n]: v }));
      ctx.onInput(n, v);
    },
    onAction: (a, p) => ctx.onAction(a, { ...values, ...p }),
  };
  const body = components.map((c, i) => <Node key={i} c={c} ctx={full} />);
  // a fieldset only where something can be disabled (offer controls); tool panes keep a plain div
  if (ctx.disabled !== undefined)
    return (
      <fieldset disabled={ctx.disabled} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
        {body}
      </fieldset>
    );
  return <div className="flex flex-col gap-3">{body}</div>;
}

function Node({ c, ctx }: { c: Component; ctx: RenderCtx }) {
  const node = <NodeBody c={c} ctx={ctx} />;
  const id = c.name !== undefined && c.type !== "issue" ? ctx.anchorFor?.(String(c.name)) : undefined;
  return id ? <Anchor id={id}>{node}</Anchor> : node;
}

function NodeBody({ c, ctx }: { c: Component; ctx: RenderCtx }) {
  const v = c.name !== undefined ? ctx.values[c.name] ?? c.value : undefined;
  switch (c.type) {
    case "issue":
      return ctx.renderIssue ? <>{ctx.renderIssue(c)}</> : null;
    case "markdown":
      return <Markdown text={c.text} size={c.size} />;
    case "text":
      return <p className={`text-sm ${c.muted ? "text-muted" : ""}`}>{c.text}</p>;
    case "heading": {
      const cls = c.level <= 2 ? "text-lg font-semibold" : c.level === 3 ? "text-base font-semibold" : "text-sm font-semibold";
      return <div className={cls}>{c.text}</div>;
    }
    case "alert":
      return (
        <div className={`rounded-lg border px-3 py-2 ${ALERT[c.kind] ?? ALERT.info}`}>
          {c.title && <div className="mb-0.5 text-sm font-semibold">{c.title}</div>}
          <Markdown text={c.text} size="sm" />
        </div>
      );
    case "badge":
      return <span className={`inline-flex w-fit rounded-md px-2 py-0.5 text-xs font-medium ${BADGE[c.kind] ?? BADGE.neutral}`}>{c.text}</span>;
    case "stat":
      return <Stat c={c} />;
    case "stats":
      return (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(110px,1fr))] gap-2">
          {(c.children || []).map((x: Component, i: number) => (
            <Stat key={i} c={x} />
          ))}
        </div>
      );
    case "kv":
      return (
        <div>
          {c.title && <div className="mb-1 text-sm font-semibold">{c.title}</div>}
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {(c.items || []).map(([k, val]: [string, any], i: number) => (
              <div key={i} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd className="tnum font-medium">{fmtValue(val)}</dd>
              </div>
            ))}
          </dl>
        </div>
      );
    case "html":
      return <div className="md" dangerouslySetInnerHTML={{ __html: sanitize(c.html) }} />;
    case "divider":
      return <hr className="border-line" />;
    case "progress":
      return (
        <div>
          {c.label && <div className="mb-1 text-xs text-muted">{c.label}</div>}
          <div className="h-2 rounded-full bg-sunken">
            <div className={`h-2 rounded-full ${c.kind === "error" ? "bg-bad" : c.kind === "success" ? "bg-good" : "bg-you"}`} style={{ width: `${Math.max(0, Math.min(1, c.value)) * 100}%` }} />
          </div>
        </div>
      );
    case "outcome":
      return (
        <div className="rounded-lg border border-line bg-sunken/50 p-2.5">
          {c.label && <div className="mb-1.5 text-xs font-medium text-muted">{c.label}</div>}
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(c.values || {}).map(([k, val]) => (
              <span key={k} className="chip">
                <span className="text-muted">{k}</span> <b className="font-semibold">{fmtValue(val)}</b>
              </span>
            ))}
          </div>
          {c.utility !== undefined && c.utility !== null && (
            <div className="mt-2">
              <Gauge value={c.utility} reserved={ctx.reserved} size="sm" />
            </div>
          )}
        </div>
      );
    case "plot":
      return <Plot figure={c.figure} height={c.height} />;
    case "table":
      return <DataTable c={c} ctx={ctx} />;
    case "button":
      return (
        <button
          className={`${BTN[c.variant] ?? "btn-secondary"} ${c.full ? "w-full" : "w-fit"}`}
          disabled={c.disabled}
          title={c.tooltip}
          onClick={() => ctx.onAction(c.action, c.payload || {})}
        >
          {c.icon && <Icon name={c.icon} size={15} />}
          {c.label}
        </button>
      );
    case "select":
      return (
        <Field label={c.label}>
          <select className="field" value={JSON.stringify(v)} disabled={c.disabled} onChange={(e) => ctx.onInput(c.name, JSON.parse(e.target.value))}>
            {(c.options || []).map((o: any, i: number) => (
              <option key={i} value={JSON.stringify(o.value)}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
      );
    case "multiselect": {
      const sel: any[] = Array.isArray(v) ? v : [];
      return (
        <Field label={c.label}>
          <div className="flex flex-wrap gap-1">
            {(c.options || []).map((o: any, i: number) => {
              const on = sel.some((x) => JSON.stringify(x) === JSON.stringify(o.value));
              return (
                <button
                  key={i}
                  aria-pressed={on}
                  className={`rounded-md border px-2 py-1 text-xs ${on ? "border-you bg-you/10 text-you" : "border-line bg-surface text-muted hover:text-ink"}`}
                  onClick={() => ctx.onInput(c.name, on ? sel.filter((x) => JSON.stringify(x) !== JSON.stringify(o.value)) : [...sel, o.value])}
                >
                  {o.label}
                </button>
              );
            })}
          </div>
        </Field>
      );
    }
    case "radio":
      return (
        <Field label={c.label}>
          <div className="inline-flex w-fit rounded-lg bg-sunken p-0.5">
            {(c.options || []).map((o: any, i: number) => {
              const on = JSON.stringify(v) === JSON.stringify(o.value);
              return (
                <button key={i} aria-pressed={on} className={`rounded-md px-2.5 py-1 text-xs font-medium ${on ? "bg-surface text-ink shadow-lift" : "text-muted hover:text-ink"}`} onClick={() => ctx.onInput(c.name, o.value)}>
                  {o.label}
                </button>
              );
            })}
          </div>
        </Field>
      );
    case "slider":
      return <Slider c={c} v={v} ctx={ctx} />;
    case "number":
      return (
        <Field label={c.label}>
          <input type="number" className="field tnum" value={v ?? ""} min={c.min} max={c.max} step={c.step ?? "any"} onChange={(e) => ctx.onInput(c.name, e.target.value === "" ? null : Number(e.target.value))} />
        </Field>
      );
    case "checkbox":
    case "switch":
      return (
        <label className="inline-flex w-fit cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--you))]" checked={!!v} onChange={(e) => ctx.onInput(c.name, e.target.checked)} />
          {c.label}
        </label>
      );
    case "textinput":
      return (
        <Field label={c.label}>
          <input className="field" value={v ?? ""} placeholder={c.placeholder} onChange={(e) => ctx.onInput(c.name, e.target.value)} />
        </Field>
      );
    case "textarea":
      return (
        <Field label={c.label}>
          <textarea className="field resize-y" rows={c.rows ?? 3} value={v ?? ""} placeholder={c.placeholder} onChange={(e) => ctx.onInput(c.name, e.target.value)} />
        </Field>
      );
    case "row":
      return (
        <div className={`flex ${c.wrap === false ? "" : "flex-wrap"} ${c.align === "end" ? "items-end" : c.align === "center" ? "items-center" : "items-start"}`} style={GAP(c.gap)}>
          {(c.children || []).map((x: Component, i: number) => (
            <div key={i} className="min-w-0">
              <Node c={x} ctx={ctx} />
            </div>
          ))}
        </div>
      );
    case "column":
      return (
        <div className="flex flex-col" style={GAP(c.gap)}>
          {(c.children || []).map((x: Component, i: number) => (
            <Node key={i} c={x} ctx={ctx} />
          ))}
        </div>
      );
    case "grid":
      return (
        <div className="grid" style={{ ...GAP(c.gap), gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${c.cols > 1 ? 260 : 9999}px), 1fr))` }}>
          {(c.children || []).map((x: Component, i: number) => (
            <div key={i} className="min-w-0">
              <Node c={x} ctx={ctx} />
            </div>
          ))}
        </div>
      );
    case "card":
      return <Card c={c} ctx={ctx} />;
    default:
      return <div className="text-xs text-muted">Unknown component “{c.type}”</div>;
  }
}

function Field({ label, children }: { label?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-[8rem]">
      {label && <span className="label">{label}</span>}
      {children}
    </div>
  );
}

function Stat({ c }: { c: Component }) {
  const color = c.kind === "success" ? "text-good" : c.kind === "error" ? "text-bad" : c.kind === "warning" ? "text-warn" : "text-ink";
  return (
    <div className="rounded-lg bg-sunken/70 px-3 py-2">
      <div className="text-xs text-muted">{c.label}</div>
      <div className={`tnum text-lg font-semibold ${color}`}>{fmtValue(c.value)}</div>
      {c.hint && <div className="text-[11px] leading-tight text-muted">{c.hint}</div>}
    </div>
  );
}

function Slider({ c, v, ctx }: { c: Component; v: any; ctx: RenderCtx }) {
  const [local, setLocal] = useState<number>(v ?? c.min);
  useEffect(() => setLocal(v ?? c.min), [v, c.min]);
  return (
    <div className="min-w-[10rem]">
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-medium text-muted">{c.label}</span>
        <span className="tnum font-semibold">
          {local}
          {c.suffix ?? ""}
        </span>
      </div>
      <input
        type="range"
        className="w-full accent-[rgb(var(--you))]"
        min={c.min}
        max={c.max}
        step={c.step ?? 1}
        value={local}
        onChange={(e) => setLocal(Number(e.target.value))}
        onPointerUp={() => ctx.onInput(c.name, local)}
        onKeyUp={() => ctx.onInput(c.name, local)}
      />
    </div>
  );
}

function Card({ c, ctx }: { c: Component; ctx: RenderCtx }) {
  const [open, setOpen] = useUiState<boolean>(c.id ? `r.${c.id}.open` : undefined, !c.collapsed);
  return (
    <section className="rounded-xl border border-line bg-surface">
      {c.title && (
        <button
          className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold ${c.collapsible ? "cursor-pointer" : "cursor-default"}`}
          onClick={() => c.collapsible && setOpen(!open)}
          aria-expanded={open}
        >
          {c.title}
          {c.collapsible && <ChevronDown size={16} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />}
        </button>
      )}
      {open && (
        <div className={`flex flex-col gap-3 px-3 pb-3 ${c.title ? "" : "pt-3"}`}>
          {(c.children || []).map((x: Component, i: number) => (
            <Node key={i} c={x} ctx={ctx} />
          ))}
        </div>
      )}
    </section>
  );
}

function DataTable({ c, ctx }: { c: Component; ctx: RenderCtx }) {
  const rows: any[] = c.rows || [];
  const cols: string[] = c.columns || [];
  const k = (n: string) => (c.id ? `r.${c.id}.${n}` : undefined);
  const [page, setPage] = useUiState(k("page"), 0);
  const [sort, setSort] = useUiState<{ col: string; dir: 1 | -1 } | null>(k("sort"), null);
  const [q, setQ] = useUiState(k("q"), "");
  const size = c.page_size || 25;
  const filtered = useMemo(() => {
    let r = rows.map((row, index) => ({ row, index }));
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter(({ row }) => cols.some((k) => String(row[k] ?? "").toLowerCase().includes(s)));
    }
    if (sort) {
      r = [...r].sort((a, b) => {
        const x = a.row[sort.col], y = b.row[sort.col];
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (x > y ? 1 : -1) * sort.dir;
      });
    }
    return r;
  }, [rows, q, sort, cols]);
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  const shown = filtered.slice(page * size, page * size + size);
  useEffect(() => setPage(0), [rows.length, q]);
  if (!rows.length) return <div className="text-sm text-muted">No rows.</div>;
  const isNum = (k: string) => rows.some((r) => typeof r[k] === "number");
  return (
    <div className="flex flex-col gap-2">
      {c.searchable && (
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-muted" />
          <input className="field pl-8" placeholder="Filter rows" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      )}
      <div className="scroll-thin overflow-auto rounded-lg border border-line" style={{ maxHeight: c.max_height ? `${c.max_height}px` : undefined }}>
        <table className="w-full border-collapse text-[0.8rem]">
          <thead className="sticky top-0 z-[1] bg-sunken">
            <tr>
              {cols.map((k) => (
                <th
                  key={k}
                  className={`whitespace-nowrap px-2.5 py-1.5 font-semibold text-muted ${isNum(k) ? "text-right" : "text-left"} ${c.sortable !== false ? "cursor-pointer hover:text-ink" : ""}`}
                  onClick={() => c.sortable !== false && setSort((s) => (s?.col === k ? { col: k, dir: (s.dir * -1) as 1 | -1 } : { col: k, dir: 1 }))}
                  aria-sort={sort?.col === k ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                >
                  {k}
                  {sort?.col === k ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ row, index }) => {
              const selected = c.selected === index;
              return (
                <tr
                  key={index}
                  className={`border-t border-line/70 ${c.on_select ? "cursor-pointer hover:bg-you/5" : ""} ${selected ? "bg-you/10" : ""}`}
                  onClick={() => c.on_select && ctx.onAction(c.on_select, { row, index })}
                  tabIndex={c.on_select ? 0 : undefined}
                  onKeyDown={(e) => c.on_select && e.key === "Enter" && ctx.onAction(c.on_select, { row, index })}
                >
                  {cols.map((k) => (
                    <td key={k} className={`px-2.5 py-1.5 align-top ${typeof row[k] === "number" ? "tnum text-right" : ""}`}>
                      {fmtCell(row[k], c.formats?.[k])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-xs text-muted">
          <span className="tnum">
            {page * size + 1}–{Math.min(filtered.length, (page + 1) * size)} of {filtered.length}
          </span>
          <button className="btn-ghost px-1.5" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page">
            <ChevronLeft size={15} />
          </button>
          <button className="btn-ghost px-1.5" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label="Next page">
            <ChevronRight size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function sanitize(html: string) {
  const doc = new DOMParser().parseFromString(html || "", "text/html");
  doc.querySelectorAll("script,iframe,object,embed,style,link").forEach((n) => n.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const a of Array.from(el.attributes)) {
      if (a.name.startsWith("on") || (a.name === "href" && a.value.trim().toLowerCase().startsWith("javascript:"))) el.removeAttribute(a.name);
    }
  });
  return doc.body.innerHTML;
}
