// Which help text a row shows (no imports, so `node --test` can load this file).

export interface HelpText {
  title: string;
  summary?: string;
  details?: string;
  scheduling?: string;
  docs?: string;
}

/** The help entry of a row: its explicit ``help`` (a key or a text), else the entry of its ``id``
 *  (``scheduling-opponents`` also finds ``scheduling.opponents``). */
export function resolveHelp(help: string | HelpText | undefined, id: string | undefined, table: Record<string, HelpText> | null | undefined): HelpText | null {
  if (help && typeof help === "object") return help;
  const t = table ?? {};
  for (const k of [help, id, id?.replace(/-/g, ".")]) if (k && t[k]) return t[k];
  return null;
}
