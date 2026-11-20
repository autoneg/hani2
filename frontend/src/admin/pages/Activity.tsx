import { useEffect, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { api } from "../../api";
import { withBase } from "../../router";
import { Plot } from "../../ui/Plot";
import { Renderer } from "../../ui/Renderer";
import { Group } from "../Group";
import { Row } from "../Row";
import { Select } from "../controls/Select";
import { TextField } from "../controls/TextField";
import { toast } from "../toast";
import { Spinner } from "../schema";

const ctx = { onInput: () => {}, onAction: () => {} };

export function Overview() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sum, setSum] = useState<any>(null);
  useEffect(() => {
    const load = () => {
      api("/api/admin/sessions").then(setRows).catch(() => {});
      api("/api/admin/events/summary").then(setSum).catch(() => {});
    };
    load();
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, []);
  const stats = [
    ["Open sessions", rows?.length ?? 0],
    ["Negotiating now", rows?.filter((r) => r.phase === "running").length ?? 0],
    ["Recorded sessions", sum?.n_sessions ?? "–"],
    ["Logged events", sum?.n_events ?? "–"],
  ];
  return (
    <>
      <div id="setting-stats" className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map(([l, v]) => (
          <div key={l} className="rounded-xl border border-line/80 bg-surface px-4 py-3">
            <div className="text-xs text-muted">{l}</div>
            <div className="tnum mt-0.5 text-2xl font-semibold tracking-tight">{v}</div>
          </div>
        ))}
      </div>
      <Group title="Sessions on this server" footer="Refreshes every 5 seconds. Idle sessions without an open tab are removed after six hours." id="setting-sessions">
        <div className="p-3">
          {rows === null ? <Loader2 className="animate-spin text-muted" /> : <Renderer components={[{ type: "table", rows, columns: ["user", "mode", "phase", "round", "scenario", "opponent", "support_agent", "connections", "idle"], searchable: true }]} ctx={ctx} />}
        </div>
      </Group>
    </>
  );
}

export function Results() {
  const [data, setData] = useState<any>(null);
  const [cols, setCols] = useState<string[]>([]);
  useEffect(() => {
    api("/api/admin/results").then((d) => {
      setData(d);
      setCols(d.default_columns.filter((c: string) => d.columns.includes(c)));
    }).catch((e) => toast(e.message, "error"));
  }, []);
  if (!data) return <Spinner />;
  return (
    <>
      <Group>
        <Row id="results-download" label="All results" hint={`${data.rows.length} negotiations from every participant`}>
          <a className="btn-secondary" href={withBase("/api/admin/results.csv")}>
            <Download size={15} /> Download CSV
          </a>
        </Row>
      </Group>
      {data.leaderboard.length > 0 && (
        <Group title="Leaderboard" id="setting-leaderboard">
          <div className="p-3">
            <Renderer components={[{ type: "table", rows: data.leaderboard, columns: ["user", "participant_type", "score", "negotiations", "mean_utility"], formats: { score: "float", mean_utility: "percent" }, page_size: 10 }]} ctx={ctx} />
          </div>
        </Group>
      )}
      {Object.keys(data.leaderboard_by_type ?? {}).length > 1 && (
        <Group title="Leaderboard by participant type" footer="Stratified by the participant type from the pre-questionnaire." id="setting-leaderboard-by-type">
          <div className="space-y-3 p-3">
            {Object.entries(data.leaderboard_by_type as Record<string, any[]>).map(([kind, rows]) => (
              <Renderer key={kind} components={[{ type: "card", title: kind || "type unknown", children: [{ type: "table", rows, columns: ["user", "score", "negotiations", "mean_utility"], formats: { score: "float", mean_utility: "percent" }, page_size: 10 }] }]} ctx={ctx} />
            ))}
          </div>
        </Group>
      )}
      {(data.simulated ?? []).length > 0 && (
        <Group title="Qualifying round (simulated participants)" footer="Simulated participants are never ranked with humans. Success: a deal worth at least the persona's reservation value." id="setting-simulated">
          <div className="p-3">
            <Renderer components={[{ type: "table", rows: data.simulated, columns: Object.keys(data.simulated[0]).filter((c) => c !== "mean_utility"), formats: Object.fromEntries(Object.keys(data.simulated[0]).filter((c) => c === "goal_rate" || c.startsWith("pass^")).map((c) => [c, "percent"])), page_size: 20 }]} ctx={ctx} />
          </div>
        </Group>
      )}
      <Group title="Negotiations" id="setting-results-table">
        <div className="p-3">
          <Renderer
            components={[
              { type: "card", title: "Choose columns", collapsible: true, collapsed: true, children: [{ type: "multiselect", name: "cols", options: data.columns.map((c: string) => ({ label: c, value: c })), value: cols }] },
              { type: "table", rows: [...data.rows].reverse(), columns: cols, searchable: true, formats: { human_utility: "percent", agent_utility: "percent", human_advantage: "percent" } },
            ]}
            ctx={{ onInput: (_: any, v: any) => setCols(v), onAction: () => {} }}
          />
        </div>
      </Group>
    </>
  );
}

