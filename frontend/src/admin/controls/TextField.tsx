import { useEffect, useState } from "react";

/** A one-line text field (right-aligned in a row). */
export function TextField({ value, onChange, placeholder, label, type = "text", className = "w-64", mono, commit = "change" }: {
  value: string | null | undefined; onChange: (v: string) => void; placeholder?: string; label?: string; type?: string; className?: string; mono?: boolean; commit?: "change" | "blur";
}) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => setV(value ?? ""), [value]);
  return (
    <input
      aria-label={label}
      type={type}
      value={commit === "blur" ? v : (value ?? "")}
      placeholder={placeholder}
      onChange={(e) => (commit === "blur" ? setV(e.target.value) : onChange(e.target.value))}
      onBlur={() => commit === "blur" && v !== (value ?? "") && onChange(v)}
      onKeyDown={(e) => commit === "blur" && e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      className={`max-w-full rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink shadow-[0_1px_1px_rgb(0_0_0/0.04)] placeholder:text-muted/70 focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20 ${mono ? "font-mono text-xs" : ""} ${className}`}
    />
  );
}

/** A multi-line text area that spans the row. */
export function TextArea({ value, onChange, rows = 8, label, mono, placeholder }: { value: string | null | undefined; onChange: (v: string) => void; rows?: number; label?: string; mono?: boolean; placeholder?: string }) {
  return (
    <textarea
      aria-label={label}
      rows={rows}
      value={value ?? ""}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full rounded-lg border border-line bg-paper/60 px-2.5 py-2 text-sm text-ink focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20 ${mono ? "font-mono text-xs leading-relaxed" : ""}`}
    />
  );
}
