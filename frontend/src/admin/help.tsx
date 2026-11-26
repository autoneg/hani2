import { useEffect, useState } from "react";
import { api } from "../api";
import { HelpButton } from "../ui/HelpDialog";
import { Markdown } from "../ui/Markdown";
import { resolveHelp, type HelpText } from "./helpKeys";

/* ``GET /api/admin/help`` and ``GET /api/admin/scheduling-methods`` are fetched once per page load.
 * Both fail silently (a row then has no `?`): the help is an aid, never a reason for an error. */
let helpP: Promise<Record<string, HelpText>> | null = null;
let helpV: Record<string, HelpText> | null = null;

export function useHelpTexts(): Record<string, HelpText> | null {
  const [t, setT] = useState(helpV);
  useEffect(() => {
    if (helpV) return;
    helpP ??= api("/api/admin/help").then((r: any) => (helpV = r?.help ?? {})).catch(() => ((helpP = null), {}));
    let live = true;
    helpP.then((v) => live && setT(v));
    return () => {
      live = false;
    };
  }, []);
  return t;
}

let methods: Promise<any> | null = null;
/** The scheduling methods of each dimension and the defaults (``undefined`` while loading, ``null`` on error). */
export function useScheduling(onError?: (e: any) => void) {
  const [m, setM] = useState<any>(undefined);
  useEffect(() => {
    methods ??= api("/api/admin/scheduling-methods");
    methods.then(setM).catch((e) => ((methods = null), onError?.(e), setM(null)));
  }, []);
  return m;
}

function SchedulingList({ dim }: { dim: string }) {
  const m = useScheduling();
  if (!m) return null;
  const opts = m.dimensions?.[dim] ?? [];
  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="mb-2 text-sm font-semibold">Methods</div>
      <ul className="space-y-1.5 text-sm">
        {opts.map((o: any) => (
          <li key={o.key}>
            <code className="text-[0.8rem]">{o.key}</code>
            {m.defaults?.[dim] === o.key && <span className="ml-1 rounded bg-you/10 px-1.5 text-[0.68rem] text-you">default</span>}
            <span className="text-muted"> — {o.summary}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">"About these methods" at the end of the Scheduling group has the full rules.</p>
    </div>
  );
}

/** The body of a settings `?` dialog. */
export function HelpBody({ h }: { h: HelpText }) {
  return (
    <>
      {h.summary && <p className="mb-3 text-sm text-muted">{h.summary}</p>}
      {h.details && <Markdown math text={h.details} size="sm" />}
      {h.scheduling && <SchedulingList dim={h.scheduling} />}
    </>
  );
}

/** The `?` of a settings row: ``help`` is a key of the help texts or a text of its own. */
export function useRowHelp(help: string | HelpText | undefined, id: string | undefined): HelpText | null {
  const table = useHelpTexts();
  return resolveHelp(help, id, table);
}

export function RowHelpButton({ h }: { h: HelpText }) {
  return <HelpButton label={`About ${h.title}`} title={h.title} size={14} className="-my-1 rounded p-0.5 text-muted hover:text-you" render={() => <HelpBody h={h} />} />;
}

/** A `?` for any label outside a row (a column header, a component field). */
export function HelpFor({ id }: { id: string }) {
  const h = useRowHelp(id, undefined);
  return h ? <RowHelpButton h={h} /> : null;
}
