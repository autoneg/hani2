export function toCsv(headers: string[], rows: any[][]): string {
  const cell = (v: any) => {
    if (v === null || v === undefined) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers, ...rows].map((r) => r.map(cell).join(",")).join("\n");
}

export function downloadText(name: string, text: string, mime = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function fmtNum(v: any): string {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") {
    if (!isFinite(v)) return "–";
    return Number.isInteger(v) ? String(v) : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(3);
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
}

export function fmtDuration(s: number | null | undefined): string {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : m > 0 ? `${m} min ${Math.round(s - m * 60)} s` : `${s.toFixed(1)} s`;
}
