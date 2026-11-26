import { useStore } from "../store";
import { pct } from "./format";

/** The colours of the issues in the colour-coded bars, most important issue first (index.css). */
const N_ISSUE_COLORS = 8;
const issueColor = (k: number) => (k < N_ISSUE_COLORS ? `var(--issue-${k + 1})` : "rgb(var(--muted))");

type Segment = { name: string; value: number; color: string };

/** The bar's segments: one per issue (most important first; the 9th issue on folds into
 * "Other"), or null when the bar is not colour-coded (the setting is off, the preferences
 * are not additive, or the participant does not know them). */
function useSegments(parts: number[] | null | undefined): Segment[] | null {
  const on = useStore((s) => !!s.state?.prefs?.color_utility_by_issue);
  const issues = useStore((s) => s.state?.utility_issues);
  if (!on || !parts || !issues || parts.length !== issues.length) return null;
  const segs: Segment[] = parts.slice(0, N_ISSUE_COLORS).map((v, k) => ({ name: issues[k], value: v, color: issueColor(k) }));
  if (parts.length > N_ISSUE_COLORS) {
    segs.push({ name: "Other", value: parts.slice(N_ISSUE_COLORS).reduce((a, b) => a + b, 0), color: issueColor(N_ISSUE_COLORS) });
  }
  return segs;
}

/** The utility gauge: how much a deal is worth to you, against your value on disagreement.
 * With ``parts`` (what each issue adds, most important first) and the participant's
 * "Colour the utility bars by issue" setting on, the bar is split into one coloured
 * segment per issue; ``legend`` then names each issue and its share below the bar. */
export function Gauge({
  value,
  reserved,
  party = "you",
  size = "md",
  showLabel = true,
  parts,
  legend = false,
}: {
  value: number | null | undefined;
  reserved?: number | null;
  party?: "you" | "opponent" | "neutral";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  parts?: number[] | null;
  legend?: boolean;
}) {
  const v = value === null || value === undefined ? null : Math.max(0, Math.min(1, value));
  const below = v !== null && reserved !== null && reserved !== undefined && v < reserved;
  const fill = below ? "bg-bad" : party === "opponent" ? "bg-opponent" : party === "neutral" ? "bg-muted" : "bg-you";
  const h = size === "sm" ? "h-1.5" : size === "lg" ? "h-2.5" : "h-2";
  const segs = useSegments(v === null ? null : parts);
  const shown = segs?.filter((s) => s.value > 0) ?? null;
  const title = [
    reserved != null ? `Value on disagreement: ${pct(reserved)}` : null,
    ...(segs ?? []).map((s) => `${s.name}: ${pct(s.value, 1)}`),
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-center gap-2" title={title || undefined}>
        <div className={`relative ${h} flex-1 rounded-full bg-sunken`}>
          {v !== null && shown && shown.length > 0 ? (
            <div
              className="absolute inset-y-0 left-0 flex gap-[2px] overflow-hidden rounded-full transition-[width] duration-500"
              style={{ width: `${v * 100}%` }}
              role="img"
              aria-label={segs!.map((s) => `${s.name} ${pct(s.value, 1)}`).join(", ")}
            >
              {shown.map((s) => (
                <div key={s.name} className="h-full min-w-[2px]" style={{ flexGrow: s.value, flexBasis: 0, background: s.color }} title={`${s.name}: ${pct(s.value, 1)}`} />
              ))}
            </div>
          ) : (
            v !== null && <div className={`absolute inset-y-0 left-0 rounded-full ${fill} transition-[width] duration-500`} style={{ width: `${v * 100}%` }} />
          )}
          {reserved !== null && reserved !== undefined && (
            <div className="absolute -inset-y-1 w-0.5 rounded bg-ink/70" style={{ left: `calc(${Math.max(0, Math.min(1, reserved)) * 100}% - 1px)` }} />
          )}
        </div>
        {showLabel && (
          <span className={`tnum w-11 shrink-0 text-right text-sm font-semibold ${below ? "text-bad" : "text-ink"}`}>{pct(v)}</span>
        )}
      </div>
      {legend && segs && segs.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted">
          {segs.map((s) => (
            <span key={s.name} className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.color }} />
              {s.name} <b className="tnum font-semibold text-ink">{pct(s.value, 1)}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
