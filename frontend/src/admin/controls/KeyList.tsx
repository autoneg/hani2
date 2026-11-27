import { X } from "lucide-react";
import { markText, VALIDATED_TIP, ValidatedMark } from "../../ui/metricGroups";

/** Keys in named groups (the catalogue's groups of similar measures, the enabled scores, …). */
export type KeyGroup = { label: string; keys: { key: string; title: string; validated?: boolean }[] };

/** An ordered list of score or criterion keys: chips with a remove button, and an "Add…" menu whose
 *  choices are grouped, validated ones marked ✓. A key that is in no group (typed into a file) still
 *  shows as a chip. */
export function KeyList({ label, value, groups, onChange, titles, tip = VALIDATED_TIP }: { label: string; value: string[]; groups: KeyGroup[]; onChange: (v: string[]) => void; titles: Record<string, string>; tip?: string }) {
  const validated = new Set(groups.flatMap((g) => g.keys.filter((x) => x.validated).map((x) => x.key)));
  return (
    <span className="flex flex-wrap items-center justify-end gap-1.5" data-key-list={label}>
      {value.map((k) => (
        <span key={k} className="chip py-0.5 text-[0.78rem]" title={k}>
          {titles[k] ?? k}
          {validated.has(k) && <ValidatedMark tip={tip} className="ml-0" />}
          <button type="button" aria-label={`Remove ${k} from ${label}`} className="text-muted hover:text-bad" onClick={() => onChange(value.filter((x) => x !== k))}>
            <X size={12} />
          </button>
        </span>
      ))}
      <select aria-label={`Add to ${label}`} value="" onChange={(e) => e.target.value && onChange([...value, e.target.value])} className="max-w-[12rem] rounded-md border border-line bg-surface py-1 pl-2 pr-6 text-xs text-ink focus:border-you focus:outline-none">
        <option value="">Add…</option>
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.keys.filter((x) => !value.includes(x.key)).map((x) => (
              <option key={x.key} value={x.key} title={x.validated ? tip : undefined} data-validated={x.validated ? "" : undefined}>
                {x.title}
                {x.title !== x.key ? ` (${x.key})` : ""}
                {markText(x.validated)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </span>
  );
}
