import { useEffect, useMemo, useState } from "react";
import { Layers, Search } from "lucide-react";
import { Group } from "../Group";
import { Tile } from "../Row";
import { Disclosure } from "../Disclosure";
import { useNav } from "../Nav";
import { LayerPicker, useLayer } from "../layer";
import { Note, Spinner } from "../schema";
import { toast } from "../toast";
import { AddItems, ItemInfo } from "./common";
import { GroupEditor, NewGroupRow } from "./GroupEditor";
import { listGroups, listItems, toItems } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** One explorer for every kind of library item (scenarios, opponents, Assistants, tools): the
 *  groups they form, the kind's own sections, how to add more, and the items with details. */
export function Explorer({ adapter }: { adapter: Adapter }) {
  const { layer } = useLayer();
  const nav = useNav();
  const [items, setItems] = useState<ExItem[] | null>(null);
  const [groups, setGroups] = useState<ExGroup[] | null>(null);
  const [q, setQ] = useState("");
  const [gq, setGq] = useState("");
  const [tick, setTick] = useState(0);
  const load = () => {
    listItems(adapter.kind, layer)
      .then((r) => setItems(toItems(r, adapter.subtitle, adapter.badge)))
      .catch((e) => (toast(e.message, "error"), setItems([])));
    listGroups(adapter.kind, layer)
      .then(setGroups)
      .catch((e) => (toast(e.message, "error"), setGroups([])));
    setTick((t) => t + 1);
  };
  useEffect(() => {
    setItems(null);
    setGroups(null);
    load();
  }, [layer.id]);
  const shown = useMemo(() => (items ?? []).filter((i) => !q || `${i.title} ${i.subtitle ?? ""} ${i.search ?? ""}`.toLowerCase().includes(q.toLowerCase())), [items, q]);
  const gs = groups ?? [];
  const shownGroups = gs.filter((g) => !gq || `${g.key} ${g.description ?? ""} ${g.origin ?? ""}`.toLowerCase().includes(gq.toLowerCase()));
  const after = () => {
    nav.pop();
    load();
  };
  const openGroup = (g: ExGroup, isNew = false) =>
    nav.push({ title: g.key, render: () => <GroupEditor adapter={adapter} layer={layer} group={g} items={items ?? []} groups={gs} onSaved={after} onReload={load} isNew={isNew} /> });
  const mine = gs.filter((g) => !g.builtin).length;
  return (
    <>
      <LayerPicker />
      {adapter.Intro && <adapter.Intro layer={layer} />}
      <Group
        title={cap(adapter.groupNouns)}
        id={`setting-${adapter.kind}-groups`}
        actions={gs.length > 8 && <SearchBox value={gq} onChange={setGq} label={`Search ${adapter.groupNouns}`} />}
        footer={`Saved to ${layer.label}: a ${adapter.groupNoun} there replaces one of the same name from a less specific layer. Entries are ${adapter.nouns} or other ${adapter.groupNoun === "set" ? "sets" : "groups"} (@name), expanded in place.`}
      >
        {!groups ? (
          <div className="px-4"><Spinner /></div>
        ) : (
          <>
            {!shownGroups.length && <div className="px-4 py-3 text-sm text-muted">{gs.length ? "Nothing matches." : `No ${adapter.groupNouns} yet.`}</div>}
            {shownGroups.map((g) => (
              <Disclosure
                key={`${g.key}-${g.origin}`}
                icon={<Tile icon={Layers} color={g.editable ? "bg-you" : g.inherited ? "bg-opponent" : "bg-muted"} />}
                label={
                  <>
                    @{g.key}
                    {g.builtin && <span className="ml-2 text-xs text-muted">built in</span>}
                    {g.inherited && <span className="ml-2 text-xs text-muted">inherited</span>}
                    {g.active === false && <span className="ml-2 text-xs text-warn">hidden</span>}
                    {g.raw?.default && <span className="ml-2 rounded bg-you/10 px-1.5 text-[0.68rem] text-you">default</span>}
                  </>
                }
                hint={[g.description, g.origin].filter(Boolean).join(" · ") || undefined}
                value={`${g.expanded?.length ?? g.entries.length} ${(g.expanded?.length ?? g.entries.length) === 1 ? adapter.noun : adapter.nouns}`}
                onClick={() => openGroup(g)}
              />
            ))}
            <NewGroupRow adapter={adapter} onCreate={(k) => (gs.some((g) => g.key.toLowerCase() === k.toLowerCase() && g.editable) ? toast(`${k} exists`, "error") : openGroup({ key: k, entries: [], editable: true }, true))} />
          </>
        )}
      </Group>
      {adapter.Extra && groups && items && <adapter.Extra key={`${layer.id}-${tick}`} layer={layer} groups={gs} items={items} reload={load} />}
      <AddItems adapter={adapter} layer={layer} groups={gs} onAdded={load} />
      <Group
        title={`${cap(adapter.nouns)}${items ? ` (${items.length})` : ""}`}
        id={`setting-${adapter.kind}-items`}
        actions={<SearchBox value={q} onChange={setQ} label={`Search ${adapter.nouns}`} />}
        footer={groups && `${mine} ${adapter.groupNoun}${mine === 1 ? "" : "s"} of your own; built-in ${adapter.nouns} cannot be removed here.`}
      >
        {!items ? (
          <div className="px-4"><Spinner /></div>
        ) : !shown.length ? (
          <div className="px-4 py-3 text-sm text-muted">{items.length ? "Nothing matches." : `No ${adapter.nouns} yet.`}</div>
        ) : (
          shown.slice(0, 300).map((it) => (
            <Disclosure
              key={it.id}
              icon={<Tile icon={adapter.icon} color={adapter.color} />}
              label={<>{it.title}{it.badge && <span className="ml-2 rounded bg-sunken px-1.5 py-px text-[0.68rem] text-muted">{it.badge}</span>}</>}
              hint={it.subtitle}
              title={it.id}
              render={() => (
                <>
                  <ItemInfo adapter={adapter} item={it} layer={layer} groups={gs} onChanged={after} />
                  {adapter.ItemExtra && <adapter.ItemExtra item={it} layer={layer} onChanged={after} />}
                </>
              )}
            />
          ))
        )}
      </Group>
      {items && shown.length > 300 && <Note>Showing 300 of {shown.length}; search to narrow.</Note>}
    </>
  );
}

export function SearchBox({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="relative">
      <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
      <input aria-label={label} type="search" className="w-40 rounded-md border border-line bg-surface py-1 pl-7 pr-2 text-sm focus:border-you focus:outline-none sm:w-48" placeholder="Search" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
