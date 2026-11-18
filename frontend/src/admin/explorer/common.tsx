import { useState } from "react";
import { FileCode2, Link2, Trash2, TriangleAlert } from "lucide-react";
import { Group } from "../Group";
import { InfoRow, Row } from "../Row";
import { shortPath, type Layer } from "../layer";
import { Select } from "../controls/Select";
import { TextField } from "../controls/TextField";
import { Toggle } from "../controls/Toggle";
import { Note } from "../schema";
import { toast } from "../toast";
import { Upload } from "./Upload";
import { forgetDescriptions, link, removeItem, saveGroup, SOURCE_LABEL, upload, type AddResult } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** What an upload or link answered: what was added, the warnings, the notice about code. */
function Outcome({ r }: { r: AddResult & { error?: string } }) {
  if (r.error) return <Note tone="warn">{r.error}</Note>;
  return (
    <Note tone={r.warnings?.length ? "warn" : "good"}>
      Added {r.items.map((i) => i.name).join(", ")}
      {r.items[0]?.n_scenarios !== undefined && ` (${r.items.reduce((a, i) => a + (i.n_scenarios ?? 0), 0)} scenarios)`}
      {" "}to {r.items[0]?.layer}.{r.notice && <> {r.notice}</>}
      {r.warnings?.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {r.warnings.slice(0, 12).map((w) => <li key={w}>{w}</li>)}
          {r.warnings.length > 12 && <li>… {r.warnings.length - 12} more</li>}
        </ul>
      )}
    </Note>
  );
}

/** Upload or link items of any kind (the library's ``upload`` and ``link``). */
export function AddItems({ adapter, layer, groups, onAdded }: { adapter: Adapter; layer: Layer; groups: ExGroup[]; onAdded: () => void }) {
  const [trusted, setTrusted] = useState(false);
  const [group, setGroup] = useState("");
  const [name, setName] = useState("");
  const [classes, setClasses] = useState("");
  const [replace, setReplace] = useState(false);
  const [target, setTarget] = useState("");
  const [syspath, setSyspath] = useState("");
  const [last, setLast] = useState<any>(null);
  const k = adapter.kind;
  const scen = k === "scenarios";
  const needTrust = adapter.code && !scen;
  const done = (r: AddResult) => {
    setLast(r);
    toast(`Added ${r.items.map((i) => i.name).join(", ")}${r.warnings?.length ? ` (${r.warnings.length} warning${r.warnings.length === 1 ? "" : "s"})` : ""}`);
    setName("");
    setTarget("");
    forgetDescriptions();
    onAdded();
  };
  const fields = { name: name || undefined, group: group || undefined, replace, classes: classes || undefined, allow_code: scen ? trusted : undefined };
  const fail = (e: any) => (setLast({ error: e.message }), toast(e.message, "error"));
  const groupOpts = [{ value: "", label: "No group" }, ...groups.filter((g) => !g.builtin && g.active !== false).map((g) => ({ value: g.key, label: `@${g.key}${g.editable ? "" : " (copied into this layer)"}` }))];
  return (
    <Group
      title={`Add ${adapter.nouns}`}
      id={`setting-${k}-add`}
      footer={
        <>
          Added to {layer.label}: {scen ? <>uploads to its <code>scenarios/</code> folder, links in <code>scenario_links.yaml</code></> : <>uploads to its <code>library/{k}/</code> folder, uploads and links listed in <code>library.yaml</code></>}. {adapter.uploadHint}
        </>
      }
    >
      {adapter.code && (
        <div className="flex items-start gap-2 bg-warn/10 px-4 py-2.5 text-sm text-warn">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" />
          <span>{scen ? "A scenario may bring a display.py: Python code that runs on this server whenever an offer is shown." : `Uploaded and linked ${adapter.nouns} are Python code. They run inside this server, with its permissions, when they are checked and whenever they are used.`} Only add code you trust.</span>
        </div>
      )}
      {adapter.code && (
        <Row label={scen ? "Allow Python files (display.py)" : "I trust this code"} hint={scen ? "Off: archives and folders with .py files are refused" : "Required before uploading or linking"}>
          <Toggle label={scen ? "Allow Python files" : "I trust this code"} value={trusted} onChange={setTrusted} />
        </Row>
      )}
      <Row label="Name" hint={scen ? "The scenario type (default: the zip's top folder or file name)" : "For one class: its name in the library (default: the class name)"}>
        <TextField label="Name for the new item" value={name} onChange={setName} placeholder="optional" className="w-40" />
      </Row>
      {adapter.code && !scen && (
        <Row label="Classes" hint={`Comma-separated (default: every ${adapter.noun} class found)`}>
          <TextField label="Classes to take" value={classes} onChange={setClasses} placeholder="optional" className="w-40" mono />
        </Row>
      )}
      <Row label="Also add to group" hint="Created when missing; a group of a less specific layer is copied into this one">
        <Select label="Add to group" value={group} onChange={setGroup} options={groupOpts} />
      </Row>
      <Row label={`Replace ${scen ? "a type" : "an item"} of the same name`} hint="Only one added at this layer; the old files go to .trash">
        <Toggle label="Replace" value={replace} onChange={setReplace} />
      </Row>
      <Row id={`${k}-upload`} icon={<FileCode2 size={16} className="text-you" />} label={`Upload ${adapter.accept.replace(/,/g, " or ")}`} hint="Checked before it is kept: safe paths only, everything must load">
        <Upload disabled={needTrust && !trusted} accept={adapter.accept} send={async (f) => { try { done(await upload(k, layer, f, fields)); } catch (e) { fail(e); } }} />
      </Row>
      <Row id={`${k}-link`} icon={<Link2 size={16} className="text-you" />} label={scen ? "Link a folder on the server" : "Link a path or a class"} hint={scen ? "A scenario folder or a category of them, read in place (absolute path)" : "An absolute path to a .py file or package folder, or a class spec"}>
        <TextField label="Path or class to link" value={target} onChange={setTarget} placeholder={adapter.linkHint} className="w-60" mono />
        <button className="btn-secondary" disabled={!target || (needTrust && !trusted)} onClick={async () => { try { done(await link(k, layer, { target, ...fields, syspath: syspath ? syspath.split(",").map((s) => s.trim()).filter(Boolean) : undefined, classes: classes ? classes.split(",").map((s) => s.trim()) : undefined })); } catch (e) { fail(e); } }}>
          <Link2 size={14} /> Link
        </button>
      </Row>
      {adapter.code && !scen && (
        <Row label="Import path for a class spec" hint="Comma-separated absolute folders added to sys.path (optional)">
          <TextField label="Import path" value={syspath} onChange={setSyspath} placeholder="/srv/agents" className="w-60" mono />
        </Row>
      )}
      {last && <div className="px-4 py-2"><Outcome r={last} /></div>}
    </Group>
  );
}

