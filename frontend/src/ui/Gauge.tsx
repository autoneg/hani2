import { pct } from "./format";

/** The utility gauge: how much a deal is worth to you, against your value on disagreement. */
export function Gauge({
  value,
  reserved,
  party = "you",
  size = "md",
  showLabel = true,
}: {
  value: number | null | undefined;
  reserved?: number | null;
  party?: "you" | "partner" | "neutral";
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}) {
  const v = value === null || value === undefined ? null : Math.max(0, Math.min(1, value));
  const below = v !== null && reserved !== null && reserved !== undefined && v < reserved;
  const fill = below ? "bg-bad" : party === "partner" ? "bg-partner" : party === "neutral" ? "bg-muted" : "bg-you";
  const h = size === "sm" ? "h-1.5" : size === "lg" ? "h-2.5" : "h-2";
  return (
    <div className="flex min-w-0 items-center gap-2" title={reserved != null ? `Value on disagreement: ${pct(reserved)}` : undefined}>
      <div className={`relative ${h} flex-1 rounded-full bg-sunken`}>
        {v !== null && <div className={`absolute inset-y-0 left-0 rounded-full ${fill} transition-[width] duration-500`} style={{ width: `${v * 100}%` }} />}
        {reserved !== null && reserved !== undefined && (
          <div className="absolute -inset-y-1 w-0.5 rounded bg-ink/70" style={{ left: `calc(${Math.max(0, Math.min(1, reserved)) * 100}% - 1px)` }} />
        )}
      </div>
      {showLabel && (
        <span className={`tnum w-11 shrink-0 text-right text-sm font-semibold ${below ? "text-bad" : "text-ink"}`}>{pct(v)}</span>
      )}
    </div>
  );
}
