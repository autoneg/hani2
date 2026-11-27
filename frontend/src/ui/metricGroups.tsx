// The groups of similar measures (src/hani2/evaluation/catalog.py, sent by the API) and the ✓ mark
// of validated measures and questionnaires: shared by the score builder, the board settings and the
// leaderboard's selectors.

/** A group as the API sends it (``groups`` of ``GET /api/admin/criteria`` or a board's ``options``). */
export type MetricGroup = { id: string; title: string; description?: string };

export const VALIDATED_TIP = "validated against a hand-computed example";
export const VALIDATED_SOURCE_TIP = "validated against the source instrument";

/** Items in the order of ``groups`` (items of unknown groups last, under "Other"); empty groups are left out. */
export function grouped<T>(items: T[], groupOf: (x: T) => string | undefined, groups: MetricGroup[] | undefined): { id: string; title: string; items: T[] }[] {
  const by: Record<string, T[]> = {};
  for (const x of items) (by[groupOf(x) || "other"] ??= []).push(x);
  const out = (groups ?? []).filter((g) => by[g.id]?.length).map((g) => ({ id: g.id, title: g.title, items: by[g.id] }));
  const known = new Set((groups ?? []).map((g) => g.id));
  const rest = Object.keys(by).filter((k) => !known.has(k)).flatMap((k) => by[k]);
  if (rest.length) out.push({ id: "other", title: "Other", items: rest });
  return out;
}

/** The text a native ``<option>`` gets for a validated entry (options cannot hold elements). */
export const markText = (validated?: boolean) => (validated ? " ✓" : "");

/** A small ✓ with a tooltip, next to a validated measure or questionnaire. */
export function ValidatedMark({ tip = VALIDATED_TIP, className = "" }: { tip?: string; className?: string }) {
  return (
    <span title={tip} aria-label={tip} data-validated className={`ml-1 inline-block align-baseline text-xs font-semibold text-good ${className}`}>
      ✓
    </span>
  );
}