/** The rows every item has, the remove button, and adding it to a group. */
export function ItemInfo({ adapter, item, layer, groups, onChanged }: { adapter: Adapter; item: ExItem; layer: Layer; groups: ExGroup[]; onChanged: () => void }) {
  const i = item.raw;
  const [target, setTarget] = useState("");
  const addable = groups.filter((g) => !g.builtin && g.active !== false && !i.groups.some((x) => x.toLowerCase() === g.key.toLowerCase()));
  const addTo = async () => {
    const g = groups.find((x) => x.key === target);
    if (!g) return;
    try {
      const r = await saveGroup(adapter.kind, layer, g.key, [...g.entries, i.name]);
      toast(`Added to @${g.key}${g.editable ? "" : ` (copied into ${layer.label})`}${r.warnings?.length ? `: ${r.warnings.join("; ")}` : ""}`, r.warnings?.length ? "error" : undefined);
      onChanged();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  const remove = async () => {
    const linked = i.source === "linked";
    if (!confirm(linked ? `Unlink ${i.name}? What it points to stays where it is.` : `Remove ${i.name} from ${layer.label}? Its files go to the layer's .trash folder.`)) return;
    try {
      const r = await removeItem(adapter.kind, layer, i.name);
      toast(r.how === "unlinked" ? `Unlinked ${i.name}` : r.trash ? `Moved to ${shortPath(r.trash)}` : `Removed ${i.name}`);
      forgetDescriptions();
      onChanged();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };
  return (
    <>
      <Group title={cap(adapter.noun)}>
        <InfoRow label="Name" value={i.name} mono />
        {i.title && i.title !== i.name && <InfoRow label="Title" value={i.title} />}
        <InfoRow label="Description" value={i.description || "No description"} />
        <InfoRow label="Source" value={`${SOURCE_LABEL[i.source] ?? i.source}${i.layer ? ` at ${i.layer}` : ""}`} hint={i.source === "registered" ? "Made available another way: a plugin, env.json, an environment variable or a group file" : undefined} />
        {i.spec && i.spec !== i.name && <InfoRow label="Class" value={i.spec} mono />}
        {i.path && <InfoRow label={i.source === "linked" ? "Linked path" : "Path"} value={shortPath(i.path)} mono />}
        <InfoRow label={`In ${adapter.groupNouns}`} value={i.groups.length ? i.groups.join(", ") : "none"} />
        {i.removable ? (
          <Row label={i.source === "linked" ? "Unlink" : "Remove"} hint={i.source === "linked" ? "Removes the link only" : "Its files go to this layer's .trash folder; groups that list it are not changed"}>
            <button className="btn-danger" onClick={remove}><Trash2 size={14} /> {i.source === "linked" ? "Unlink" : "Remove"}</button>
          </Row>
        ) : (i.source === "uploaded" || i.source === "linked") && i.layer !== layer.id ? (
          <InfoRow label="Remove" value={`Added at ${i.layer}: choose that layer to remove it`} />
        ) : null}
      </Group>
      {addable.length > 0 && (
        <Group title="Add to a group" footer={`Saved to ${layer.label}; a group of a less specific layer is copied into it.`}>
          <Row label="Group">
            <Select label="Target group" value={target} onChange={setTarget} options={[{ value: "", label: "Choose…" }, ...addable.map((g) => ({ value: g.key, label: `@${g.key}${g.editable ? "" : " (copy)"}` }))]} />
            <button className="btn-primary" disabled={!target} onClick={addTo}>Add</button>
          </Row>
        </Group>
      )}
    </>
  );
}
