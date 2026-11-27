// Admin → Hosted agents: the Assistants and opponents teams run on their own machines (hani2.hosting).
// Register a team's address, give the team its token (shown once), check that the host answers, switch
// an agent off, and make a project's Assistants or opponents self-hosted (its `hosted:` block).
import { useEffect, useState } from "react";
import { Activity, Bot, KeyRound, Plus, Swords, Trash2 } from "lucide-react";
import { api } from "../../api";
import { Group } from "../Group";
import { InfoRow, Row, Tile } from "../Row";
import { Select } from "../controls/Select";
import { Stepper } from "../controls/Stepper";
import { TextField } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { CopyField } from "../CopyField";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";

export const HOSTED_ENTRIES = [
  { id: "hosted-mode", label: "Self-hosted mode", hint: "The project's Assistants and/or opponents are the registered hosted agents", keywords: "remote self-hosted hosted assistants opponents mode" },
  { id: "hosted-add", label: "Register a hosted agent", hint: "A team's address and token", keywords: "remote url address token team register" },
  { id: "hosted-list", label: "Hosted agents", hint: "Check, switch off, new token, remove", keywords: "remote check health token" },
];

interface Agent { name: string; kind: string; url: string; team?: string; enabled?: boolean; timeout?: number | null; spec: string; has_token: boolean }
interface Mode { assistants: boolean; opponents: boolean; timeout: number; max_failures: number }

