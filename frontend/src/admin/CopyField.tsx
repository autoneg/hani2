import { Copy, ExternalLink } from "lucide-react";
import { copyText } from "./toast";

/** A row value that can be copied (and opened, for a URL). */
export function CopyField({ value, label, open }: { value: string; label: string; open?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-1">
      <code className="min-w-0 flex-1 select-all truncate rounded-md border border-line bg-paper/60 px-2 py-1 text-xs" title={value}>
        {value}
      </code>
      <button className="btn-ghost shrink-0 px-1.5" aria-label={`Copy ${label}`} title="Copy" onClick={() => copyText(value)}>
        <Copy size={14} />
      </button>
      {open && (
        <a className="btn-ghost shrink-0 px-1.5" aria-label={`Open ${label}`} title="Open" href={value} target="_blank" rel="noreferrer">
          <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}
