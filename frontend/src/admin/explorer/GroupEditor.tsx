import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Layers, Plus, Save, Search, Trash2, TriangleAlert, X } from "lucide-react";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { Disclosure } from "../Disclosure";
import { TextField } from "../controls/TextField";
import { Note } from "../schema";
import { toast } from "../toast";
import { shortPath, type Layer } from "../layer";
import { choices as choicesOf, deleteGroup, describe, groupOf, isRef, saveGroup } from "./library";
import type { Adapter, EntryInfo, ExGroup, ExItem } from "./types";

const PAGE = 60;
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
const an = (w: string) => (/^[aeiou]/i.test(w) ? `an ${w}` : `a ${w}`);

/** A searchable list of entries with what each one is (read-only or editable). */
export function EntryList({ title, entries, adapter, layer, groups, self, onRemove, onMove }: {
  title?: string; entries: string[]; adapter: Adapter; layer: Layer; groups: ExGroup[]; self?: string; onRemove?: (e: string) => void; onMove?: (i: number, d: number) => void;
}) {
  const [q, setQ] = useState("");
  const [n, setN] = useState(PAGE);
  const [desc, setDesc] = useState<Record<string, EntryInfo>>({});
  const shown = useMemo(() => entries.filter((e) => !q || `${e} ${desc[e]?.description ?? ""}`.toLowerCase().includes(q.toLowerCase())), [entries, q, desc]);
  useEffect(() => {
    const need = shown.slice(0, n).filter((e) => !(e in desc));
    if (need.length) describe(adapter.kind, layer, need).then((d) => setDesc((x) => ({ ...x, ...d })));
  }, [shown, n, layer.id]);
  return (
    <Group
      title={title ?? `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`}
      actions={
        entries.length > 8 && (
          <label className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
            <input aria-label="Search entries" className="w-48 rounded-md border border-line bg-surface py-1 pl-7 pr-2 text-sm focus:border-you focus:outline-none" placeholder="Search" value={q} onChange={(e) => (setQ(e.target.value), setN(PAGE))} />
          </label>
        )
      }
    >
      {!shown.length && <div className="px-4 py-3 text-sm text-muted">{entries.length ? "Nothing matches." : "Empty."}</div>}
      {shown.slice(0, n).map((e) => {
        const i = entries.indexOf(e);
        const d = desc[e];
        const g = groupOf(e, groups, self);
        const isGroup = !!g || d?.kind === "group" || (isRef(e) && d?.kind !== "unknown");
        const bad = !!d && !d.ok;
        return (
          <Row
            key={e}
            icon={isGroup ? <Layers size={15} className="text-you" /> : bad ? <TriangleAlert size={15} className="text-bad" /> : undefined}
            label={<code className="break-all text-[0.8rem]">{e}</code>}
            hint={
              isGroup ? (
                `${cap(adapter.groupNoun)}: its ${g?.expanded?.length ?? d?.n ?? "?"} ${(g?.expanded?.length ?? d?.n) === 1 ? adapter.noun : adapter.nouns}, in its order${g?.description ? ` · ${g.description}` : ""}`
              ) : bad ? (
                <span className="text-bad">{d.error || "unknown"}</span>
              ) : d ? (
                d.description || (d.title && d.title !== e ? d.title : "No description")
              ) : (
                "…"
              )
            }
          >
            {onMove && (
              <>
                <button className="btn-ghost px-1" aria-label={`Move ${e} up`} disabled={i === 0} onClick={() => onMove(i, -1)}><ArrowUp size={14} /></button>
                <button className="btn-ghost px-1" aria-label={`Move ${e} down`} disabled={i === entries.length - 1} onClick={() => onMove(i, 1)}><ArrowDown size={14} /></button>
              </>
            )}
            {onRemove && (
              <button className="btn-ghost px-1.5 text-bad" aria-label={`Remove ${e}`} onClick={() => onRemove(e)}>
                <X size={15} />
              </button>
            )}
          </Row>
        );
      })}
      {shown.length > n && (
        <button className="w-full px-4 py-2 text-left text-sm text-you hover:bg-sunken/60" onClick={() => setN(n + PAGE * 3)}>
          Show more ({shown.length - n} more)
        </button>
      )}
    </Group>
  );
}

