/** A segmented control (one of a few choices). */
export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: [T, string][]; label?: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full flex-wrap rounded-lg bg-sunken p-0.5">
      {options.map(([k, l]) => (
        <button
          key={k}
          role="tab"
          aria-selected={value === k}
          onClick={() => onChange(k)}
          className={`rounded-md px-3 py-1 text-sm ${value === k ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgb(0_0_0/0.12)]" : "text-muted hover:text-ink"}`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
