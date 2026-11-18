import type { Layer } from "./layer";

/** A searchable entry: one row of a page. */
export interface SearchEntry {
  id: string; // row id (DOM id `setting-<id>`)
  label: string;
  hint?: string;
  keywords?: string;
}

export interface PageProps {
  meta: any;
  layer: Layer;
}

export interface PageDef {
  id: string;
  title: string;
  icon: any;
  color: string; // tile colour class
  group: string;
  subtitle?: string;
  /** old URL fragments that open this page */
  aliases?: string[];
  entries?: SearchEntry[];
  /** entries that depend on the server (tools, abilities) */
  dynamicEntries?: (meta: any) => SearchEntry[];
  Component: (p: PageProps) => React.ReactNode;
  /** a link, not a page */
  href?: string;
}
