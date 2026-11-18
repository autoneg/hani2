import { Loader2, Save, Undo2 } from "lucide-react";
import { Group } from "./Group";
import { Row } from "./Row";
import { Toggle } from "./controls/Toggle";
import { Select, Option } from "./controls/Select";
import { Stepper } from "./controls/Stepper";
import { TextArea, TextField } from "./controls/TextField";
import { Tags } from "./controls/Tags";
import { Checks } from "./controls/Checks";
import type { SearchEntry } from "./types";

/** A declarative setting: the same list drives the rows and the search index. */
export interface Field {
  id: string;
  path?: string;
  label: string;
  hint?: string;
  keywords?: string;
  type: "toggle" | "select" | "stepper" | "text" | "password" | "textarea" | "tags" | "checks" | "custom";
  options?: Option[] | { value: string; label: string; hint?: string }[];
  min?: number;
  max?: number;
  step?: number;
  nullable?: boolean;
  placeholder?: string;
  mono?: boolean;
  rows?: number;
  /** stored as null when empty (text fields) */
  emptyNull?: boolean;
  render?: (s: Settings) => React.ReactNode;
  wide?: boolean;
}

export interface FieldGroup {
  title?: string;
  footer?: React.ReactNode;
  fields: Field[];
}

export interface Settings {
  get: (path: string) => any;
  set: (path: string, v: any) => void;
  overridden: (path: string) => boolean;
  reset: (path: string) => void;
}

export const entriesOf = (groups: FieldGroup[]): SearchEntry[] => groups.flatMap((g) => g.fields.map((f) => ({ id: f.id, label: f.label, hint: f.hint, keywords: [g.title, f.keywords, f.path].filter(Boolean).join(" ") })));

function Control({ f, s }: { f: Field; s: Settings }) {
  const v = f.path ? s.get(f.path) : undefined;
  const on = (x: any) => f.path && s.set(f.path, x);
  switch (f.type) {
    case "toggle":
      return <Toggle label={f.label} value={!!v} onChange={on} />;
    case "select":
      return <Select label={f.label} value={v == null ? "" : String(v)} onChange={on} options={f.options as Option[]} />;
    case "stepper":
      return <Stepper label={f.label} value={v} onChange={on} min={f.min} max={f.max} step={f.step} nullable={f.nullable} placeholder={f.placeholder} />;
    case "text":
    case "password":
      return <TextField label={f.label} type={f.type === "password" ? "password" : "text"} value={v} placeholder={f.placeholder} mono={f.mono} onChange={(x) => on(f.emptyNull && !x ? null : x)} />;
    case "textarea":
      return <TextArea label={f.label} value={v} rows={f.rows} mono={f.mono} onChange={on} />;
    case "tags":
      return <Tags label={f.label} value={v} onChange={on} placeholder={f.placeholder} />;
    case "checks":
      return <Checks value={v} onChange={on} options={f.options as any} />;
    case "custom":
      return <>{f.render?.(s)}</>;
  }
}

export function FieldRows({ fields, s }: { fields: Field[]; s: Settings }) {
  return (
    <>
      {fields.map((f) => (
        <Row key={f.id} id={f.id} label={f.label} hint={f.hint} wide={f.wide ?? (f.type === "textarea" || f.type === "checks")} overridden={!!f.path && s.overridden(f.path)} onReset={f.path ? () => s.reset(f.path!) : undefined}>
          <Control f={f} s={s} />
        </Row>
      ))}
    </>
  );
}

export function SchemaGroups({ groups, s }: { groups: FieldGroup[]; s: Settings }) {
  return (
    <>
      {groups.map((g, i) => (
        <Group key={g.title ?? i} title={g.title} footer={g.footer}>
          <FieldRows fields={g.fields} s={s} />
        </Group>
      ))}
    </>
  );
}

/** The bar at the bottom of a settings page. */
export function SaveBar({ dirty, save, discard, where }: { dirty: boolean; save: () => void; discard?: () => void; where?: string }) {
  return (
    <div className="sticky bottom-0 z-10 -mx-4 mt-2 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
      <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved changes${where ? ` · will be saved to ${where}` : ""}` : where ? `Saving to ${where}` : ""}</span>
      {dirty && discard && (
        <button className="btn-ghost" onClick={discard}>
          <Undo2 size={15} /> Revert
        </button>
      )}
      <button className="btn-primary" onClick={save} disabled={!dirty}>
        <Save size={15} /> Save
      </button>
    </div>
  );
}

export const Spinner = () => (
  <div className="flex items-center gap-2 py-10 text-sm text-muted">
    <Loader2 size={16} className="animate-spin" /> Loading…
  </div>
);

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{children}</div>;
}
export function Note({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" | "good" }) {
  const c = tone === "warn" ? "border-warn/30 bg-warn/10 text-warn" : tone === "good" ? "border-good/30 bg-good/10 text-good" : "border-line bg-sunken/70 text-muted";
  return <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</div>;
}
