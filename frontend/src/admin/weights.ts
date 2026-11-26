// The weights of a score in the score builder (no imports, so `node --test` can load this file).
// The editor shows percentages; a score is saved with fractions that sum to 1 (the API accepts a
// sum within 1e-6 of 1), so Save is enabled only when the percentages sum to 100 within 1e-4.

/** The tolerance on a sum of percentages (1e-6 on fractions). */
export const PERCENT_TOLERANCE = 1e-4;

const clean = (w: unknown) => {
  const x = Number(w);
  return Number.isFinite(x) && x > 0 ? x : 0;
};

/** The running sum of the percentages (negative or empty weights count as 0). */
export function sumPercent(ws: unknown[]): number {
  return ws.reduce<number>((a, w) => a + clean(w), 0);
}

/** Whether the percentages sum to 100 % (and every weight is ≥ 0). */
export function atHundred(ws: unknown[]): boolean {
  return ws.length > 0 && ws.every((w) => Number(w) >= 0) && Math.abs(sumPercent(ws) - 100) <= PERCENT_TOLERANCE;
}

/** The running sum as the editor shows it ("100 %", "87.5 %"). */
export function sumText(ws: unknown[]): string {
  const s = Math.round(sumPercent(ws) * 100) / 100;
  return `${s} %`;
}

/** Rescale the weights to sum to exactly 100 % while keeping their proportions, rounded to
 *  ``decimals`` places (the largest remainders get the last units, so the shown sum is exactly 100).
 *  All-zero (or empty) weights become equal shares. */
export function normalise(ws: unknown[], decimals = 2): number[] {
  const n = ws.length;
  if (!n) return [];
  const unit = 10 ** decimals;
  const total = 100 * unit;
  const raw = ws.map(clean);
  const s = raw.reduce((a, b) => a + b, 0);
  const exact = s > 0 ? raw.map((w) => (w / s) * total) : raw.map(() => total / n);
  const floors = exact.map(Math.floor);
  let left = total - floors.reduce((a, b) => a + b, 0);
  const order = exact.map((x, i) => [x - floors[i], i] as const).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let j = 0; left > 0; j = (j + 1) % n, left--) floors[order[j][1]] += 1;
  return floors.map((f) => f / unit);
}

/** Percentages to the fractions a score is saved with (they sum to 1). */
export function toFractions(ws: unknown[]): number[] {
  const raw = ws.map(clean);
  const s = raw.reduce((a, b) => a + b, 0);
  if (s <= 0) return raw.map(() => 0);
  return raw.map((w) => w / s);
}

/** Fractions (as stored) to percentages for the editor, rounded to ``decimals`` places. */
export function toPercent(fs: unknown[], decimals = 2): number[] {
  const unit = 10 ** decimals;
  return fs.map((f) => Math.round(clean(f) * 100 * unit) / unit);
}
