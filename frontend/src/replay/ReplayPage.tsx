import { useEffect, useState } from "react";
import { ArrowLeft, Clapperboard } from "lucide-react";
import { api } from "../api";
import { Brand, ThemeButton } from "../negotiate/Header";
import { navigate, queryParams, withBase } from "../router";
import { Library } from "./Library";
import { MetricReferenceSheet, ReferenceButton } from "./MetricReference";
import { Player } from "./Player";

/** Admin tool: browse, replay, evaluate and compare recorded negotiations. */
export function ReplayPage() {
  // the recording key is in the query string, which `usePath` does not track
  const [, bump] = useState(0);
  useEffect(() => {
    const on = () => bump((x) => x + 1);
    window.addEventListener("popstate", on);
    window.addEventListener("hani-nav", on);
    return () => {
      window.removeEventListener("popstate", on);
      window.removeEventListener("hani-nav", on);
    };
  }, []);
  const key = queryParams().key;
  const [allowed, setAllowed] = useState<boolean | null>(null);
  useEffect(() => {
    api<{ user: string | null; is_admin?: boolean }>("/api/auth/me")
      .then((m) => {
        if (!m.user) navigate(`/login?next=${encodeURIComponent("/replay" + location.search)}`, true);
        else setAllowed(!!m.is_admin);
      })
      .catch(() => setAllowed(false));
  }, []);
  if (allowed === false) return <div className="flex h-screen items-center justify-center text-sm text-muted">This page is for administrators.</div>;
  if (allowed === null) return null;
  return (
    <div className="flex h-[100dvh] flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-line bg-surface px-4 py-2">
        <Brand />
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <Clapperboard size={16} className="text-you" /> Replay
        </div>
        <div className="flex-1" />
        {key && (
          <a className="btn-secondary px-2.5 py-1 text-xs" href={withBase("/replay")} onClick={(e) => { e.preventDefault(); navigate("/replay"); }}>
            <ArrowLeft size={14} /> All recordings
          </a>
        )}
        <ReferenceButton />
        <a className="btn-ghost px-2.5 py-1 text-xs" href={withBase("/admin")} onClick={(e) => { e.preventDefault(); navigate("/admin"); }}>
          Admin
        </a>
        <ThemeButton />
      </header>
      {key ? (
        <Player key={key} rkey={key} />
      ) : (
        <main className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-8">
          <div className="mx-auto max-w-7xl">
            <Library />
          </div>
        </main>
      )}
      <MetricReferenceSheet />
    </div>
  );
}
