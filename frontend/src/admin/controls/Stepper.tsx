import { Minus, Plus } from "lucide-react";

/** A number field with − / + buttons. ``null`` (empty) is allowed when ``nullable``. */
export function Stepper({ value, onChange, min, max, step = 1, label, nullable, placeholder, width = "w-20" }: {
  value: number | null | undefined; onChange: (v: number | null) => void; min?: number; max?: number; step?: number; label?: string; nullable?: boolean; placeholder?: string; width?: string;
}) {
  const clamp = (v: number) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v));
  const round = (v: number) => Math.round(v * 1e6) / 1e6;
  const bump = (d: number) => onChange(clamp(round((value ?? min ?? 0) + d)));
  return (
    <span className="inline-flex items-stretch overflow-hidden rounded-md border border-line bg-surface shadow-[0_1px_1px_rgb(0_0_0/0.04)] focus-within:border-you focus-within:ring-2 focus-within:ring-you/20">
      <button type="button" className="px-1.5 text-muted hover:bg-sunken hover:text-ink disabled:opacity-40" aria-label={`Decrease ${label ?? ""}`} onClick={() => bump(-step)} disabled={value != null && min != null && value <= min}>
        <Minus size={13} />
      </button>
      <input
        aria-label={label}
        inputMode="decimal"
        className={`tnum ${width} border-x border-line bg-transparent px-1.5 py-1 text-center text-sm text-ink focus:outline-none`}
        value={value ?? ""}
        placeholder={placeholder ?? (nullable ? "none" : "")}
        onChange={(e) => {
          const t = e.target.value.trim();
          if (t === "") return onChange(nullable ? null : (min ?? 0));
          const n = Number(t);
          if (!Number.isNaN(n)) onChange(n);
        }}
        onBlur={() => value != null && onChange(clamp(value))}
      />
      <button type="button" className="px-1.5 text-muted hover:bg-sunken hover:text-ink disabled:opacity-40" aria-label={`Increase ${label ?? ""}`} onClick={() => bump(step)} disabled={value != null && max != null && value >= max}>
        <Plus size={13} />
      </button>
    </span>
  );
}
