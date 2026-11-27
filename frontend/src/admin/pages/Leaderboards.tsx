// Admin → Leaderboards: any project or study board as an admin reads it (every enabled score and every
// criterion with a direction to sort by, every switch value: the strata included), with the weights in
// effect, what was left out and the warnings, and links to the board and score editors. It reads the
// same API a website reads.
import { useEffect, useRef, useState } from "react";
import { ExternalLink, Pencil, SlidersHorizontal } from "lucide-react";
import { ApiError, api } from "../../api";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { Select } from "../controls/Select";
import { Note, Spinner } from "../schema";
import { useNav } from "../Nav";
import { type Board, boardPage, fetchBoard, fmt, trackTitle } from "../../leaderboard/board";
import { BoardView } from "../../leaderboard/BoardView";
import { ROOT } from "../../pages/Leaderboard";
import { scrollToWhenReady, useCriteria } from "../boards";
import { ProjectView, StudyView } from "./Projects";

export const LEADERBOARD_ENTRIES = [
  { id: "boards-pick", label: "Choose a board", hint: "Any project board or study board", keywords: "leaderboard ranking project study" },
  { id: "boards-weights", label: "Weights in effect", hint: "Each score's weights after coverage, and the parts left out", keywords: "scores weights dropped provisional" },
  { id: "boards-excluded", label: "Games left out", hint: "Practice, admin sessions, abandoned matches, caps, …", keywords: "excluded cap abandoned practice" },
];

