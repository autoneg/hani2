import { useState } from "react";
import { X } from "lucide-react";

/** A list of short strings as removable chips plus an input (Enter or comma adds). */
export function Tags({ value, onChange, placeholder = "Add…", label, suggestions }: { value: string[] | null | undefined; onChange: (v: string[]) => void; placeholder?: string; label?: string; suggestions?: string[] }) {
  const items = value ?? [];
  const [t, setT] = useState("");
  const listId = suggestions ? `tags-${label?.replace(/\W+/g, "-")}` : undefined;
  const add = (raw: string) => {
    const parts = raw.split(",").map((x) => x.trim()).filter((x) => x && !items.includes(x));
    if (parts.length) onChange([...items, ...parts]);
    setT("");
  };
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-end gap-1">
      {items.map((x) => (
        <span key={x} className="chip max-w-full">
          <span className="truncate">{x}</span>
          <button type="button" className="text-muted hover:text-bad" aria-label={`Remove ${x}`} onClick={() => onChange(items.filter((y) => y !== x))}>
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        aria-label={label}
        list={listId}
        className="w-40 rounded-md border border-line bg-surface px-2 py-1 text-sm placeholder:text-muted/70 focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20"
        value={t}
        placeholder={placeholder}
        onChange={(e) => (e.target.value.endsWith(",") ? add(e.target.value) : setT(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add(t);
          } else if (e.key === "Backspace" && !t && items.length) onChange(items.slice(0, -1));
        }}
        onBlur={() => t && add(t)}
      />
      {suggestions && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
    </div>
  );
}
