import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BarChart3, Download, FileDown, Loader2, Play, RefreshCw, Scale, Upload } from "lucide-react";
import { api, apiRaw } from "../api";
import { navigate, withBase } from "../router";
import { useStore } from "../store";
import { downloadText, fmtDuration, fmtNum, toCsv } from "./csv";

export interface RecInfo {
  key: string;
  id: string;
  user?: string;
  sid?: string;
  mode?: string;
  started?: string | number;
  duration?: number;
  scenario?: string;
  opponent?: string;
  mechanism_id?: string;
  status?: string;
  ended_by?: string;
  human_utility?: number | null;
  agent_utility?: number | null;
  support_agent?: boolean;
  questionnaire?: boolean;
  experiment?: string;
  file?: string;
  size?: number;
  complete?: boolean;
  location?: string;
}
export interface MetricInfo {
  name: string;
  kind: "hard" | "soft" | "subjective";
  title: string;
  description: string;
  needs_llm: boolean;
  default: boolean;
  columns: { name: string; title: string; description: string; higher_is_better: boolean | null }[];
}
interface Col {
  name: string;
  metric?: string;
  kind?: string;
  title: string;
  description?: string;
  higher_is_better?: boolean | null;
}

const toast = (message: string, level: "success" | "error" = "success") => useStore.getState().pushToast({ message, level });
const when = (v: any) => {
  if (v == null) return "–";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return isNaN(d.getTime()) ? String(v) : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
};
const kb = (n?: number) => (n == null ? "–" : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} kB`);
export const openRecording = (key: string) => navigate(`/replay?key=${encodeURIComponent(key)}`);

function Table({ cols, rows, empty }: { cols: Col[]; rows: Record<string, any>[]; empty?: string }) {
  return (
    <div className="scroll-thin overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-left text-sm">
        <thead className="bg-sunken/60 text-xs text-muted">
          <tr>
            {cols.map((c) => (
              <th key={c.name} className="whitespace-nowrap px-3 py-2 font-medium" title={c.description || c.title}>
                {c.title}
                {c.higher_is_better === true ? " ↑" : c.higher_is_better === false ? " ↓" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line/70">
              {cols.map((c) => (
                <td key={c.name} className="tnum whitespace-nowrap px-3 py-1.5">
                  {fmtNum(r[c.name])}
                </td>
              ))}
            </tr>
          ))}
          {!rows.length && (
            <tr>
              <td className="px-3 py-4 text-center text-muted" colSpan={cols.length}>
                {empty || "Nothing to show"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- evaluation / comparison panel ---------------- */
function Analysis({ keys, mode, onClose }: { keys: string[]; mode: "evaluate" | "compare"; onClose: () => void }) {
  const [metrics, setMetrics] = useState<MetricInfo[] | null>(null);
  const [llm, setLlm] = useState<{ configured: boolean; model?: string }>({ configured: false });
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [useLlm, setUseLlm] = useState(false);
  const [refresh, setRefresh] = useState(false);
  const [by, setBy] = useState("opponent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<any>(null);

  useEffect(() => {
    api<{ metrics: MetricInfo[]; llm: any }>("/api/replay/metrics")
      .then((m) => {
        setMetrics(m.metrics);
        setLlm(m.llm || { configured: false });
        setSel(new Set(m.metrics.filter((x) => x.default).map((x) => x.name)));
      })
      .catch((e) => {
        setMetrics([]);
        setError(`Could not load the metric list: ${e.message}`);
      });
  }, []);
  useEffect(() => setRes(null), [mode]);

  const groups: [string, string][] = [
    ["hard", "Hard (computed from the recording)"],
    ["soft", "Soft (LLM)"],
    ["subjective", "Subjective (questionnaire)"],
  ];
  const toggle = (n: string) =>
    setSel((s) => {
      const x = new Set(s);
      x.has(n) ? x.delete(n) : x.add(n);
      return x;
    });
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const names = [...sel];
      const body = mode === "evaluate" ? { keys, metrics: names.length ? names : null, llm: useLlm, refresh } : { keys, metrics: names.length ? names : null, by, llm: useLlm };
      setRes(await api(`/api/replay/${mode}`, { body }));
    } catch (e: any) {
      setError(e.message || String(e));
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  const evalCols: Col[] = res?.columns ?? [];
  const idCols: Col[] = [
    { name: "id", title: "Recording" },
    { name: "user", title: "User" },
    { name: "scenario", title: "Scenario" },
    { name: "opponent", title: "Opponent" },
    { name: "support_agent", title: "Assistant" },
  ];
  const exportEval = () => {
    const cs = [...idCols, ...evalCols];
    downloadText("evaluation.csv", toCsv(cs.map((c) => c.name), (res.rows as any[]).map((r) => cs.map((c) => r[c.name]))));
  };
  const cmpCols: Col[] = res?.columns ?? [];
  const exportCmp = () => {
    const head = ["group", "n", ...cmpCols.flatMap((c) => [`${c.name}_mean`, `${c.name}_std`])];
    downloadText("comparison.csv", toCsv(head, (res.groups as any[]).map((g) => [g.group, g.n, ...cmpCols.flatMap((c) => [g.mean?.[c.name], g.std?.[c.name]])])));
  };

  return (
    <section className="panel mt-4 p-4">
      <div className="mb-3 flex items-center gap-2">
        {mode === "evaluate" ? <BarChart3 size={17} className="text-you" /> : <Scale size={17} className="text-you" />}
        <h2 className="flex-1 text-base font-semibold">
          {mode === "evaluate" ? "Evaluate" : "Compare"} {keys.length} recording{keys.length === 1 ? "" : "s"}
        </h2>
        <button className="btn-ghost px-2 py-1 text-xs" onClick={onClose}>
          Close
        </button>
      </div>
      {metrics === null ? (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Loader2 size={15} className="animate-spin" /> Loading metrics…
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {groups.map(([kind, title]) => {
            const ms = metrics.filter((m) => m.kind === kind);
            return (
              <div key={kind}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</div>
                {ms.length === 0 && <div className="text-xs text-muted">None available</div>}
                {ms.map((m) => (
                  <label key={m.name} className="flex cursor-pointer items-start gap-2 py-0.5 text-sm" title={m.description}>
                    <input type="checkbox" className="mt-1 accent-[rgb(var(--you))]" checked={sel.has(m.name)} onChange={() => toggle(m.name)} />
                    <span>
                      {m.title}
                      {m.needs_llm && <span className="ml-1 text-[10px] text-muted">LLM</span>}
                    </span>
                  </label>
                ))}
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-line pt-3 text-sm">
        <label className={`flex items-center gap-2 ${llm.configured ? "" : "opacity-50"}`} title={llm.configured ? `Judge: ${llm.model ?? ""}` : "No language model is configured"}>
          <input type="checkbox" disabled={!llm.configured} checked={useLlm && llm.configured} onChange={(e) => setUseLlm(e.target.checked)} className="accent-[rgb(var(--you))]" />
          Use LLM judge
        </label>
        {mode === "evaluate" ? (
          <label className="flex items-center gap-2" title="Recompute instead of using cached values">
            <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} className="accent-[rgb(var(--you))]" />
            Refresh
          </label>
        ) : (
          <label className="flex items-center gap-2">
            Group by
            <select className="field w-auto" value={by} onChange={(e) => setBy(e.target.value)}>
              {["opponent", "support_agent", "user", "scenario", "experiment"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        )}
        <button className="btn-primary" disabled={busy || !keys.length} onClick={run}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <BarChart3 size={15} />} Run
        </button>
      </div>
      {error && <div className="mt-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>}
      {res && mode === "evaluate" && (
        <div className="mt-4">
          <div className="mb-2 flex items-center">
            <div className="flex-1 text-sm font-medium">Results</div>
            <button className="btn-secondary px-2 py-1 text-xs" onClick={exportEval}>
              <FileDown size={14} /> CSV
            </button>
          </div>
          <Table cols={[...idCols, ...evalCols]} rows={res.rows || []} />
          {res.errors && Object.keys(res.errors).length > 0 && (
            <details className="mt-2 text-xs text-bad">
              <summary className="cursor-pointer">Some metrics failed</summary>
              <pre className="mt-1 whitespace-pre-wrap">{JSON.stringify(res.errors, null, 1)}</pre>
            </details>
          )}
        </div>
      )}
      {res && mode === "compare" && (
        <div className="mt-4 flex flex-col gap-4">
          <div>
            <div className="mb-2 flex items-center">
              <div className="flex-1 text-sm font-medium">By {res.by}</div>
              <button className="btn-secondary px-2 py-1 text-xs" onClick={exportCmp}>
                <FileDown size={14} /> CSV
              </button>
            </div>
            <Table
              cols={[{ name: "group", title: res.by }, { name: "n", title: "n" }, ...cmpCols.map((c) => ({ ...c, name: c.name }))]}
              rows={(res.groups || []).map((g: any) => ({
                group: g.group,
                n: g.n,
                ...Object.fromEntries(cmpCols.map((c) => [c.name, g.mean?.[c.name] == null ? null : `${fmtNum(g.mean[c.name])} ± ${fmtNum(g.std?.[c.name] ?? 0)}`])),
              }))}
            />
          </div>
          {res.reliability?.length > 0 && (
            <div>
              <div className="mb-2 text-sm font-medium" title="pass^k: the probability that all k attempts succeed">
                Reliability (pass^k)
              </div>
              <Table cols={[{ name: "group", title: res.by }, { name: "k", title: "k" }, { name: "pass_hat_k", title: "pass^k" }]} rows={res.reliability} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/* ---------------- the library ---------------- */
type SortKey = keyof RecInfo;
export function Library() {
  const [recs, setRecs] = useState<RecInfo[] | null>(null);
  const [roots, setRoots] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [q, setQ] = useState("");
  const [f, setF] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 }>({ k: "started", dir: -1 });
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [panel, setPanel] = useState<null | "evaluate" | "compare">(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError(null);
    api<{ recordings: RecInfo[]; roots: string[] }>(`/api/replay/recordings?all=${all}`)
      .then((r) => {
        setRecs(r.recordings);
        setRoots(r.roots || []);
      })
      .catch((e) => {
        setRecs([]);
        setError(e.status === 401 || e.status === 403 ? "This page is for administrators." : e.message);
      });
  }, [all]);
  useEffect(load, [load]);

  const options = (k: keyof RecInfo) => [...new Set((recs ?? []).map((r) => r[k]).filter((v) => v != null && v !== "").map(String))].sort();
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    let r = (recs ?? []).filter((x) => (!s || JSON.stringify(x).toLowerCase().includes(s)) && Object.entries(f).every(([k, v]) => !v || String((x as any)[k] ?? "") === v));
    r = [...r].sort((a, b) => {
      const x: any = a[sort.k],
        y: any = b[sort.k];
      if (x === y) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : -1) * sort.dir;
    });
    return r;
  }, [recs, q, f, sort]);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) await apiRaw(`/api/replay/upload?name=${encodeURIComponent(file.name)}`, file);
      toast(`Uploaded ${files.length} file${files.length === 1 ? "" : "s"}`);
      load();
    } catch (e: any) {
      toast(`Upload failed: ${e.message}`, "error");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const head = (k: SortKey, label: string, cls = "") => (
    <th className={`whitespace-nowrap px-3 py-2 font-medium ${cls}`}>
      <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort((s) => ({ k, dir: s.k === k ? (-s.dir as 1 | -1) : 1 }))}>
        {label}
        {sort.k === k && (sort.dir === 1 ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
      </button>
    </th>
  );
  const allSel = rows.length > 0 && rows.every((r) => sel.has(r.key));
  const keys = [...sel];

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input className="field max-w-xs" placeholder="Search recordings…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
        {(["user", "opponent", "status", "scenario"] as const).map((k) => (
          <select key={k} className="field w-auto" value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} aria-label={`Filter by ${k}`}>
            <option value="">All {k === "status" ? "statuses" : k + "s"}</option>
            {options(k).map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        ))}
        <label className="flex items-center gap-1.5 text-sm text-muted" title="Include recordings of other users and of the whole results folder">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="accent-[rgb(var(--you))]" /> All locations
        </label>
        <div className="flex-1" />
        <button className="btn-ghost px-2" onClick={load} aria-label="Refresh">
          <RefreshCw size={16} />
        </button>
        <input ref={fileRef} type="file" accept=".hrec,.jsonl,.gz" multiple className="hidden" onChange={(e) => upload(e.target.files)} />
        <button className="btn-secondary" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} Upload .hrec
        </button>
        <button className="btn-secondary" disabled={!keys.length} onClick={() => setPanel("evaluate")}>
          <BarChart3 size={15} /> Evaluate selected{keys.length ? ` (${keys.length})` : ""}
        </button>
        <button className="btn-secondary" disabled={keys.length < 2} onClick={() => setPanel("compare")}>
          <Scale size={15} /> Compare selected
        </button>
      </div>
      {error && <div className="mb-3 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</div>}
      <div className="scroll-thin overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="bg-sunken/60 text-xs text-muted">
            <tr>
              <th className="w-8 px-3 py-2">
                <input type="checkbox" aria-label="Select all" checked={allSel} onChange={() => setSel(allSel ? new Set() : new Set(rows.map((r) => r.key)))} className="accent-[rgb(var(--you))]" />
              </th>
              {head("started", "Started")}
              {head("user", "User")}
              {head("scenario", "Scenario")}
              {head("opponent", "Opponent")}
              {head("status", "Status")}
              {head("human_utility", "You", "text-right")}
              {head("agent_utility", "Partner", "text-right")}
              {head("duration", "Duration", "text-right")}
              {head("support_agent", "Assistant")}
              {head("size", "Size", "text-right")}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {recs === null && (
              <tr>
                <td colSpan={12} className="px-3 py-6 text-center text-muted">
                  <Loader2 size={16} className="mr-2 inline animate-spin" /> Loading…
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-line/70 hover:bg-sunken/40">
                <td className="px-3 py-1.5">
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.id}`}
                    checked={sel.has(r.key)}
                    onChange={() =>
                      setSel((s) => {
                        const x = new Set(s);
                        x.has(r.key) ? x.delete(r.key) : x.add(r.key);
                        return x;
                      })
                    }
                    className="accent-[rgb(var(--you))]"
                  />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5" title={r.id}>
                  {when(r.started)}
                  {r.complete === false && <span className="chip ml-1.5 text-warn">partial</span>}
                </td>
                <td className="px-3 py-1.5">{r.user ?? "–"}</td>
                <td className="px-3 py-1.5">{r.scenario ?? "–"}</td>
                <td className="px-3 py-1.5">{r.opponent ?? "–"}</td>
                <td className="px-3 py-1.5">{r.status ?? "–"}</td>
                <td className="tnum px-3 py-1.5 text-right">{r.human_utility != null ? r.human_utility.toFixed(2) : "–"}</td>
                <td className="tnum px-3 py-1.5 text-right">{r.agent_utility != null ? r.agent_utility.toFixed(2) : "–"}</td>
                <td className="tnum whitespace-nowrap px-3 py-1.5 text-right">{fmtDuration(r.duration)}</td>
                <td className="px-3 py-1.5">{r.support_agent ? "yes" : "no"}</td>
                <td className="tnum px-3 py-1.5 text-right text-muted">{kb(r.size)}</td>
                <td className="whitespace-nowrap px-3 py-1.5 text-right">
                  <button className="btn-secondary px-2 py-1 text-xs" onClick={() => openRecording(r.key)}>
                    <Play size={13} /> Open
                  </button>
                  <a className="btn-ghost ml-1 px-1.5 py-1" href={withBase(`/api/replay/download?key=${encodeURIComponent(r.key)}`)} aria-label="Download" title="Download the .hrec file">
                    <Download size={14} />
                  </a>
                </td>
              </tr>
            ))}
            {recs && !rows.length && (
              <tr>
                <td colSpan={12} className="px-3 py-6 text-center text-muted">
                  No recordings{recs.length ? " match the filters" : " yet. Every negotiation is recorded automatically"}.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {roots.length > 0 && <div className="mt-2 text-xs text-muted">Searching {roots.join(", ")}</div>}
      {panel && <Analysis keys={keys} mode={panel} onClose={() => setPanel(null)} />}
    </div>
  );
}
