import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { api } from "../api";
import { withBase } from "../router";
import { fmtDuration, fmtNum, fmtTime } from "./csv";
import type { FidelityReport, Replay } from "./reconstruct";
import { COLOR, KINDS, type Kind, type TimelineItem } from "./summary";
import type { RecInfo } from "./Library";
import { InfoButton, ReferenceButton } from "./MetricReference";

/* ---------------- events ---------------- */
export function EventsPanel({ items, T, onSeek }: { items: TimelineItem[]; T: number; onSeek: (t: number) => void }) {
  const [on, setOn] = useState<Set<Kind>>(new Set(KINDS.filter((k) => k.defaultOn).map((k) => k.kind)));
  const [follow, setFollow] = useState(true);
  const shown = useMemo(() => items.filter((i) => on.has(i.kind)), [items, on]);
  let cur = -1;
  {
    let lo = 0,
      hi = shown.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (shown[mid].t <= T) {
        cur = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
  }
  const refs = useRef<Record<number, HTMLButtonElement | null>>({});
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!follow || cur < 0) return;
    const el = refs.current[cur];
    const b = box.current;
    if (el && b) {
      const top = el.offsetTop - b.clientHeight / 2;
      b.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    }
  }, [cur, follow]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap gap-1 border-b border-line p-2">
        {KINDS.map((k) => (
          <button
            key={k.kind}
            onClick={() =>
              setOn((s) => {
                const x = new Set(s);
                x.has(k.kind) ? x.delete(k.kind) : x.add(k.kind);
                return x;
              })
            }
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] ${on.has(k.kind) ? "border-line bg-sunken text-ink" : "border-transparent text-muted line-through"}`}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: k.color }} /> {k.label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1 text-[11px] text-muted">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} className="accent-[rgb(var(--you))]" /> Follow
        </label>
      </div>
      <div ref={box} className="scroll-thin relative min-h-0 flex-1 overflow-y-auto">
        {shown.map((i, n) => (
          <button
            key={n}
            ref={(el) => {
              refs.current[n] = el;
            }}
            onClick={() => onSeek(i.t)}
            style={{ contentVisibility: "auto", containIntrinsicSize: "0 28px" }}
            className={`flex w-full items-start gap-2 border-b border-line/50 px-2.5 py-1 text-left text-xs hover:bg-sunken/60 ${n === cur ? "bg-you/10" : n > cur ? "" : "opacity-70"}`}
          >
            <span className="tnum w-12 shrink-0 text-muted">{fmtTime(i.t)}</span>
            <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: COLOR[i.kind] }} />
            <span className="min-w-0 break-words">{i.text}</span>
          </button>
        ))}
        {!shown.length && <div className="p-4 text-center text-xs text-muted">No events of these kinds.</div>}
      </div>
    </div>
  );
}

/* ---------------- metrics ---------------- */
export function MetricsPanel({ rkey }: { rkey: string }) {
  const [useLlm, setUseLlm] = useState(false);
  const [llm, setLlm] = useState<{ configured: boolean; model?: string }>({ configured: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<any>(null);
  const run = (refresh = false) => {
    setBusy(true);
    setError(null);
    api("/api/replay/evaluate", { body: { keys: [rkey], metrics: null, llm: useLlm, refresh } })
      .then(setRes)
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  };
  useEffect(() => {
    api("/api/replay/metrics")
      .then((m: any) => setLlm(m.llm || { configured: false }))
      .catch(() => {});
  }, []);
  useEffect(() => run(), [rkey, useLlm]);
  const row = res?.rows?.[0] ?? {};
  const cols: any[] = res?.columns ?? [];
  const errors = res?.errors?.[rkey] ?? {};
  const groups: [string, string][] = [
    ["hard", "Hard"],
    ["soft", "Soft (LLM)"],
    ["subjective", "Subjective"],
  ];
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3 text-sm">
      <div className="mb-3 flex items-center gap-3">
        <label className={`flex items-center gap-1.5 text-xs ${llm.configured ? "" : "opacity-50"}`} title={llm.configured ? `Judge: ${llm.model ?? ""}` : "No language model is configured"}>
          <input type="checkbox" disabled={!llm.configured} checked={useLlm && llm.configured} onChange={(e) => setUseLlm(e.target.checked)} className="accent-[rgb(var(--you))]" /> Use LLM judge
        </label>
        <ReferenceButton className="ml-auto" />
        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => run(true)} disabled={busy}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
      </div>
      {error && <div className="mb-2 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">{error}</div>}
      {groups.map(([kind, title]) => {
        const cs = cols.filter((c) => c.kind === kind);
        if (!cs.length) return null;
        return (
          <section key={kind} className="mb-4">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</div>
            <div className="rounded-lg border border-line">
              {cs.map((c) => (
                <div key={c.name} className="flex items-center gap-1 border-b border-line/60 px-2.5 py-1 last:border-0">
                  <span className="text-xs">{c.title}</span>
                  <InfoButton name={c.name} label={`About ${c.title}`} />
                  <span className="flex-1" />
                  <span className="tnum font-medium">{fmtNum(row[c.name])}</span>
                </div>
              ))}
            </div>
          </section>
        );
      })}
      {Object.keys(errors).length > 0 && (
        <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-xs text-bad">
          {Object.entries(errors).map(([m, msg]) => (
            <div key={m}>
              {m}: {String(msg)}
            </div>
          ))}
        </div>
      )}
      {res?.details?.[rkey] && Object.keys(res.details[rkey]).length > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted">Details</summary>
          <pre className="scroll-thin mt-1 max-h-72 overflow-auto rounded-lg bg-sunken p-2">{JSON.stringify(res.details[rkey], null, 1)}</pre>
        </details>
      )}
      {!busy && !error && !cols.length && <div className="text-xs text-muted">No metrics are available.</div>}
    </div>
  );
}

/* ---------------- fidelity ---------------- */
export function FidelityPanel({ replay, onSeek }: { replay: Replay; onSeek: (t: number) => void }) {
  const [rep, setRep] = useState<FidelityReport | null>(null);
  useEffect(() => {
    setRep(null);
    const h = window.setTimeout(() => setRep(replay.verify()), 20);
    return () => window.clearTimeout(h);
  }, [replay]);
  if (!replay.hasTelemetry)
    return <div className="p-4 text-sm text-muted">This recording has no client telemetry (it was made without the browser reporting), so the reconstruction cannot be verified.</div>;
  if (!rep)
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-muted">
        <Loader2 size={15} className="animate-spin" /> Verifying…
      </div>
    );
  const bad = rep.items.filter((i) => !i.ok);
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3 text-sm">
      <div className={`mb-3 rounded-lg border px-3 py-2 ${bad.length ? "border-warn/40 bg-warn/10" : "border-good/30 bg-good/10"}`}>
        <div className="font-medium">
          {rep.matched}/{rep.items.length} checkpoints match
        </div>
        <div className="text-xs text-muted">The browser hashed the state it showed; the reconstruction from the recording must produce the same hash.</div>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-line p-2">
          <div className="text-muted">Messages recorded</div>
          <div className="tnum text-base font-semibold">{rep.recorded}</div>
        </div>
        <div className="rounded-lg border border-line p-2">
          <div className="text-muted">Received by the browser</div>
          <div className="tnum text-base font-semibold">
            {rep.received}
            {rep.received === rep.recorded ? "" : ` (${rep.recorded - rep.received} not reported)`}
          </div>
        </div>
      </div>
      {rep.missing.length > 0 && (
        <div className="mb-3 text-xs text-muted">
          Missing sequence numbers (recorded, never confirmed by the client): {rep.missing.slice(0, 40).join(", ")}
          {rep.missing.length > 40 ? ` … and ${rep.missing.length - 40} more` : ""}
        </div>
      )}
      {bad.length > 0 && <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Mismatches</div>}
      {bad.map((b, n) => (
        <button key={n} className="mb-1.5 block w-full rounded-lg border border-line p-2 text-left text-xs hover:bg-sunken/60" onClick={() => onSeek(b.t)}>
          <div className="flex gap-2">
            <span className="tnum font-medium">{fmtTime(b.t)}</span>
            <span className="text-muted">seq {b.seq}</span>
            <span className="tnum ml-auto text-muted">
              {b.expected} vs {b.got}
            </span>
          </div>
          {b.note && <div className="mt-1">{b.note}</div>}
          {b.keys && b.keys.length > 0 && <div className="mt-1 text-muted">Differing keys: {b.keys.join(", ")}</div>}
        </button>
      ))}
    </div>
  );
}

/* ---------------- info ---------------- */
function KV({ k, v }: { k: string; v: any }) {
  if (v === null || v === undefined || v === "") return null;
  return (
    <div className="flex gap-3 border-b border-line/60 py-1 text-xs">
      <div className="w-28 shrink-0 text-muted">{k}</div>
      <div className="min-w-0 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</div>
    </div>
  );
}
export function InfoPanel({ replay, rkey, meta }: { replay: Replay; rkey: string; meta?: RecInfo | null }) {
  const h = replay.header;
  const last = (k: string) => [...replay.events].reverse().find((e) => e.k === k);
  const sc = last("scenario");
  const start = last("start");
  const res = last("result");
  const q = last("questionnaire");
  const n = (k: string) => replay.events.filter((e) => e.k === k).length;
  return (
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">
      <KV k="Recording" v={h.id} />
      <KV k="Created" v={h.created} />
      <KV k="User" v={h.session?.user} />
      <KV k="Mode" v={h.session?.mode} />
      <KV k="Session" v={h.session?.sid} />
      <KV k="Experiment" v={h.experiment} />
      <KV k="Duration" v={fmtDuration(replay.duration)} />
      <KV k="File size" v={meta?.size != null ? `${(meta.size / 1024).toFixed(1)} kB` : null} />
      <KV k="Location" v={meta?.location} />
      <KV k="Scenario" v={sc?.name} />
      <KV k="Parties" v={sc?.parties?.join(", ")} />
      <KV k="Issues" v={sc?.issue_names?.join(", ")} />
      <KV k="Opponent" v={start?.opponent} />
      <KV k="Mechanism" v={start?.mechanism_id} />
      <KV k="Assistant" v={start?.support_agent ? `${start.support_agent.name ?? ""} ${start.support_agent.model ?? ""}`.trim() || "yes" : "none"} />
      <KV k="Autopilot" v={start?.autopilot ? "on" : null} />
      <KV k="Status" v={res?.summary?.status} />
      <KV k="Ended by" v={res?.summary?.ended_by} />
      <KV k="Your utility" v={res?.summary?.human_utility != null ? fmtNum(res.summary.human_utility) : null} />
      <KV k="Opponent utility" v={res?.summary?.agent_utility != null ? fmtNum(res.summary.agent_utility) : null} />
      <KV k="Agreement" v={res?.agreement} />
      <KV k="Questionnaire" v={q ? q.answers : null} />
      <KV k="Records" v={`${replay.events.length} (${n("out")} messages out, ${n("in")} in, ${n("tel")} telemetry batches, ${n("llm")} LLM calls, ${n("fn")} functions)`} />
      <KV k="Browser" v={h.session?.user_agent} />
      <a className="btn-secondary mt-3 w-full" href={withBase(`/api/replay/download?key=${encodeURIComponent(rkey)}`)}>
        <Download size={15} /> Download .hrec
      </a>
    </div>
  );
}
