// What the board editor and Admin → Leaderboards share: the criteria catalogue as sort keys and titles,
// the enabled scores, and scrolling to a group after opening a project or study.
import { useEffect, useState } from "react";
import { api } from "../api";
import type { SortOption } from "../leaderboard/board";

export const SOURCE_TITLE: Record<string, string> = {
  hard: "Criteria measured when the game ends",
  soft: "Criteria rated by the language-model judge",
  subjective: "Questionnaire scales (bundled)",
  questionnaire: "Questionnaire items and scales of the forms",
};

export interface Criteria {
  /** criteria with a direction (higher or lower), by source: what a board can be sorted by */
  sortGroups: { label: string; options: SortOption[] }[];
  /** every criterion, for columns (a criterion without a direction can be shown but not sorted by) */
  all: { key: string; title: string; direction: string; source: string }[];
  titles: Record<string, string>;
}

const qs = (project: string, study?: string | null) => (study ? `study=${encodeURIComponent(`${project}/${study}`)}` : `project=${encodeURIComponent(project)}`);

/** ``GET /api/admin/criteria`` of a project or study, as sort groups and titles (``undefined`` while loading). */
export function useCriteria(project: string | null, study?: string | null): Criteria | undefined {
  const [c, setC] = useState<Criteria | undefined>(undefined);
  useEffect(() => {
    if (!project) return;
    setC(undefined);
    api(`/api/admin/criteria?${qs(project, study)}`)
      .then((d: any) => {
        const crit = (d.criteria ?? []).filter((x: any) => x.source !== "score");
        const titles: Record<string, string> = {};
        for (const x of d.criteria ?? []) titles[x.id] = x.title || x.id;
        const sortGroups = Object.keys(SOURCE_TITLE)
          .map((s) => ({
            label: SOURCE_TITLE[s],
            options: crit.filter((x: any) => x.source === s && (x.direction === "higher" || x.direction === "lower")).map((x: any) => ({ key: x.id, title: x.title || x.id, kind: "criterion" as const, direction: x.direction, description: x.description })),
          }))
          .filter((g) => g.options.length);
        setC({ sortGroups, titles, all: crit.map((x: any) => ({ key: x.id, title: x.title || x.id, direction: x.direction, source: x.source })) });
      })
      .catch(() => setC({ sortGroups: [], titles: {}, all: [] }));
  }, [project, study]);
  return c;
}

/** ``GET /api/admin/scores``: every defined score (key, title, track) and the enabled ones. */
export function useScores(project: string | null, study?: string | null, version?: unknown) {
  const [d, setD] = useState<{ scores: { key: string; title: string; track: string }[]; enabled: string[] } | null | undefined>(undefined);
  useEffect(() => {
    if (!project) return;
    api(`/api/admin/scores?${qs(project, study)}`)
      .then((r: any) => setD({ scores: (r.scores ?? []).map((s: any) => ({ key: s.key, title: s.title || s.key, track: s.track })), enabled: r.enabled ?? [] }))
      .catch(() => setD(null));
  }, [project, study, version]);
  return d;
}

/** Scroll to ``#<id>`` once it is rendered (after a sub-page was pushed). */
export function scrollToWhenReady(id: string, tries = 40) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  else if (tries > 0) setTimeout(() => scrollToWhenReady(id, tries - 1), 100);
}
