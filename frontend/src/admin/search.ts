import type { PageDef, SearchEntry } from "./types";

export interface Hit {
  page: PageDef;
  entry: SearchEntry | null; // null: the page itself
  score: number;
}

const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");

/** Settings whose label, hint or keywords contain every word of the query (labels rank first). */
export function searchSettings(pages: PageDef[], meta: any, q: string): Hit[] {
  const words = norm(q).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const hits: Hit[] = [];
  for (const page of pages) {
    const pt = norm(page.title);
    if (words.every((w) => pt.includes(w))) hits.push({ page, entry: null, score: 0 });
    const entries = [...(page.entries ?? []), ...(page.dynamicEntries && meta ? page.dynamicEntries(meta) : [])];
    for (const e of entries) {
      const label = norm(e.label);
      const all = `${label} ${norm(e.hint ?? "")} ${norm(e.keywords ?? "")} ${pt}`;
      if (!words.every((w) => all.includes(w))) continue;
      hits.push({ page, entry: e, score: words.every((w) => label.includes(w)) ? (label.startsWith(words[0]) ? 1 : 2) : 3 });
    }
  }
  return hits.sort((a, b) => a.score - b.score).slice(0, 60);
}