export function Analytics() {
  const [sum, setSum] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [f, setF] = useState({ user: "", types: "", since: "", until: "" });
  const load = () => {
    api("/api/admin/events/summary").then(setSum).catch((e) => toast(e.message, "error"));
    const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as any).toString();
    api(`/api/admin/events?limit=2000&${q}`).then(setEvents).catch((e) => toast(e.message, "error"));
  };
  useEffect(load, []);
  const types = sum ? Object.keys(sum.by_type) : [];
  return (
    <>
      <Group>
        <Row id="events-export" label="Event log" hint="Everything participants and their Assistants did, as logged by the server">
          <a className="btn-secondary" href={withBase("/api/admin/events.csv")}>
            <Download size={15} /> Export CSV
          </a>
        </Row>
      </Group>
      {sum && (
        <div className="mb-6 grid gap-4 xl:grid-cols-2">
          <Group title="Events by type">
            <div className="p-3">
              <Plot height={280} figure={{ data: [{ type: "bar", orientation: "h", y: types, x: types.map((t) => sum.by_type[t]), marker: { color: "#3B4BDB" } }], layout: { margin: { l: 130, r: 10, t: 10, b: 30 }, yaxis: { automargin: true } } }} />
            </div>
          </Group>
          <Group title="Activity over time (per hour)">
            <div className="p-3">
              <Plot height={280} figure={{ data: [{ type: "scatter", mode: "lines", fill: "tozeroy", x: sum.by_hour.map((r: any) => r.hour + ":00"), y: sum.by_hour.map((r: any) => r.count), line: { color: "#D9821B" } }], layout: { margin: { l: 40, r: 10, t: 10, b: 40 } } }} />
            </div>
          </Group>
        </div>
      )}
      <Group title="Filter events" id="setting-events-filter">
        <Row label="User">
          <Select label="User" value={f.user} onChange={(v) => setF({ ...f, user: v })} options={[{ value: "", label: "Everyone" }, ...(sum?.users ?? [])]} />
        </Row>
        <Row label="Event type">
          <Select label="Event type" value={f.types} onChange={(v) => setF({ ...f, types: v })} options={[{ value: "", label: "All types" }, ...types]} />
        </Row>
        <Row label="From / until">
          <TextField label="From" type="date" className="w-40" value={f.since} onChange={(v) => setF({ ...f, since: v })} />
          <TextField label="Until" type="date" className="w-40" value={f.until} onChange={(v) => setF({ ...f, until: v })} />
        </Row>
        <Row label="">
          <button className="btn-primary" onClick={load}>
            <RefreshCw size={14} /> Apply
          </button>
        </Row>
      </Group>
      <Group title="Events">
        <div className="p-3">
          <Renderer components={[{ type: "table", rows: events, columns: ["timestamp", "user", "event_type", "component", "action", "value", "scenario_id", "utility_value"], searchable: true, page_size: 50 }]} ctx={ctx} />
        </div>
      </Group>
      {sum?.sessions?.length > 0 && (
        <Group title="Recorded sessions">
          <div className="p-3">
            <Renderer components={[{ type: "table", rows: sum.sessions, columns: ["start_time", "end_time", "user", "mode", "project", "study", "user_agent"], searchable: true }]} ctx={ctx} />
          </div>
        </Group>
      )}
    </>
  );
}
