// What the board editor and Admin → Leaderboards share: the criteria catalogue as sort keys and titles,
// the enabled scores, and scrolling to a group after opening a project or study.
import { useEffect, useState } from "react";
import { api } from "../api";
import type { SortOption } from "../leaderboard/board";
import { grouped, type MetricGroup } from "../ui/metricGroups";

export interface Criteria {
  /** criteria with a direction (higher or lower), in the catalogue's groups: what a board can be sorted by */
  sortGroups: { label: string; options: SortOption[] }[];
  /** every criterion, for columns (a criterion without a direction can be shown but not sorted by) */
  all: { key: string; title: string; direction: string; source: string; group: string; validated: boolean }[];
  /** the groups of similar measures (``groups`` of the API), in order */
  groups: MetricGroup[];
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
        const groups: MetricGroup[] = d.groups ?? [];
        const sortable = crit.filter((x: any) => x.direction === "higher" || x.direction === "lower");
        const sortGroups = grouped(sortable, (x: any) => x.group, groups).map((g) => ({
          label: g.title,
          options: g.items.map((x: any) => ({ key: x.id, title: x.title || x.id, kind: "criterion" as const, direction: x.direction, description: x.description, group: x.group, validated: !!x.validated })),
        }));
        setC({ sortGroups, titles, groups, all: crit.map((x: any) => ({ key: x.id, title: x.title || x.id, direction: x.direction, source: x.source, group: x.group, validated: !!x.validated })) });
      })
      .catch(() => setC({ sortGroups: [], titles: {}, all: [], groups: [] }));
  }, [project, study]);
  return c;
}

/** ``GET /api/admin/scores``: every defined score (key, title, track, whether it is validated) and the enabled ones. */
export function useScores(project: string | null, study?: string | null, version?: unknown) {
  const [d, setD] = useState<{ scores: { key: string; title: string; track: string; validated: boolean }[]; enabled: string[] } | null | undefined>(undefined);
  useEffect(() => {
    if (!project) return;
    api(`/api/admin/scores?${qs(project, study)}`)
      .then((r: any) => setD({ scores: (r.scores ?? []).map((s: any) => ({ key: s.key, title: s.title || s.key, track: s.track, validated: !!s.validated })), enabled: r.enabled ?? [] }))
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
