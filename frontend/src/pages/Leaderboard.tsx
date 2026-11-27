// The end-user leaderboard pages: /s/<project>/leaderboard (the project board) and
// /s/<project>/<study>/leaderboard (one study's board). They read the same API a website reads, as end
// users get it (view=user), so they show only the sort keys and switches the project allows and
// follow the board's visibility. /leaderboard lists the boards the viewer may see.
import { useEffect, useRef, useState } from "react";
import { LogIn, Trophy } from "lucide-react";
import { ApiError, api } from "../api";
import { Brand, ThemeButton } from "../negotiate/Header";
import { BASE, currentPath, navigate, withBase } from "../router";
import { type Board, fetchBoard, trackTitle } from "../leaderboard/board";
import { BoardView } from "../leaderboard/BoardView";

/** The server's root (the mount path, without a study's /s/<project>/<study>). */
export const ROOT = BASE.replace(/\/s\/[^/]+\/[^/]+$/, "");

/** Which board a path shows: ``/s/P/leaderboard`` (the app at the root) or ``/leaderboard`` inside a study. */
export function boardOfPath(path: string): { project: string; study: string | null } | null {
  const p = /^\/s\/([^/]+)\/leaderboard\/?$/.exec(path);
  if (p) return { project: decodeURIComponent(p[1]), study: null };
  const s = /\/s\/([^/]+)\/([^/]+)$/.exec(BASE);
  if (s && /^\/leaderboard\/?$/.test(path)) return { project: decodeURIComponent(s[1]), study: decodeURIComponent(s[2]) };
  return null;
}

function readQuery(): Record<string, string> {
  const out: Record<string, string> = {};
  new URLSearchParams(location.search).forEach((v, k) => {
    if (["sort", "games", "stratum", "window"].includes(k) && v) out[k] = v;
  });
  return out;
}

function writeQuery(q: Record<string, string>, defaults: Record<string, string>) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v && v !== defaults[k]) sp.set(k, v);
  const s = sp.toString();
  history.replaceState(null, "", location.pathname + (s ? `?${s}` : ""));
}

function Shell({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: React.ReactNode }) {
  return (
    <div className="min-h-[100dvh] bg-paper">
      <header className="border-b border-line bg-surface/70">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <Brand />
          <ThemeButton />
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pb-16 pt-6">
        <div className="mb-5 flex items-start gap-3">
          <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-warn/15 text-warn"><Trophy size={18} /></span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold leading-tight tracking-tight sm:text-2xl">{title}</h1>
            {subtitle && <div className="mt-0.5 text-sm text-muted">{subtitle}</div>}
          </div>
        </div>
        {children}
      </main>
    </div>
  );
}

function Message({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="panel flex flex-col items-center gap-3 px-6 py-12 text-center" role="status">
      <div className="max-w-md text-sm text-muted">{children}</div>
      {action}
    </div>
  );
}

export function LeaderboardPage({ project, study }: { project: string; study: string | null }) {
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState<string | null>(null);
  const seq = useRef(0);
  const load = (q: Record<string, string>, retry = true) => {
    const n = ++seq.current;
    setBusy(true);
    fetchBoard(project, study, q, true)
      .then((b) => {
        if (n !== seq.current) return;
        setBoard(b);
        setErr(null);
        writeQuery(b.query, b.options.defaults);
      })
      .catch((e: ApiError) => {
        if (n !== seq.current) return;
        // a link with a sort or switch the board no longer allows: show its defaults instead
        if (e.status === 400 && retry && Object.keys(q).length) return load({}, false);
        setErr(e);
      })
      .finally(() => n === seq.current && setBusy(false));
  };
  useEffect(() => {
    load(readQuery());
    api("/api/v1/leaderboards")
      .then((d: any) => setTitle(d.boards?.find((x: any) => x.project === project)?.title ?? null))
      .catch(() => {});
  }, [project, study]);
  const heading = `${title && title !== project ? title : project}${study ? ` · ${study}` : ""}`;
  document.title = `Leaderboard · ${heading}`;
  if (err) {
    const next = currentPath() + location.search;
    return (
      <Shell title={heading}>
        {err.status === 401 ? (
          <Message action={<button className="btn-primary" onClick={() => navigate(`/login?next=${encodeURIComponent(next)}`)}><LogIn size={15} /> Sign in</button>}>
            This leaderboard is for signed-in participants. Sign in to see it.
          </Message>
        ) : err.status === 403 ? (
          <Message>This leaderboard is not open to you. {err.message}</Message>
        ) : err.status === 404 ? (
          <Message>There is no leaderboard here.</Message>
        ) : (
          <Message>The leaderboard could not be loaded: {err.message}</Message>
        )}
      </Shell>
    );
  }
  if (!board) return <Shell title={heading}><div className="h-40 animate-pulse rounded-xl bg-sunken" /></Shell>;
  const when = new Date(board.generated_at);
  return (
    <Shell title={heading} subtitle={<>{trackTitle(board.track)}{board.source === "tournament" ? " · simulated table" : ""} · updated {Number.isNaN(when.getTime()) ? board.generated_at : when.toLocaleString()}</>}>
      <BoardView board={board} onQuery={(q) => load(q)} busy={busy} />
    </Shell>
  );
}

/** ``/leaderboard`` outside a study: the boards this viewer may see. */
export function LeaderboardIndex() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api("/api/v1/leaderboards").then(setD).catch(() => setD({ boards: [] }));
  }, []);
  return (
    <Shell title="Leaderboards">
      {!d ? (
        <div className="h-24 animate-pulse rounded-xl bg-sunken" />
      ) : d.boards.length === 0 ? (
        <Message>No leaderboard is open to you. Signed-in participants may see more.</Message>
      ) : (
        <ul className="panel divide-y divide-line/60">
          {d.boards.map((b: any) => (
            <li key={b.project} className="px-4 py-3">
              <a className="font-medium text-you hover:underline" href={withBase(`/s/${encodeURIComponent(b.project)}/leaderboard`)}>{b.title || b.project}</a>
              <div className="text-xs text-muted">{trackTitle(b.track)}{b.year ? ` · ${b.year}` : ""}</div>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