export function Leaderboards() {
  const [projects, setProjects] = useState<any[] | null>(null);
  const [project, setProject] = useState<string>("");
  const [study, setStudy] = useState<string>("");
  const [query, setQuery] = useState<Record<string, string>>({});
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNav();
  const seq = useRef(0);
  const crit = useCriteria(project || null, study || null);
  useEffect(() => {
    api("/api/admin/projects")
      .then((d: any) => {
        const ps = (d.projects ?? []).filter((p: any) => p.name !== "default" || p.studies?.length);
        setProjects(ps);
        const first = ps.find((p: any) => p.defaults?.leaderboard) ?? ps.find((p: any) => p.kind !== "none") ?? ps[0];
        if (first) setProject(first.name);
      })
      .catch((e) => setErr(e.message));
  }, []);
  useEffect(() => {
    if (!project) return;
    const n = ++seq.current;
    setBusy(true);
    fetchBoard(project, study || null, query, false)
      .then((b) => n === seq.current && (setBoard(b), setErr(null)))
      .catch((e: ApiError) => {
        if (n !== seq.current) return;
        if (e.status === 400 && Object.keys(query).length) return setQuery({});
        setBoard(null);
        setErr(e.message);
      })
      .finally(() => n === seq.current && setBusy(false));
  }, [project, study, query]);
  if (!projects) return err ? <Note tone="warn">{err}</Note> : <Spinner />;
  const p = projects.find((x) => x.name === project);
  const studies: string[] = p?.studies ?? [];
  const pick = (pr: string, st: string) => {
    setProject(pr);
    setStudy(st);
    setQuery({});
    setBoard(null);
  };
  const openEditor = (target: string) => {
    if (study) nav.push({ title: study, render: () => <StudyView project={project} study={study} /> });
    else nav.push({ title: project, render: () => <ProjectView name={project} /> });
    scrollToWhenReady(target);
  };
  return (
    <>
      <Group title="Board" id="setting-boards-pick" footer="The board as an admin sees it: every enabled score and criterion to sort by, and every switch value. End users see only what the board's settings allow.">
        <Row label="Project">
          <Select label="Project" value={project} onChange={(v) => pick(v, "")} options={projects.map((x) => ({ value: x.name, label: `${x.name}${x.full_name ? ` — ${x.full_name}` : ""}${x.defaults?.leaderboard ? "" : " (no board settings)"}` }))} />
        </Row>
        <Row label="Board" hint={study ? "One study's games; its settings override the project's key by key" : "The project board: the studies it names, and rows taken in from other projects"}>
          <Select label="Board" value={study} onChange={(v) => pick(project, v)} options={[{ value: "", label: "Project board" }, ...studies.map((s) => ({ value: s, label: `Study ${s}` }))]} />
        </Row>
        <Row label="Open or edit">
          <span className="flex flex-wrap justify-end gap-2">
            <a className="btn-secondary text-xs" href={boardPage(ROOT, project, study || null)} target="_blank" rel="noreferrer"><ExternalLink size={13} /> As end users see it</a>
            <button className="btn-secondary text-xs" onClick={() => openEditor("setting-board-settings")}><SlidersHorizontal size={13} /> Board settings</button>
            <button className="btn-secondary text-xs" onClick={() => openEditor("setting-scores")}><Pencil size={13} /> Scores</button>
          </span>
        </Row>
        {board && (
          <InfoRow label="Track, source, visibility" value={`${trackTitle(board.track)} · ${board.source === "tournament" ? "simulated table" : "games"} · ${board.visibility ?? ""}`} />
        )}
      </Group>
      {err && <Note tone="warn">{err}</Note>}
      {board ? (
        <>
          <div className="mb-6">
            <BoardView board={board} onQuery={setQuery} sortGroups={crit?.sortGroups} titles={crit?.titles} admin busy={busy} />
          </div>
          <Weights board={board} titles={crit?.titles ?? {}} />
          <Group title="Games left out" id="setting-boards-excluded" footer="Counted over every row the board read, whatever the switches show.">
            {Object.entries(board.excluded ?? {}).length ? (
              Object.entries(board.excluded).map(([k, n]) => <InfoRow key={k} label={k} value={n} />)
            ) : (
              <InfoRow label="Nothing" value="every game counted" />
            )}
            {board.totals?.sessions !== undefined && <InfoRow label="Games in this view" value={`${board.totals.sessions}${board.totals.matches ? ` (${board.totals.matches} matches between people)` : ""}`} />}
            {typeof board.totals?.agreement_rate === "number" && <InfoRow label="Deals" value={`${Math.round(100 * board.totals.agreement_rate)} %`} />}
            {typeof board.totals?.welfare === "number" && <InfoRow label="Welfare" value={fmt(board.totals.welfare)} />}
          </Group>
          <Group title="Rules in effect" footer="From the board settings (Projects & Studies).">
            {Object.entries(board.rules ?? {}).map(([k, v]) => <InfoRow key={k} label={<code className="text-[0.8rem]">{k}</code>} value={v === null ? "no cap" : String(v)} />)}
          </Group>
          {board.warnings.length > 0 && (
            <Group title="Warnings">
              <ul className="list-disc space-y-1 px-8 py-3 text-sm text-warn" data-warnings>
                {board.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </Group>
          )}
        </>
      ) : (
        !err && <Spinner />
      )}
    </>
  );
}

function Weights({ board, titles }: { board: Board; titles: Record<string, string> }) {
  const entries = Object.entries(board.scores ?? {});
  if (!entries.length) return null;
  return (
    <Group title="Weights in effect" id="setting-boards-weights" footer="After coverage: a part measured for too few games of some entrant is left out for everyone, and the rest are rescaled to 100 %.">
      {entries.map(([k, s]) => (
        <div key={k} className="px-4 py-3" data-score-weights={k}>
          <div className="mb-1.5 flex items-center gap-2 text-sm font-medium">
            {s.title ?? k} <code className="text-[0.75rem] text-muted">{k}</code>
            {s.provisional && <span className="rounded bg-warn/15 px-1 text-[0.65rem] font-medium uppercase text-warn">provisional</span>}
          </div>
          <div className="space-y-1">
            {Object.entries(s.weights_in_effect)
              .filter(([, w]) => w > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([c, w]) => (
                <div key={c} className="flex items-center gap-2 text-xs">
                  <span className="w-48 truncate sm:w-64" title={c}>{titles[c] ?? c}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/70"><div className="h-full rounded-full bg-you" style={{ width: `${100 * w}%` }} /></div>
                  <span className="tnum w-12 text-right">{(100 * w).toFixed(1)} %</span>
                </div>
              ))}
          </div>
          {s.dropped.length > 0 && <div className="mt-1.5 text-xs text-muted">Left out: {s.dropped.map((c) => titles[c] ?? c).join(", ")}</div>}
        </div>
      ))}
    </Group>
  );
}
