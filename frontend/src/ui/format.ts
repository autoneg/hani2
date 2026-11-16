export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtValue = (v: any): string => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  return String(v);
};

export const fmtCell = (v: any, format?: string): string => {
  if (v === null || v === undefined || v === "") return "";
  if (format === "percent" && typeof v === "number") return `${(v * 100).toFixed(1)}%`;
  if (format === "float" && typeof v === "number") return v.toFixed(2);
  if (format === "int" && typeof v === "number") return String(Math.round(v));
  if (typeof v === "number" && !Number.isInteger(v)) return String(Math.round(v * 1000) / 1000);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

export const clock = (s: number) => {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
};
