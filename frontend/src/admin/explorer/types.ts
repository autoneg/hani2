import type { Layer } from "../layer";

/** The library kinds (``/api/admin/library/{kind}``). */
export type Kind = "scenarios" | "opponents" | "assistants" | "tools";

/** A library item as the API lists it (``GET /api/admin/library/{kind}``). */
export interface LibItem {
  name: string;
  title: string;
  description: string;
  source: "builtin" | "registered" | "uploaded" | "linked";
  layer: string | null;
  spec?: string;
  path?: string | null;
  groups: string[];
  removable: boolean;
  [k: string]: any;
}

/** One thing an explorer lists (a scenario type, an opponent, an Assistant, a tool). */
export interface ExItem {
  id: string;
  title: string;
  subtitle?: string;
  badge?: string;
  search?: string;
  raw: LibItem;
}

/** A named collection of entries (a scenario set; an opponent, Assistant or tool group).
 *  Entries are items or other groups (composition: ``@name``, or ``:name`` as before). */
export interface ExGroup {
  key: string;
  description?: string;
  /** the raw entries, as written */
  entries: string[];
  /** the members after composition */
  expanded?: string[];
  origin?: string;
  /** defined at the chosen layer (saved and deleted there) */
  editable: boolean;
  /** defined at a less specific layer (read-only here; saving copies it into this layer) */
  inherited?: boolean;
  /** false when a group of the same name at a more specific layer hides it */
  active?: boolean;
  builtin?: boolean;
  raw?: any;
}

export interface Choice {
  value: string;
  label: string;
  hint?: string;
  group?: boolean;
}

/** What an entry of a group is (``POST /api/admin/library/{kind}/describe``). */
export interface EntryInfo {
  entry: string;
  kind: "item" | "group" | "unknown";
  name: string;
  title?: string;
  description?: string;
  n?: number;
  ok: boolean;
  error?: string;
}

export interface Adapter {
  kind: Kind;
  noun: string;
  nouns: string;
  groupNoun: string;
  groupNouns: string;
  icon: any;
  color: string;
  /** entries keep their order (scenario sets) */
  ordered?: boolean;
  /** uploads are Python code (scenarios: may hold a display.py) */
  code: boolean;
  Intro?: (p: { layer: Layer }) => React.ReactNode;
  /** kind-specific item sections (after the common ones) */
  ItemExtra?: (p: { item: ExItem; layer: Layer; onChanged: () => void }) => React.ReactNode;
  /** kind-specific sections of the explorer page (pools, default set, offer, placement) */
  Extra?: (p: { layer: Layer; groups: ExGroup[]; items: ExItem[]; reload: () => void }) => React.ReactNode;
  /** how an item is shown in the list */
  subtitle?: (i: LibItem) => string;
  badge?: (i: LibItem) => string | undefined;
  validKey?: (k: string) => boolean;
  /** placeholder of the link field */
  linkHint: string;
  /** what an upload holds */
  uploadHint: string;
  /** accepted upload files */
  accept: string;
}