export function Hosted() {
  const [projects, setProjects] = useState<any[] | null>(null);
  const [project, setProject] = useState("");
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [checks, setChecks] = useState<Record<string, any>>({});
  const [n, setN] = useState({ name: "", kind: "assistant", url: "", team: "" });
  const [token, setToken] = useState<{ name: string; token: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api("/api/admin/projects")
      .then((d: any) => {
        const ps = d.projects ?? [];
        setProjects(ps);
        const first = ps.find((p: any) => p.name !== "default") ?? ps[0];
        if (first) setProject(first.name);
      })
      .catch((e) => setErr(e.message));
  }, []);
  const base = `/api/admin/projects/${encodeURIComponent(project)}`;
  const load = () =>
    api(`${base}/hosted`)
      .then((d: any) => (setAgents(d.agents), setMode(d.mode), setErr(null)))
      .catch((e) => setErr(e.message));
  useEffect(() => {
    if (!project) return;
    setAgents(null);
    setChecks({});
    setToken(null);
    load();
  }, [project]);
  if (!projects) return err ? <Note tone="warn">{err}</Note> : <Spinner />;
  const saveMode = async (m: Mode) => {
    try {
      const d: any = await api(`${base}/hosted-mode`, { method: "PUT", body: m });
      setMode(d.mode);
      toast("Saved");
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const add = async () => {
    try {
      const d: any = await api(`${base}/hosted`, { body: n });
      if (d.token) setToken({ name: n.name, token: d.token });
      toast(`Registered remote:${n.name}`);
      setN({ name: "", kind: n.kind, url: "", team: "" });
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const check = async (a: Agent) => {
    setChecks((c: Record<string, any>) => ({ ...c, [a.name]: { busy: true } }));
    try {
      const r = await api(`${base}/hosted/${encodeURIComponent(a.name)}/check`, { method: "POST" });
      setChecks((c: Record<string, any>) => ({ ...c, [a.name]: r }));
    } catch (e: any) {
      setChecks((c: Record<string, any>) => ({ ...c, [a.name]: { ok: false, error: e.message } }));
    }
  };
  const act = async (a: Agent, what: "enable" | "token" | "remove", on?: boolean) => {
    try {
      const u = `${base}/hosted/${encodeURIComponent(a.name)}`;
      if (what === "enable") await api(`${u}/enabled`, { method: "PUT", body: { enabled: on } });
      if (what === "remove") {
        if (!confirm(`Remove remote:${a.name}? Sessions that name it will fail until it is registered again.`)) return;
        await api(u, { method: "DELETE" });
      }
      if (what === "token") {
        if (!confirm(`Make a new token for remote:${a.name}? The old one stops working at once.`)) return;
        const d: any = await api(`${u}/token`, { method: "POST" });
        setToken({ name: a.name, token: d.token });
      }
      load();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <>
      <Group title="Project">
        <Row label="Project">
          <Select label="Project" value={project} onChange={setProject} options={projects.map((p: any) => ({ value: p.name, label: `${p.name}${p.full_name ? ` — ${p.full_name}` : ""}` }))} />
        </Row>
      </Group>
      {err && <Note tone="warn">{err}</Note>}
      {mode && (
        <Group
          title="Self-hosted mode"
          id="setting-hosted-mode"
          footer="When a side is self-hosted, every registered hosted agent of that kind that is switched on is in the pool (unless the study lists its own assistants or opponents). A study may override this in its study.yaml (hosted:)."
        >
          <Row label="Assistants are self-hosted" hint="Each team runs its Assistant with its own language model">
            <Toggle label="Assistants are self-hosted" value={mode.assistants} onChange={(v) => saveMode({ ...mode, assistants: v })} />
          </Row>
          <Row label="Opponents are self-hosted">
            <Toggle label="Opponents are self-hosted" value={mode.opponents} onChange={(v) => saveMode({ ...mode, opponents: v })} />
          </Row>
          <Row label="Time limit per call" hint="Seconds HANI2 waits for a host before the opponent passes its turn or the Assistant reports an error">
            <Stepper label="Time limit per call" value={mode.timeout} min={1} max={600} onChange={(v) => v && saveMode({ ...mode, timeout: v })} />
          </Row>
          <Row label="Failures before an opponent walks away" hint="Failed calls in a row; the game still counts">
            <Stepper label="Failures before walking away" value={mode.max_failures} min={1} max={20} onChange={(v) => v && saveMode({ ...mode, max_failures: v })} />
          </Row>
        </Group>
      )}
      <Group title="Register a hosted agent" id="setting-hosted-add" footer="HANI2 makes a token for the team; they start their host with it (hani2 host-assistant … --token-env VAR). Use it as remote:<name> in pools and groups.">
        <Row label="Name" hint="Recorded in results and on boards (letters, digits, . _ -)">
          <TextField label="Name" value={n.name} onChange={(v) => setN({ ...n, name: v })} className="w-56" />
        </Row>
        <Row label="Kind">
          <Select label="Kind" value={n.kind} onChange={(v) => setN({ ...n, kind: v })} options={[{ value: "assistant", label: "Assistant" }, { value: "opponent", label: "Opponent" }]} />
        </Row>
        <Row label="Address" hint="Where HANI2 reaches the host, e.g. https://team.example.org:8700">
          <TextField label="Address" value={n.url} onChange={(v) => setN({ ...n, url: v })} className="w-80" mono />
        </Row>
        <Row label="Team" hint="Optional">
          <TextField label="Team" value={n.team} onChange={(v) => setN({ ...n, team: v })} className="w-56" />
        </Row>
        <Row label="">
          <button className="btn-primary" disabled={!n.name || !n.url} onClick={add}>
            <Plus size={15} /> Register
          </button>
        </Row>
      </Group>
      {token && (
        <Group title={`Token for remote:${token.name}`} footer="Shown once. Send it to the team privately; HANI2 never shows it again.">
          <Row label="Token" icon={<Tile icon={KeyRound} color="bg-warn" />}>
            <CopyField value={token.token} label="token" />
          </Row>
        </Group>
      )}
      <Group title={`Hosted agents${agents ? ` (${agents.length})` : ""}`} id="setting-hosted-list">
        {!agents ? (
          <Spinner />
        ) : agents.length === 0 ? (
          <InfoRow label="None yet" value="Register a team's address above" />
        ) : (
          agents.map((a) => {
            const c = checks[a.name];
            return (
              <Row
                key={a.name}
                icon={<Tile icon={a.kind === "opponent" ? Swords : Bot} color={a.enabled === false ? "bg-muted" : a.kind === "opponent" ? "bg-opponent" : "bg-you"} />}
                label={<code className="text-[0.85rem]">{a.spec}</code>}
                hint={
                  <>
                    {a.kind} · <span className="font-mono">{a.url}</span>
                    {a.team ? ` · ${a.team}` : ""}
                    {c && !c.busy && (
                      <span className={c.ok ? "text-good" : "text-bad"} data-check={c.ok ? "ok" : "fail"}>
                        {" · "}
                        {c.ok ? `answers: ${c.info?.name ?? ""} ${c.info?.version ?? ""} (${Math.round((c.latency ?? 0) * 1000)} ms)` : c.error}
                      </span>
                    )}
                  </>
                }
              >
                <span className="flex flex-wrap items-center justify-end gap-2">
                  <Toggle label={`Use remote:${a.name}`} value={a.enabled !== false} onChange={(v) => act(a, "enable", v)} />
                  <button className="btn-secondary text-xs" onClick={() => check(a)} disabled={c?.busy}>
                    <Activity size={13} /> Check
                  </button>
                  <button className="btn-secondary text-xs" onClick={() => act(a, "token")}>
                    <KeyRound size={13} /> New token
                  </button>
                  <button className="btn-secondary text-xs" onClick={() => act(a, "remove")} aria-label={`Remove remote:${a.name}`}>
                    <Trash2 size={13} />
                  </button>
                </span>
              </Row>
            );
          })
        )}
      </Group>
    </>
  );
}