/** Edit one group or set: its entries (items and other groups), saved to the chosen layer. */
export function GroupEditor({ adapter, layer, group, items, groups, onSaved, onReload, isNew }: { adapter: Adapter; layer: Layer; group: ExGroup; items: ExItem[]; groups: ExGroup[]; onSaved: () => void; onReload?: () => void; isNew?: boolean }) {
  const [entries, setEntries] = useState<string[]>(group.entries);
  const [dirty, setDirty] = useState(!!isNew);
  const [add, setAdd] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const choices = choicesOf(items, groups).filter((c) => c.value.toLowerCase() !== `@${group.key}`.toLowerCase() && !entries.includes(c.value));
  const change = (e: string[]) => (setEntries(e), setDirty(true));
  const doAdd = (v: string) => {
    const x = v.trim();
    if (x && !entries.includes(x)) change([...entries, x]);
    setAdd("");
  };
  const editable = group.editable || !!isNew;
  const canEdit = editable || !!group.inherited;
  const save = async () => {
    try {
      const r = await saveGroup(adapter.kind, layer, group.key, entries);
      setWarnings(r.warnings ?? []);
      toast(`Saved ${adapter.groupNoun} ${group.key} to ${layer.label}${r.warnings?.length ? ` (${r.warnings.length} warning${r.warnings.length === 1 ? "" : "s"})` : ""}`);
      setDirty(false);
      if (!r.warnings?.length) onSaved();
      else onReload?.(); // stay to show the warnings
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const composed = (group.expanded?.length ?? 0) > 0 && JSON.stringify(group.expanded) !== JSON.stringify(group.entries);
  const listId = `choices-${adapter.kind}`;
  return (
    <>
      <Group title={`${cap(adapter.groupNoun)} ${group.key}`}>
        {group.description && <InfoRow label="What it is" value={group.description} />}
        {group.origin && <InfoRow label="Defined in" value={group.origin} hint={group.raw?.path ? shortPath(group.raw.path) : undefined} />}
        {group.active === false && <InfoRow label="Hidden" value="A group of the same name at a more specific layer is used instead" />}
        <InfoRow label={cap(adapter.nouns)} value={group.expanded?.length ?? entries.length} hint={composed ? "after expanding the groups it contains" : undefined} />
        {composed && (
          <Disclosure
            id={`${adapter.kind}-composition`}
            icon={<Layers size={16} className="text-you" />}
            label="Members after composition"
            hint="Groups expanded in place, duplicates dropped, cycles broken"
            value={String(group.expanded!.length)}
            title={`${group.key}: members`}
            render={() => <EntryList title={`${group.expanded!.length} ${adapter.nouns}`} entries={group.expanded!} adapter={adapter} layer={layer} groups={[]} />}
          />
        )}
      </Group>
      {warnings.length > 0 && (
        <Note tone="warn">
          Saved, but:
          <ul className="mt-1 list-disc pl-5">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </Note>
      )}
      {!editable && <Note>{group.builtin ? `Built in: read-only. Make a ${adapter.groupNoun} of your own that lists @${group.key}.` : `Defined in another layer (${group.origin}). Saving copies it into ${layer.label}, where it replaces that one.`}</Note>}
      {canEdit && (
        <Group title={`Add to ${group.key}`} footer={`Type ${an(adapter.noun)} or pick ${an(adapter.groupNoun)} (@name) to include everything in it, in place.`}>
          <Row label={`${cap(adapter.noun)} or ${adapter.groupNoun}`}>
            <input
              aria-label={`Add to ${group.key}`}
              list={listId}
              className="w-72 max-w-full rounded-md border border-line bg-surface px-2 py-1 text-sm focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20"
              placeholder="Start typing…"
              value={add}
              onChange={(e) => setAdd(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), doAdd(add))}
            />
            <datalist id={listId}>
              {choices.slice(0, 500).map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </datalist>
            <button className="btn-secondary" disabled={!add.trim()} onClick={() => doAdd(add)}>
              <Plus size={14} /> Add
            </button>
          </Row>
        </Group>
      )}
      <EntryList
        title={`Entries (${entries.length})`}
        entries={entries}
        adapter={adapter}
        layer={layer}
        groups={groups}
        self={group.key}
        onRemove={canEdit ? (e) => change(entries.filter((x) => x !== e)) : undefined}
        onMove={canEdit && adapter.ordered ? (i, d) => { const n = [...entries]; [n[i], n[i + d]] = [n[i + d], n[i]]; change(n); } : undefined}
      />
      {canEdit && (
        <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t border-line bg-paper/85 px-4 py-3 backdrop-blur sm:-mx-8 sm:px-8">
          <span className="mr-auto truncate text-xs text-muted">{dirty ? `Unsaved · saves to ${layer.label}` : layer.label}</span>
          {group.editable && !isNew && (
            <button
              className="btn-danger"
              onClick={async () => {
                if (!confirm(`Delete ${adapter.groupNoun} ${group.key} from ${layer.label}?`)) return;
                try {
                  await deleteGroup(adapter.kind, layer, group.key);
                  toast(`Deleted ${group.key}`);
                  onSaved();
                } catch (e: any) {
                  toast(e.message, "error");
                }
              }}
            >
              <Trash2 size={14} /> Delete
            </button>
          )}
          <button className="btn-primary" disabled={editable ? !dirty : false} onClick={save}>
            <Save size={15} /> {editable ? "Save" : `Copy into ${layer.kind === "settings" ? "settings" : layer.kind}`}
          </button>
        </div>
      )}
    </>
  );
}

export function NewGroupRow({ adapter, onCreate }: { adapter: Adapter; onCreate: (key: string) => void }) {
  const [k, setK] = useState("");
  const ok = adapter.validKey ? adapter.validKey(k) : /^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$/.test(k);
  return (
    <Row label={`New ${adapter.groupNoun}`} hint={adapter.kind === "opponents" || adapter.kind === "assistants" ? "Letters, digits, '.', '_' and '-'" : "Letters, digits, spaces, '.', '_' and '-'"}>
      <TextField label={`New ${adapter.groupNoun} name`} value={k} onChange={setK} className="w-44" placeholder={adapter.kind === "scenarios" ? "Pilot" : adapter.kind === "tools" ? "basics" : "finalists"} />
      <button className="btn-primary" disabled={!k || !ok} onClick={() => (onCreate(k), setK(""))}>
        <Plus size={15} /> Create
      </button>
    </Row>
  );
}
