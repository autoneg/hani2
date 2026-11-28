import { useEffect, useState } from "react";
import { FileCode2, Save, Undo2 } from "lucide-react";
import { Group } from "./Group";
import { TextArea } from "./controls/TextField";

/** The layer's own file as text: the catch-all for every key without a control of its own.
 *  ``parse`` returns the problem with a text (``""``: fine); ``locked`` refuses to open it while
 *  structured edits are unsaved (both would write the same file). */
export function RawFile({ title, text, load, parse, save, locked, lockedNote, footer, id = "raw-file" }: {
  title: string;
  text: string;
  /** reads the file afresh when the editor opens (another control may have saved it since the page loaded) */
  load?: () => Promise<string>;
  parse: (t: string) => string;
  save: (t: string) => Promise<void>;
  locked?: boolean;
  lockedNote?: string;
  footer?: React.ReactNode;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [base, setBase] = useState(text);
  const [draft, setDraft] = useState(text);
  const [busy, setBusy] = useState(false);
  useEffect(() => (setBase(text), setDraft(text)), [text]);
  const problem = open ? parse(draft) : "";
  const dirty = draft !== base;
  const openEditor = async () => {
    let t = text;
    if (load) {
      try {
        t = await load();
      } catch {
        /* keep the text the page has */
      }
    }
    setBase(t);
    setDraft(t);
    setOpen(true);
  };
  return (
    <Group id={id} title={title} footer={footer}>
      {!open ? (
        <div className="flex flex-wrap items-center gap-3 px-4 py-2.5">
          <span className="min-w-0 flex-1 text-xs text-muted">Every key of this layer's own file, including those without a control above.</span>
          <button type="button" className="btn-ghost text-sm" disabled={locked} title={locked ? lockedNote : undefined} onClick={openEditor}>
            <FileCode2 size={14} /> Edit the file
          </button>
          {locked && <span className="w-full text-xs text-warn">{lockedNote}</span>}
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-4 py-3" data-raw-file={id}>
          <TextArea label={title} value={draft} rows={Math.min(30, Math.max(8, draft.split("\n").length + 1))} mono onChange={setDraft} />
          {problem && (
            <div className="text-xs text-bad" role="alert" data-raw-problem>
              {problem}
            </div>
          )}
          <div className="flex items-center justify-end gap-2">
            <button type="button" className="btn-ghost text-sm" onClick={() => (setDraft(base), setOpen(false))}>
              <Undo2 size={14} /> Close without saving
            </button>
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={!dirty || !!problem || busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await save(draft);
                  setOpen(false);
                } catch {
                  /* the caller reported it; the draft stays open */
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Save size={14} /> Save the file
            </button>
          </div>
        </div>
      )}
    </Group>
  );
}

/** ``""`` when ``t`` is a JSON object (or empty), else what is wrong. */
export function jsonObjectProblem(t: string): string {
  if (!t.trim()) return "";
  try {
    const v = JSON.parse(t);
    return v && typeof v === "object" && !Array.isArray(v) ? "" : "The file must be a JSON object: { … }";
  } catch (e: any) {
    return `Not valid JSON: ${e.message}`;
  }
}
