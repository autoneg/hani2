import { ChevronsUpDown } from "lucide-react";

export type Option = string | { value: string; label: string };
export const optValue = (o: Option) => (typeof o === "string" ? o : o.value);
export const optLabel = (o: Option) => (typeof o === "string" ? o : o.label);

/** A compact pop-up button (native select, so it is keyboard and screen-reader friendly). */
export function Select({ value, onChange, options, label, className = "" }: { value: string | null | undefined; onChange: (v: string) => void; options: Option[]; label?: string; className?: string }) {
  const known = options.some((o) => optValue(o) === (value ?? ""));
  return (
    <span className={`relative inline-flex max-w-full items-center ${className}`}>
      <select
        aria-label={label}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-full appearance-none truncate rounded-md border border-line bg-surface py-1 pl-2.5 pr-7 text-sm text-ink shadow-[0_1px_1px_rgb(0_0_0/0.04)] focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20"
      >
        {!known && <option value={value ?? ""}>{value || "—"}</option>}
        {options.map((o) => (
          <option key={optValue(o)} value={optValue(o)}>
            {optLabel(o)}
          </option>
        ))}
      </select>
      <ChevronsUpDown size={13} className="pointer-events-none absolute right-2 text-muted" />
    </span>
  );
}
