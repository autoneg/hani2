/** A set of checkboxes (a multi-select over a short, fixed list). */
export function Checks({ value, onChange, options, columns = 2 }: { value: string[] | null | undefined; onChange: (v: string[]) => void; options: { value: string; label: string; hint?: string }[]; columns?: 1 | 2 }) {
  const v = value ?? [];
  return (
    <div className={`grid gap-x-6 gap-y-2 ${columns === 2 ? "sm:grid-cols-2" : ""}`}>
      {options.map((o) => (
        <label key={o.value} className="flex cursor-pointer items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--you))]" checked={v.includes(o.value)} onChange={(e) => onChange(e.target.checked ? [...v, o.value] : v.filter((x) => x !== o.value))} />
          <span className="min-w-0">
            {o.label}
            {o.hint && <span className="block text-xs text-muted">{o.hint}</span>}
          </span>
        </label>
      ))}
    </div>
  );
}
