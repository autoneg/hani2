import { ChevronRight } from "lucide-react";
import { useNav } from "./Nav";

/** A row that opens a sub-page (with a back button) — or runs ``onClick``. */
export function Disclosure({ id, label, hint, value, icon, title, render, onClick }: {
  id?: string; label: React.ReactNode; hint?: React.ReactNode; value?: React.ReactNode; icon?: React.ReactNode; title?: string; render?: () => React.ReactNode; onClick?: () => void;
}) {
  const nav = useNav();
  const open = () => (onClick ? onClick() : render && nav.push({ title: title ?? String(label), render }));
  return (
    <button type="button" id={id ? `setting-${id}` : undefined} data-setting={id} onClick={open} className="flex w-full scroll-mt-24 items-center gap-3 px-4 py-2.5 text-left hover:bg-sunken/60 focus-visible:bg-sunken/60 focus-visible:outline-none">
      {icon && <span className="shrink-0">{icon}</span>}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink">{label}</span>
        {hint && <span className="block text-xs leading-snug text-muted">{hint}</span>}
      </span>
      {value !== undefined && <span className="max-w-[45%] shrink-0 truncate text-sm text-muted">{value}</span>}
      <ChevronRight size={16} className="shrink-0 text-muted/70" />
    </button>
  );
}
